from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image, PngImagePlugin

from snippets.audit import audit_changes
from snippets.duplicates import duplicate_groups
from snippets.models import Burial, Cemetery, CemeteryPlan, Deceased, Grave, GraveFee, RecordChange, SavedGrave, Section


def plan_image():
    stream = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("location", "private metadata")
    Image.new("RGB", (200, 100), "white").save(stream, format="PNG", pnginfo=metadata)
    return SimpleUploadedFile("plan.png", stream.getvalue(), content_type="image/png")


class LocationFeaturesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mod = User.objects.create_user("map-moderator")
        cls.mod.groups.add(Group.objects.get(name="Moderators"))
        cls.user = User.objects.create_user("map-user")
        cls.other = User.objects.create_user("map-other")
        cls.staff = User.objects.create_user("map-staff", is_staff=True)
        cls.inactive = User.objects.create_user("map-inactive", is_superuser=True, is_active=False)
        cls.root = User.objects.create_superuser("map-root", password="test")
        cls.cemetery = Cemetery.objects.create(name="Parkowy")
        cls.section = Section.objects.create(cemetery=cls.cemetery, name="A")
        cls.grave = Grave.objects.create(section=cls.section, row="1", number="1")
        cls.second = Cemetery.objects.create(name="Leśny")
        cls.second_section = Section.objects.create(cemetery=cls.second, name="B")
        cls.other_grave = Grave.objects.create(section=cls.second_section, row="1", number="2")

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        setting = override_settings(MEDIA_ROOT=self.media.name)
        setting.enable()
        self.addCleanup(setting.disable)

    def upload(self, **extra):
        self.client.force_login(self.mod)
        return self.client.post(reverse("moderator-plan-edit", args=[self.cemetery.pk]),
                                {"image": plan_image(), **extra})

    def position(self, **extra):
        self.client.force_login(self.mod)
        plan = CemeteryPlan.objects.filter(cemetery=self.cemetery).first()
        return self.client.post(reverse("moderator-position-edit", args=[self.grave.pk]),
            {"map_x": "25.50", "map_y": "60", "plan_revision": plan.image.name if plan else "", **extra})

    def test_permissions_methods_and_csrf(self):
        urls = [reverse(name, args=[pk]) for name, pk in [
            ("moderator-plan-edit", self.cemetery.pk), ("moderator-position-edit", self.grave.pk),
            ("moderator-fee-edit", self.grave.pk)]]
        urls += [reverse("moderator-fees"), reverse("moderator-duplicates")]
        for user, expected in [(None, 302), (self.user, 403), (self.staff, 403), (self.inactive, 302)]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            for url in urls:
                for method in ["get", "post"]:
                    self.assertEqual(getattr(self.client, method)(url).status_code, expected)
        for user in [self.mod, self.root]:
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 200)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.mod)
        for url in urls[:3]:
            self.assertEqual(client.post(url).status_code, 403)
        self.assertEqual(self.client.post(reverse("moderator-duplicates")).status_code, 405)
        self.assertEqual(self.client.post(reverse("cemetery-map", args=[self.cemetery.pk])).status_code, 405)

    def test_plan_upload_sanitizes_image_and_public_map_highlights_only_own_cemetery(self):
        self.assertEqual(self.upload().status_code, 302)
        plan = CemeteryPlan.objects.get()
        with Image.open(plan.image.path) as image:
            self.assertNotIn("location", image.info)
        self.assertEqual(self.position().status_code, 302)
        self.client.logout()
        response = self.client.get(reverse("cemetery-map", args=[self.cemetery.pk]), {"grave": self.grave.pk})
        self.assertContains(response, 'aria-current="location"')
        self.assertContains(response, 'left: 25.50%; top: 60.00%')
        self.assertNotContains(response, "Zarządzaj planem")
        self.assertContains(self.client.get(self.grave.get_absolute_url()), "Położenie grobu")
        self.assertEqual(self.client.get(reverse("cemetery-map", args=[self.cemetery.pk]), {"grave": self.other_grave.pk}).status_code, 404)
        self.assertContains(self.client.get(reverse("cemetery-map", args=[self.second.pk])), "nie został jeszcze dodany")
        self.assertTrue(RecordChange.objects.filter(entity_type="cemeteryplan", editor=self.mod).exists())
        self.assertEqual(RecordChange.objects.get(entity_type="grave").after["map_x"], "25.50")

    def test_invalid_plan_upload_leaves_existing_plan_and_markers(self):
        self.upload(); self.position()
        original = CemeteryPlan.objects.get().image.name
        for upload in [SimpleUploadedFile("fake.png", b"fake"),
                       SimpleUploadedFile("large.png", b"x" * (5 * 1024 * 1024 + 1))]:
            response = self.client.post(reverse("moderator-plan-edit", args=[self.cemetery.pk]), {"image": upload})
            self.assertTrue(response.context["form"].errors)
        self.assertEqual(CemeteryPlan.objects.get().image.name, original)
        self.grave.refresh_from_db()
        self.assertEqual(self.grave.map_x, Decimal("25.50"))

    def test_plan_replacement_requires_confirmation_and_cleans_old_file_after_commit(self):
        self.upload(); self.position()
        plan = CemeteryPlan.objects.get()
        old_path, revision = plan.image.path, plan.image.name
        response = self.upload()
        self.assertIn("reset_positions", response.context["form"].errors)
        self.assertEqual(CemeteryPlan.objects.get().image.name, revision)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.upload(reset_positions="on").status_code, 302)
        self.assertFalse(Path(old_path).exists())
        self.grave.refresh_from_db()
        self.assertIsNone(self.grave.map_x)
        self.assertIsNone(self.grave.map_y)
        self.assertTrue(RecordChange.objects.filter(entity_type="grave", after__map_x=None).exists())
        self.assertTrue(self.position(plan_revision=revision).context["form"].non_field_errors())

    def test_failed_plan_audit_removes_new_file_and_retains_previous_plan(self):
        self.upload(); self.position()
        old_path = CemeteryPlan.objects.get().image.path
        old_count = RecordChange.objects.count()
        with patch("snippets.audit.RecordChange.objects.create", side_effect=IntegrityError("failed audit")):
            response = self.upload(reset_positions="on")
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(RecordChange.objects.count(), old_count)
        self.assertEqual(CemeteryPlan.objects.get().image.path, old_path)
        self.assertEqual([str(p) for p in Path(self.media.name).rglob("*") if p.is_file()], [old_path])
        self.grave.refresh_from_db()
        self.assertEqual(self.grave.map_x, Decimal("25.50"))

    def test_position_validation_boundary_clear_and_noop_history(self):
        self.assertTrue(self.position().context["form"].errors)  # No plan yet.
        self.upload()
        for data in [{"map_x": "-1"}, {"map_y": "101"}, {"map_x": "NaN"},
                     {"map_x": ""}, {"map_x": "5.555"}, {"map_y": "Infinity"}]:
            self.assertTrue(self.position(**data).context["form"].errors)
        self.assertEqual(self.position(map_x="0", map_y="100").status_code, 302)
        count = RecordChange.objects.count()
        self.assertEqual(self.position(map_x="0.00", map_y="100.00").status_code, 302)
        self.assertEqual(RecordChange.objects.count(), count)
        self.assertEqual(self.position(map_x="", map_y="").status_code, 302)
        self.grave.refresh_from_db()
        self.assertIsNone(self.grave.map_x)
        for values in [(None, 1), (0, None), (-1, 50), (101, 50)]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Grave.objects.filter(pk=self.grave.pk).update(map_x=values[0], map_y=values[1])

    def test_moving_grave_or_section_to_another_cemetery_clears_coordinates(self):
        self.upload(); self.position()
        self.client.post(reverse("moderator-grave-edit", args=[self.grave.pk]),
            {"cemetery": self.second.pk, "section": self.second_section.pk, "row": "4", "number": "4"})
        self.grave.refresh_from_db()
        self.assertEqual(self.grave.section_id, self.second_section.pk)
        self.assertIsNone(self.grave.map_x)
        Grave.objects.filter(pk=self.grave.pk).update(section=self.section, map_x=1, map_y=2)
        self.client.post(reverse("moderator-section-edit", args=[self.section.pk]),
                         {"cemetery": self.second.pk, "name": "Moved"})
        self.grave.refresh_from_db()
        self.assertIsNone(self.grave.map_x)

    def test_plan_deletion_defers_file_cleanup_and_rollback_keeps_file(self):
        self.upload()
        plan = CemeteryPlan.objects.get()
        path = plan.image.path
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(IntegrityError), audit_changes(self.mod):
                plan.delete()
                raise IntegrityError("rollback")
        self.assertTrue(Path(path).exists())
        with self.captureOnCommitCallbacks(execute=True), audit_changes(self.mod):
            CemeteryPlan.objects.get().delete()
        self.assertFalse(Path(path).exists())

    def test_fee_dates_are_private_and_reminders_have_inclusive_30_day_boundary(self):
        today = timezone.localdate()
        graves = [self.grave]
        for i in range(4):
            graves.append(Grave.objects.create(section=self.section, row="F", number=str(i)))
        for grave, offset in zip(graves, [-1, 0, 30, 31, -50]):
            GraveFee.objects.create(grave=grave, valid_until=today + timedelta(days=offset))
        for grave in graves[:4]:
            SavedGrave.objects.create(user=self.user, grave=grave)
        SavedGrave.objects.create(user=self.other, grave=graves[4])
        self.assertEqual(self.client.get(reverse("fee-reminders")).status_code, 302)
        self.assertNotContains(self.client.get(self.grave.get_absolute_url()), "Termin opłaty")
        self.assertNotIn("valid_until", self.client.get(reverse("grave-api-detail", args=[self.grave.pk])).content.decode())
        self.client.force_login(self.user)
        response = self.client.get(reverse("fee-reminders"))
        self.assertEqual(response.context["paginator"].count, 3)
        self.assertEqual(response.context["fee_reminder_count"], 3)
        self.assertEqual(self.client.get(reverse("fee-reminders"), {"status": "overdue"}).context["paginator"].count, 1)
        self.assertEqual(self.client.get(reverse("fee-reminders"), {"status": "soon"}).context["paginator"].count, 2)
        self.assertEqual(self.client.get(reverse("fee-reminders"), {"status": "all"}).context["paginator"].count, 4)
        self.assertContains(self.client.get(self.grave.get_absolute_url()), "Termin opłaty")
        self.client.post(reverse("grave-unsave", args=[self.grave.pk]))
        self.assertNotContains(self.client.get(self.grave.get_absolute_url()), "Termin opłaty")
        self.assertEqual(self.client.get(reverse("fee-reminders")).context["paginator"].count, 2)
        self.client.force_login(self.mod)
        self.assertEqual(self.client.get(reverse("moderator-fees")).context["paginator"].count, 4)

    def test_fee_edit_records_author_and_renewal_removes_reminder(self):
        self.client.force_login(self.mod)
        url = reverse("moderator-fee-edit", args=[self.grave.pk])
        today = timezone.localdate()
        self.assertTrue(self.client.post(url, {"valid_until": "invalid"}).context["form"].errors)
        self.assertEqual(self.client.post(url, {"valid_until": today.isoformat()}).status_code, 302)
        self.assertEqual(RecordChange.objects.get(entity_type="gravefee").editor, self.mod)
        self.client.post(url, {"valid_until": today.isoformat()})
        self.assertEqual(RecordChange.objects.filter(entity_type="gravefee").count(), 1)
        SavedGrave.objects.create(user=self.user, grave=self.grave)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("fee-reminders")).context["paginator"].count, 1)
        self.client.force_login(self.mod)
        self.client.post(url, {"valid_until": (today + timedelta(days=365)).isoformat()})
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("fee-reminders")).context["paginator"].count, 0)
        self.assertEqual(RecordChange.objects.filter(entity_type="gravefee", action="update").count(), 1)

    def test_fee_reminder_pagination_invalid_filter_and_account_isolation(self):
        for i in range(21):
            grave = Grave.objects.create(section=self.section, row="P", number=str(i))
            GraveFee.objects.create(grave=grave, valid_until=timezone.localdate())
            SavedGrave.objects.create(user=self.user, grave=grave)
        self.client.force_login(self.user)
        self.assertEqual(len(self.client.get(reverse("fee-reminders")).context["page_obj"]), 20)
        self.assertEqual(len(self.client.get(reverse("fee-reminders"), {"page": 2}).context["page_obj"]), 1)
        self.assertTrue(self.client.get(reverse("fee-reminders"), {"status": "bad"}).context["form"].errors)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("fee-reminders"), {"status": "all", "user": self.user.pk}).context["paginator"].count, 0)

    def test_duplicate_detection_normalizes_unicode_case_and_spaces_without_merging(self):
        params = dict(birth_date=date(1900, 1, 1), death_date=date(1980, 1, 1))
        first = Deceased.objects.create(name="ŁUCJA  Anna", surname="Żółć", **params)
        second = Deceased.objects.create(name="  łucja anna ", surname="z\u0307o\u0301łc\u0301", **params)
        Deceased.objects.create(name="Łucja Anna", surname="Żółć", birth_date=date(1900, 1, 1), death_date=date(1981, 1, 1))
        groups = duplicate_groups("deceased")
        self.assertEqual([[obj.pk for obj in group] for group in groups], [[first.pk, second.pk]])
        self.client.force_login(self.mod)
        response = self.client.get(reverse("moderator-duplicates"))
        self.assertContains(response, reverse("moderator-deceased-edit", args=[first.pk]))
        self.assertContains(response, reverse("moderator-deceased-edit", args=[second.pk]))
        self.assertEqual(Deceased.objects.count(), 3)
        self.assertFalse(RecordChange.objects.exists())

    def test_duplicates_for_locations_and_burials_exclude_unrelated_records(self):
        Cemetery.objects.create(name=" parkowy ")
        Cemetery.objects.create(name="Parkowy", address="Inny adres")
        Section.objects.create(cemetery=self.cemetery, name=" a ")
        Grave.objects.create(section=self.section, row=" 1 ", number="1")
        person = Deceased.objects.create(name="Jan", surname="Test", birth_date="1900-01-01", death_date="1980-01-01")
        for _ in range(2):
            Burial.objects.create(deceased=person, grave=self.grave, burial_date="1980-01-02")
        for kind in ["cemetery", "section", "grave", "burial"]:
            self.assertEqual(len(duplicate_groups(kind)), 1)
        self.client.force_login(self.mod)
        self.assertTrue(self.client.get(reverse("moderator-duplicates"), {"kind": "bad"}).context["form"].errors)

    def test_duplicate_pagination_keeps_default_person_filter(self):
        for i in range(21):
            for _ in range(2):
                Deceased.objects.create(name="Jan", surname=f"Osoba {i}", birth_date="1900-01-01", death_date="1980-01-01")
        self.client.force_login(self.mod)
        response = self.client.get(reverse("moderator-duplicates"), {"page": 2})
        self.assertEqual(response.context["paginator"].count, 21)
        self.assertEqual(len(response.context["groups"]), 1)
        self.assertContains(response, "Sprawdź rekord")

    def test_map_rejects_invalid_selected_ids_and_editor_hides_revision_label(self):
        self.upload()
        for value in ["invalid", "1" * 100, "9999999999999999999"]:
            self.assertEqual(self.client.get(reverse("cemetery-map", args=[self.cemetery.pk]), {"grave": value}).status_code, 404)
        response = self.client.get(reverse("moderator-position-edit", args=[self.grave.pk]))
        self.assertContains(response, 'type="hidden" name="plan_revision"')
        self.assertNotContains(response, 'for="id_plan_revision"')
