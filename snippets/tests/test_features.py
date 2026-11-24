from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image, PngImagePlugin

from snippets.audit import audit_changes
from snippets.models import (Burial, Cemetery, CorrectionRequest, Deceased, Grave,
                             GravePhoto, RecordChange, SavedGrave, Section)
from snippets.moderation import review_request
from snippets.photo_forms import GravePhotoForm


def picture(fmt="PNG", size=(20, 10), **kwargs):
    stream = BytesIO()
    Image.new("RGB", size, "green").save(stream, format=fmt, **kwargs)
    return SimpleUploadedFile("untrusted.name", stream.getvalue(), content_type="application/octet-stream")


class FeatureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("visitor")
        cls.other = User.objects.create_user("other")
        cls.staff = User.objects.create_user("staff", is_staff=True)
        cls.mod = User.objects.create_user("moderator")
        cls.mod.groups.add(Group.objects.get(name="Moderators"))
        cls.root = User.objects.create_superuser("root", password="test")
        cls.inactive = User.objects.create_user("inactive", is_superuser=True, is_active=False)
        cls.cemetery = Cemetery.objects.create(name="Centralny", address="Lipowa")
        cls.section = Section.objects.create(cemetery=cls.cemetery, name="A")
        cls.grave = Grave.objects.create(section=cls.section, row="1", number="2")

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def url(self, name, obj=None):
        return reverse(name, args=[(obj or self.grave).pk] if name in (
            "grave-save", "grave-unsave", "photo-upload", "photo-delete",
            "moderator-grave-edit", "moderator-grave-delete") else [])

    def upload(self, user=None, image=None, caption="Podpis"):
        self.client.force_login(user or self.mod)
        return self.client.post(self.url("photo-upload"), {"image": image or picture(), "caption": caption})

    def test_saved_actions_idempotent_and_account_scoped(self):
        self.client.force_login(self.user)
        for _ in range(2):
            self.assertEqual(self.client.post(self.url("grave-save")).status_code, 302)
        self.assertEqual(SavedGrave.objects.count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SavedGrave.objects.create(user=self.user, grave=self.grave)
        SavedGrave.objects.create(user=self.other, grave=self.grave)
        for _ in range(2):
            self.client.post(self.url("grave-unsave"), {"user": self.other.pk})
        self.assertEqual(SavedGrave.objects.get().user, self.other)
        self.assertEqual(RecordChange.objects.count(), 0)

    def test_saved_login_post_csrf_and_visibility(self):
        for name in ("grave-save", "grave-unsave", "saved-graves"):
            self.assertEqual(self.client.get(self.url(name)).status_code, 302)
        self.client.force_login(self.user)
        for name in ("grave-save", "grave-unsave"):
            self.assertEqual(self.client.get(self.url(name)).status_code, 405)
            client = Client(enforce_csrf_checks=True)
            client.force_login(self.user)
            self.assertEqual(client.post(self.url(name)).status_code, 403)
        self.assertContains(self.client.get(self.grave.get_absolute_url()), "Zapisz grób")
        self.client.post(self.url("grave-save"))
        self.assertContains(self.client.get(self.grave.get_absolute_url()), "Usuń z zapisanych")
        self.assertContains(self.client.get(self.url("saved-graves")), str(self.grave))
        self.client.force_login(self.other)
        self.assertContains(self.client.get(self.url("saved-graves")), "Nie masz jeszcze")

    def test_saved_pagination_and_cascades(self):
        for i in range(21):
            grave = Grave.objects.create(section=self.section, row="P", number=str(i))
            SavedGrave.objects.create(user=self.user, grave=grave)
        self.client.force_login(self.user)
        response = self.client.get(self.url("saved-graves"))
        self.assertEqual(len(response.context["page_obj"]), 20)
        self.assertEqual(len(self.client.get(self.url("saved-graves"), {"page": 2}).context["page_obj"]), 1)
        grave.delete()
        self.assertEqual(SavedGrave.objects.count(), 20)
        self.user.delete()
        self.assertFalse(SavedGrave.objects.exists())

    def test_feature_roles_and_post_only_upload(self):
        self.upload()
        photo = GravePhoto.objects.get()
        endpoints = [self.url("photo-upload"), self.url("photo-delete", photo), self.url("record-history")]
        for user, status in ((None, 302), (self.user, 403), (self.staff, 403), (self.inactive, 302)):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for endpoint in endpoints:
                for method in ("get", "post"):
                    self.assertEqual(getattr(self.client, method)(endpoint).status_code, status)
        for user in (self.mod, self.root):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url("photo-upload")).status_code, 405)
            self.assertEqual(self.client.get(self.url("photo-delete", photo)).status_code, 200)
            self.assertEqual(self.client.get(self.url("record-history")).status_code, 200)
            self.assertEqual(self.client.post(self.url("record-history")).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.mod)
        for endpoint in endpoints[:2]:
            self.assertEqual(client.post(endpoint).status_code, 403)

    def test_valid_photos_public_gallery_order_and_metadata(self):
        info = PngImagePlugin.PngInfo()
        info.add_text("private", "secret location")
        self.assertEqual(self.upload(image=picture(pnginfo=info)).status_code, 302)
        first = GravePhoto.objects.get()
        with Image.open(first.image.path) as decoded:
            self.assertNotIn("private", decoded.info)
        self.assertNotIn("untrusted", first.image.name)
        self.assertEqual(first.uploader, self.mod)
        self.assertEqual(self.upload(image=picture("JPEG"), caption="Drugie").status_code, 302)
        second = GravePhoto.objects.latest("pk")
        with Image.open(second.image.path) as decoded:
            self.assertEqual(decoded.format, "JPEG")
        self.client.logout()
        response = self.client.get(self.grave.get_absolute_url())
        self.assertContains(response, first.image.url)
        self.assertLess(response.content.index(b"Drugie"), response.content.index(b"Podpis"))
        self.assertEqual(list(self.grave.photos.all()), [second, first])
        self.assertNotContains(response, "Usuń zdjęcie")
        self.assertEqual(RecordChange.objects.filter(entity_type="gravephoto", action="create").count(), 2)

    def test_invalid_images_size_dimensions_animation(self):
        stream = BytesIO()
        frames = [Image.new("RGB", (10, 10), color) for color in ("red", "blue")]
        frames[0].save(stream, format="PNG", save_all=True, append_images=frames[1:])
        cases = [SimpleUploadedFile("fake.jpg", b"not an image"),
                 SimpleUploadedFile("large.png", b"x" * (5 * 1024 * 1024 + 1)),
                 picture("GIF"), picture(size=(5000, 4001)),
                 SimpleUploadedFile("animated.png", stream.getvalue()),
                 SimpleUploadedFile("truncated.png", picture().read()[:40])]
        for image in cases:
            with self.subTest(name=image.name):
                response = self.upload(image=image)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.context["form"].errors)
        self.assertFalse(GravePhoto.objects.exists())
        self.assertFalse(RecordChange.objects.exists())
        # Boundary is inclusive; avoid storing a large image for this form check.
        form = GravePhotoForm(files={"image": picture(size=(5000, 4000))})
        self.assertTrue(form.is_valid(), form.errors)

    def test_decompression_bomb_is_rejected(self):
        with patch("PIL.Image.MAX_IMAGE_PIXELS", 100):
            self.assertEqual(self.upload(image=picture(size=(15, 10))).status_code, 400)
        self.assertFalse(GravePhoto.objects.exists())

    def test_confirm_delete_commit_cleanup_and_audit_survives(self):
        self.upload()
        photo = GravePhoto.objects.get()
        path, photo_id = photo.image.path, photo.pk
        self.assertContains(self.client.get(self.url("photo-delete", photo)), "Czy na pewno")
        self.assertTrue(Path(path).exists())
        self.assertTrue(GravePhoto.objects.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(self.url("photo-delete", photo)).status_code, 302)
        self.assertFalse(Path(path).exists())
        change = RecordChange.objects.get(action="delete")
        self.assertEqual(change.entity_id, photo_id)
        self.assertEqual(change.before["grave_id"], self.grave.pk)
        self.assertEqual(change.editor, self.mod)

    def test_grave_cascade_preview_cleanup_and_history(self):
        self.upload()
        photo = GravePhoto.objects.get()
        path = photo.image.path
        SavedGrave.objects.create(user=self.user, grave=self.grave)
        preview = self.client.get(self.url("moderator-grave-delete"))
        self.assertNotContains(preview, "Nie można usunąć")
        self.assertContains(preview, "wpisy zapisanych grobów (1)")
        grave_id = self.grave.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(self.url("moderator-grave-delete")).status_code, 302)
        self.assertFalse(Path(path).exists())
        self.assertFalse(SavedGrave.objects.exists())
        self.assertFalse(GravePhoto.objects.exists())
        self.assertTrue(RecordChange.objects.filter(entity_type="grave", entity_id=grave_id, action="delete").exists())
        self.assertTrue(RecordChange.objects.filter(entity_type="gravephoto", action="delete").exists())

    def test_rollback_retains_file_and_removes_audit(self):
        self.upload()
        photo = GravePhoto.objects.get()
        path = photo.image.path
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(IntegrityError):
                with audit_changes(self.mod):
                    photo.delete()
                    raise IntegrityError("rollback")
        self.assertTrue(Path(path).exists())
        self.assertTrue(GravePhoto.objects.exists())
        self.assertFalse(RecordChange.objects.filter(action="delete").exists())

    def test_failed_photo_record_or_audit_save_cleans_file(self):
        for target in ("snippets.models.GravePhoto.save", "snippets.models.GravePhoto._do_insert",
                       "snippets.audit.RecordChange.objects.create"):
            if target.endswith("GravePhoto.save"):
                original = GravePhoto.save
                def fail_after_save(instance, *args, **kwargs):
                    original(instance, *args, **kwargs)
                    raise IntegrityError("failed record")
                mock_kwargs = {"new": fail_after_save}
            else:
                mock_kwargs = {"side_effect": IntegrityError("failed audit")}
            with patch(target, **mock_kwargs):
                response = self.upload()
            self.assertEqual(response.status_code, 400)
            self.assertFalse(GravePhoto.objects.exists())
            self.assertFalse(RecordChange.objects.exists())
            self.assertEqual([p for p in Path(self.media.name).rglob("*") if p.is_file()], [])

    def test_audit_crud_foreign_keys_dates_noop_and_direct_orm(self):
        self.assertFalse(RecordChange.objects.exists())
        self.client.force_login(self.mod)
        self.client.post(reverse("moderator-cemetery-edit", args=[self.cemetery.pk]), {"name": "Zmieniony", "address": "Lipowa"})
        change = RecordChange.objects.get()
        self.assertEqual(change.before["name"], "Centralny")
        self.assertEqual(change.after["name"], "Zmieniony")
        self.assertEqual(change.editor, self.mod)
        self.client.post(reverse("moderator-cemetery-edit", args=[self.cemetery.pk]), {"name": "Zmieniony", "address": "Lipowa"})
        self.assertEqual(RecordChange.objects.count(), 1)
        with audit_changes(self.mod):
            person = Deceased.objects.create(name="Jan", surname="Test", birth_date=date(1900, 1, 1), death_date=date(1980, 1, 1))
            burial = Burial.objects.create(grave=self.grave, deceased=person, burial_date=date(1980, 1, 2))
        after = RecordChange.objects.get(entity_type="burial").after
        self.assertEqual(after["burial_date"], "1980-01-02")
        self.assertEqual(after["grave_id"], self.grave.pk)
        with audit_changes(self.mod):
            person.save()  # No field changes, including loaded date objects.
        self.assertEqual(RecordChange.objects.count(), 3)
        self.cemetery.name = "Script"
        self.cemetery.save()
        self.assertEqual(RecordChange.objects.count(), 3)

    def test_guided_creation_audits_each_record_and_rolls_back(self):
        self.client.force_login(self.mod)
        payload = dict(cemetery=self.cemetery.pk, section=self.section.pk, row="2", number="2", occupant="new",
                       name="Jan", surname="Test", birth_date="1900-01-01", death_date="1980-01-01", burial_date="1980-01-02")
        self.assertEqual(self.client.post(reverse("moderator-grave-create"), payload).status_code, 302)
        self.assertEqual(set(RecordChange.objects.values_list("entity_type", flat=True)), {"grave", "deceased", "burial"})
        payload["number"] = "3"
        with patch("snippets.management_forms.Burial.save", side_effect=IntegrityError("failed")):
            self.client.post(reverse("moderator-grave-create"), payload)
        self.assertEqual(RecordChange.objects.count(), 3)
        self.assertFalse(Grave.objects.filter(number="3").exists())

    def test_approval_logs_created_grave_and_rolls_back_on_failure(self):
        submission = CorrectionRequest.objects.create(user=self.user, request_type="missing_grave", proposed_section=self.section,
                       proposed_row="2", proposed_number="3", description="Nowy")
        with patch("snippets.audit.RecordChange.objects.create", side_effect=IntegrityError("audit")):
            with self.assertRaises(IntegrityError):
                review_request(submission.pk, self.mod, "approved", "Dodano")
        submission.refresh_from_db()
        self.assertEqual(submission.status, "pending")
        self.assertFalse(Grave.objects.filter(number="3").exists())
        result = review_request(submission.pk, self.mod, "approved", "Dodano")
        change = RecordChange.objects.get()
        self.assertEqual(change.entity_id, result.resulting_grave_id)
        self.assertEqual(change.editor, self.mod)

    def test_admin_create_edit_noop_delete_bulk_and_readonly_history(self):
        self.client.force_login(self.root)
        self.client.post(reverse("admin:snippets_cemetery_add"), {"name": "Admin", "address": "", "_save": "Save"})
        record = Cemetery.objects.get(name="Admin")
        change_url = reverse("admin:snippets_cemetery_change", args=[record.pk])
        for _ in range(2):
            self.client.post(change_url, {"name": "Admin edit", "address": "", "_save": "Save"})
        self.assertEqual(RecordChange.objects.count(), 2)
        self.client.post(reverse("admin:snippets_cemetery_delete", args=[record.pk]), {"post": "yes"})
        self.assertEqual(RecordChange.objects.count(), 3)
        records = [Cemetery.objects.create(name=f"Bulk {i}") for i in range(2)]
        self.client.post(reverse("admin:snippets_cemetery_changelist"), {"action": "delete_selected", "_selected_action": [r.pk for r in records], "post": "yes"})
        self.assertEqual(RecordChange.objects.filter(action="delete").count(), 3)
        entry = RecordChange.objects.first()
        self.assertEqual(self.client.get(reverse("admin:snippets_recordchange_changelist")).status_code, 200)
        self.assertEqual(self.client.post(reverse("admin:snippets_recordchange_change", args=[entry.pk]), {"record_label": "Tampered"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:snippets_recordchange_delete", args=[entry.pk]), {"post": "yes"}).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin:snippets_recordchange_changelist")).status_code, 403)

    def test_admin_bulk_grave_deletion_audits_cascades_and_cleans_files(self):
        self.upload()
        photo = GravePhoto.objects.get()
        path = photo.image.path
        self.client.force_login(self.root)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("admin:snippets_grave_changelist"), {"action": "delete_selected", "_selected_action": [self.grave.pk], "post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Path(path).exists())
        self.assertEqual(RecordChange.objects.filter(action="delete", editor=self.root).count(), 2)

    def test_history_pagination_filters_and_deleted_record_labels(self):
        with audit_changes(self.mod):
            for i in range(21):
                record = Cemetery.objects.create(name=f"History {i}")
            deleted_id = record.pk
            record.delete()
        self.client.force_login(self.mod)
        response = self.client.get(self.url("record-history"), {"type": "cemetery"})
        self.assertEqual(len(response.context["rows"]), 20)
        self.assertContains(response, "type=cemetery&amp;page=2")
        response = self.client.get(self.url("record-history"), {"type": "cemetery", "action": "delete", "record": deleted_id})
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertContains(response, "History 20")
        self.assertContains(response, "moderator")
        self.assertContains(response, "nazwa")
        self.assertEqual(self.client.get(self.url("record-history"), {"record": "invalid"}).context["paginator"].count, 0)
