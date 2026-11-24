from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from snippets.management_forms import GraveCreateForm
from snippets.models import Burial, Cemetery, CorrectionRequest, Deceased, Grave, Section
from snippets.record_management import RECORDS


class RecordManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.create_user("manager")
        cls.moderator.groups.add(Group.objects.get(name="Moderators"))
        cls.superuser = User.objects.create_superuser("root", password="test")
        cls.user = User.objects.create_user("visitor")
        cls.staff = User.objects.create_user("staff", is_staff=True)
        cls.inactive = User.objects.create_user("inactive", is_active=False, is_superuser=True)
        cls.cemetery = Cemetery.objects.create(name="Centralny", address="Lipowa 1")
        cls.section = Section.objects.create(cemetery=cls.cemetery, name="A")
        cls.other = Cemetery.objects.create(name="Inny")
        cls.other_section = Section.objects.create(cemetery=cls.other, name="B")
        cls.grave = Grave.objects.create(section=cls.section, row="1", number="2")
        cls.person = Deceased.objects.create(name="Anna", surname="Kowalska", birth_date="1900-01-01", death_date="1980-01-01")
        cls.burial = Burial.objects.create(grave=cls.grave, deceased=cls.person, burial_date="1980-01-02")

    def setUp(self):
        self.client.force_login(self.moderator)

    def url(self, kind, action, record=None):
        return reverse(f"moderator-{kind}-{action}", args=[record.pk] if record else [])

    def records(self):
        return dict(cemetery=self.cemetery, section=self.section, grave=self.grave,
                    deceased=self.person, burial=self.burial)

    def payload(self, **changes):
        data = dict(cemetery=self.cemetery.pk, section=self.section.pk, row="3", number="4", occupant="none")
        data.update(changes)
        return data

    def test_every_endpoint_checks_roles_for_get_and_post(self):
        endpoints = [(self.url(kind, action, record if action in ("edit", "delete") else None), action)
                     for kind, record in self.records().items() for action in ("list", "create", "edit", "delete")]
        for user, expected in [(None, 302), (self.user, 403), (self.staff, 403), (self.inactive, 302)]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            for url, action in endpoints:
                for method in ("get", "post"):
                    with self.subTest(user=user, url=url, method=method):
                        self.assertEqual(getattr(self.client, method)(url).status_code, expected)
        for user in (self.moderator, self.superuser):
            self.client.force_login(user)
            for url, action in endpoints:
                self.assertEqual(self.client.get(url).status_code, 200)
                if action != "delete":
                    self.assertEqual(self.client.post(url).status_code, 405 if action == "list" else 200)
        self.assertTrue(Burial.objects.filter(pk=self.burial.pk).exists())

    def test_crud_all_five_models(self):
        cases = [
            ("cemetery", dict(name="Nowy", address="Adres"), dict(name="Zmieniony", address="Nowy adres")),
            ("section", dict(cemetery=self.other.pk, name="C"), dict(cemetery=self.other.pk, name="D")),
            ("grave", self.payload(), self.payload(row="9")),
            ("deceased", dict(name="Jan", surname="Nowak", birth_date="1910-01-01", death_date="1990-01-01"),
             dict(name="Janina", surname="Nowak", birth_date="1910-01-01", death_date="1990-01-01")),
            ("burial", dict(deceased=self.person.pk, grave=self.grave.pk, burial_date="1981-01-01"),
             dict(deceased=self.person.pk, grave=self.grave.pk, burial_date="1982-01-01")),
        ]
        for kind, create, edit in cases:
            model = RECORDS[kind][0]
            with self.subTest(kind=kind):
                count = model.objects.count()
                response = self.client.post(self.url(kind, "create"), create)
                record = model.objects.latest("pk")
                self.assertRedirects(response, self.url(kind, "edit", record))
                self.assertEqual(model.objects.count(), count + 1)
                self.assertRedirects(self.client.post(self.url(kind, "edit", record), edit), self.url(kind, "edit", record))
                record.refresh_from_db()
                field = {"grave": "row", "burial": "burial_date"}.get(kind, "name")
                self.assertEqual(str(getattr(record, field)), edit[field])
                self.assertEqual(self.client.get(self.url(kind, "delete", record)).status_code, 200)
                self.assertTrue(model.objects.filter(pk=record.pk).exists())
                self.assertRedirects(self.client.post(self.url(kind, "delete", record)), self.url(kind, "list"))
                self.assertFalse(model.objects.filter(pk=record.pk).exists())

    def test_protected_delete_links_and_never_cascades(self):
        for kind, record, linked_kind, linked in [
            ("cemetery", self.cemetery, "section", self.section),
            ("section", self.section, "grave", self.grave),
            ("grave", self.grave, "burial", self.burial),
            ("deceased", self.person, "burial", self.burial),
        ]:
            for method in ("get", "post"):
                response = getattr(self.client, method)(self.url(kind, "delete", record))
                self.assertContains(response, "Nie można usunąć")
                self.assertContains(response, self.url(linked_kind, "edit", linked))
                self.assertTrue(type(record).objects.filter(pk=record.pk).exists())
        self.assertEqual(Burial.objects.count(), 1)
        self.burial.delete()
        submission = CorrectionRequest.objects.create(user=self.user, grave=self.grave, description="Poprawka")
        response = self.client.post(self.url("grave", "delete", self.grave))
        self.assertContains(response, reverse("moderator-request-detail", args=[submission.pk]))

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.moderator)
        for kind, record in self.records().items():
            for action in ("create", "edit", "delete"):
                self.assertEqual(client.post(self.url(kind, action, record if action != "create" else None)).status_code, 403)

    def test_guided_three_choices_and_additional_occupant(self):
        for mode in ("none", "existing", "new"):
            response = self.client.post(self.url("grave", "create"), self.payload(
                number=mode, occupant=mode, deceased=self.person.pk, name="Jan", surname="Nowak",
                birth_date="1901-01-01", death_date="1981-01-01", burial_date="1982-01-01"))
            grave = Grave.objects.get(number=mode)
            self.assertRedirects(response, self.url("grave", "edit", grave))
            self.assertEqual(grave.burials.count(), 0 if mode == "none" else 1)
            if mode == "new":
                self.assertEqual(grave.burials.get().deceased.name, "Jan")
            add_url = self.url("burial", "create") + f"?grave={grave.pk}"
            self.assertContains(self.client.get(response.url), add_url)
            self.assertEqual(self.client.get(add_url).context["form"]["grave"].value(), grave.pk)
        response = self.client.post(add_url, dict(grave=grave.pk, deceased=self.person.pk, burial_date="1983-01-01"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(grave.burials.count(), 2)

    def test_guided_invalid_keeps_values_and_creates_nothing(self):
        for changes, field in [
            (dict(occupant="existing", deceased=self.person.pk), "burial_date"),
            (dict(occupant="new", surname="Nowak"), "name"),
            (dict(occupant="new", name="Jan", surname="Nowak", birth_date="2000-01-01", death_date="1990-01-01", burial_date="1991-01-01"), "death_date"),
            (dict(occupant="existing", deceased=self.person.pk, burial_date="1979-01-01"), "burial_date"),
            (dict(section=self.other_section.pk), "section"),
            (dict(row="1", number="2"), "__all__"),
        ]:
            response = self.client.post(self.url("grave", "create"), self.payload(**changes))
            self.assertIn(field, response.context["form"].errors)
            self.assertEqual(response.context["form"]["row"].value(), changes.get("row", "3"))
            self.assertEqual((Grave.objects.count(), Deceased.objects.count(), Burial.objects.count()), (1, 1, 1))

    def test_atomic_rollback_when_burial_save_fails(self):
        data = self.payload(occupant="new", name="Jan", surname="Nowak", birth_date="1900-01-01",
                            death_date="1980-01-01", burial_date="1981-01-01")
        for error in (IntegrityError("conflict"), ValidationError("Data zmieniona")):
            with patch("snippets.management_forms.Burial.save", side_effect=error):
                response = self.client.post(self.url("grave", "create"), data)
            self.assertTrue(response.context["form"].non_field_errors())
            self.assertEqual((Grave.objects.count(), Deceased.objects.count(), Burial.objects.count()), (1, 1, 1))

    def test_model_validation_and_grave_edit_does_not_change_people(self):
        response = self.client.post(self.url("section", "create"), dict(cemetery=self.cemetery.pk, name=" A "))
        self.assertTrue(response.context["form"].errors)
        response = self.client.post(self.url("deceased", "edit", self.person), dict(
            name="Anna", surname="Kowalska", birth_date="1900-01-01", death_date="1981-01-01"))
        self.assertIn("death_date", response.context["form"].errors)
        response = self.client.post(self.url("burial", "edit", self.burial), dict(
            deceased=self.person.pk, grave=self.grave.pk, burial_date="1970-01-01"))
        self.assertIn("burial_date", response.context["form"].errors)
        response = self.client.post(self.url("grave", "edit", self.grave), self.payload(
            occupant="new", name="Injected", surname="Person", birth_date="1900-01-01", death_date="1980-01-01"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Deceased.objects.count(), 1)
        self.assertEqual(Burial.objects.count(), 1)
        self.assertFalse(GraveCreateForm(self.payload(occupant="invalid")).is_valid())

    def test_lists_search_filter_empty_and_pagination(self):
        for kind, q in [("cemetery", "Lipowa"), ("section", "Centralny A"), ("grave", "Centralny 2"),
                        ("deceased", "Kowalska Anna"), ("burial", "Kowalska Centralny")]:
            response = self.client.get(self.url(kind, "list"), dict(q=q))
            self.assertEqual(response.context["paginator"].count, 1)
            self.assertContains(self.client.get(self.url(kind, "list"), dict(q="ZZZ")), "Brak rekordów")
        for kind in ("section", "grave", "burial"):
            response = self.client.get(self.url(kind, "list"), dict(cemetery=self.cemetery.pk))
            self.assertEqual(response.context["paginator"].count, 1)
            response = self.client.get(self.url(kind, "list"), dict(cemetery="invalid"))
            self.assertTrue(response.context["form"].errors)
            self.assertEqual(response.context["paginator"].count, 0)
        for i in range(22):
            Grave.objects.create(section=self.section, row="Page", number=str(i))
        response = self.client.get(self.url("grave", "list"), dict(q="Page", cemetery=self.cemetery.pk))
        self.assertEqual(len(response.context["rows"]), 20)
        self.assertContains(response, f'q=Page&amp;cemetery={self.cemetery.pk}&amp;page=2')
        response = self.client.get(self.url("grave", "list"), dict(q="Page", cemetery=self.cemetery.pk, page=2))
        self.assertEqual(len(response.context["rows"]), 2)

    def test_links_only_for_moderators_and_corrections_stay_manual(self):
        submission = CorrectionRequest.objects.create(user=self.user, grave=self.grave, description="Poprawka")
        for user, visible in [(self.user, False), (self.staff, False), (self.moderator, True), (self.superuser, True)]:
            self.client.force_login(user)
            for kind, record in [("cemetery", self.cemetery), ("grave", self.grave), ("deceased", self.person)]:
                response = self.client.get(record.get_absolute_url())
                if visible:
                    self.assertContains(response, self.url(kind, "edit", record))
                else:
                    self.assertNotContains(response, self.url(kind, "edit", record))
        self.client.force_login(self.moderator)
        response = self.client.get(reverse("moderator-request-detail", args=[submission.pk]))
        self.assertContains(response, self.url("grave", "edit", self.grave))
        self.client.post(self.url("grave", "edit", self.grave), self.payload())
        submission.refresh_from_db()
        self.assertEqual(submission.status, "pending")
        self.assertEqual(submission.admin_response, "")
