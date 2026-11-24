from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from snippets.models import Burial, Cemetery, CorrectionRequest, Deceased, Grave, Section
from snippets.moderation import ReviewConflict, review_request


class RequestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("owner")
        cls.other = User.objects.create_user("other")
        cls.moderator = User.objects.create_user("moderator")
        cls.moderator.groups.add(Group.objects.get(name="Moderators"))
        cls.superuser = User.objects.create_superuser("root", password="test")
        cls.staff = User.objects.create_user("staff", is_staff=True)
        cls.inactive = User.objects.create_user("inactive", is_active=False)
        cls.inactive.groups.add(Group.objects.get(name="Moderators"))
        cls.cemetery = Cemetery.objects.create(name="Cmentarz testowy")
        cls.section = Section.objects.create(cemetery=cls.cemetery, name="A")
        cls.foreign_section = Section.objects.create(cemetery=Cemetery.objects.create(name="Inny"), name="B")
        cls.grave = Grave.objects.create(section=cls.section, row="1", number="1")
        cls.deceased = Deceased.objects.create(name="Jan", surname="Kowalski", birth_date="1900-01-01", death_date="1980-01-01")

    def missing(self, **kwargs):
        fields = dict(user=self.user, request_type="missing_grave", proposed_section=self.section,
                      proposed_row="2", proposed_number="3", description="Brakujący grób")
        fields.update(kwargs)
        return CorrectionRequest.objects.create(**fields)

    def correction(self, **kwargs):
        fields = dict(user=self.user, grave=self.grave, description="Poprawka")
        fields.update(kwargs)
        return CorrectionRequest.objects.create(**fields)

    def payload(self, **kwargs):
        fields = dict(cemetery=self.cemetery.pk, proposed_section=self.section.pk,
                      proposed_row=" 2 ", proposed_number=" 3 ", description=" Opis ")
        fields.update(kwargs)
        return fields

    def test_guests_redirect_through_login(self):
        submission = self.missing()
        for url in [reverse("missing-grave-create"), reverse("request-list"), submission.get_absolute_url(),
                    reverse("request-create", args=["grave", self.grave.pk]), reverse("moderator-dashboard"),
                    reverse("moderator-request-detail", args=[submission.pk])]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, reverse("login") + "?next=" + url)

    def test_moderator_access(self):
        submission = self.missing()
        urls = [reverse("moderator-dashboard"), reverse("moderator-request-detail", args=[submission.pk])]
        for user, expected in [(self.user, 403), (self.staff, 403), (self.moderator, 200), (self.superuser, 200)]:
            self.client.force_login(user)
            for url in urls:
                with self.subTest(user=user, url=url):
                    self.assertEqual(self.client.get(url).status_code, expected)
        self.client.force_login(self.inactive)
        self.assertEqual(self.client.get(urls[0]).status_code, 302)
        with self.assertRaises(PermissionDenied):
            review_request(submission.pk, self.inactive, "approved", "Tak")

    def test_personal_ownership_for_both_types_even_for_superuser(self):
        for submission in [self.missing(), self.correction()]:
            self.client.force_login(self.user)
            self.assertContains(self.client.get(submission.get_absolute_url()), submission.description)
            for user in [self.other, self.moderator, self.superuser]:
                self.client.force_login(user)
                self.assertEqual(self.client.get(submission.get_absolute_url()).status_code, 404)
                self.assertNotContains(self.client.get(reverse("request-list")), f"Zgłoszenie #{submission.pk}")

    def test_submission_trims_and_ignores_protected_fields(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("missing-grave-create"), self.payload(
            user=self.other.pk, status="approved", request_type="correction", grave=self.grave.pk,
            deceased=self.deceased.pk, resulting_grave=self.grave.pk, reviewed_by=self.moderator.pk,
            reviewed_at=timezone.now().isoformat(), admin_response="Forged",
        ))
        submission = CorrectionRequest.objects.get()
        self.assertRedirects(response, submission.get_absolute_url())
        self.assertEqual((submission.proposed_row, submission.proposed_number, submission.description), ("2", "3", "Opis"))
        self.assertEqual(submission.user, self.user)
        self.assertEqual(submission.request_type, "missing_grave")
        self.assertEqual(submission.status, "pending")
        self.assertIsNone(submission.grave)
        self.assertIsNone(submission.deceased)
        self.assertIsNone(submission.resulting_grave)
        self.assertIsNone(submission.reviewed_by)
        self.assertIsNone(submission.reviewed_at)
        self.assertEqual(submission.admin_response, "")
        self.assertEqual(Grave.objects.count(), 1)

    def test_missing_fields_and_mismatched_location(self):
        self.client.force_login(self.user)
        for field in ["cemetery", "proposed_section", "proposed_row", "proposed_number", "description"]:
            response = self.client.post(reverse("missing-grave-create"), self.payload(**{field: " "}))
            self.assertEqual(response.status_code, 200)
            self.assertIn(field, response.context["form"].errors)
        response = self.client.post(reverse("missing-grave-create"), self.payload(proposed_section=self.foreign_section.pk))
        self.assertFormError(response, "form", "proposed_section", "Sektor nie należy do wybranego cmentarza.")
        self.assertEqual(CorrectionRequest.objects.count(), 0)

    def test_duplicate_submission_links_existing_grave(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("missing-grave-create"), self.payload(proposed_row=" 1 ", proposed_number="1"))
        self.assertContains(response, "już istnieje")
        self.assertContains(response, self.grave.get_absolute_url())
        self.assertEqual(CorrectionRequest.objects.count(), 0)

    def test_cemetery_preselection_and_navigation(self):
        self.assertContains(self.client.get(reverse("home")), reverse("missing-grave-create"))
        response = self.client.get(self.cemetery.get_absolute_url())
        self.assertContains(response, reverse("missing-grave-create") + f"?cemetery={self.cemetery.pk}")
        self.client.force_login(self.user)
        response = self.client.get(reverse("missing-grave-create"), {"cemetery": self.cemetery.pk})
        self.assertEqual(response.context["form"]["cemetery"].value(), str(self.cemetery.pk))
        self.assertNotContains(self.client.get(reverse("home")), reverse("moderator-dashboard"))
        self.client.force_login(self.moderator)
        self.assertContains(self.client.get(reverse("home")), reverse("moderator-dashboard"))

    def test_correction_submission_still_works_and_is_protected(self):
        self.client.force_login(self.user)
        for kind, target in [("grave", self.grave), ("deceased", self.deceased)]:
            response = self.client.post(reverse("request-create", args=[kind, target.pk]), {
                "description": "Nowe dane", "status": "approved", "user": self.other.pk,
                "request_type": "missing_grave", "admin_response": "Forged",
            })
            submission = CorrectionRequest.objects.latest("pk")
            self.assertRedirects(response, submission.get_absolute_url())
            self.assertEqual(submission.target, target)
            self.assertEqual(submission.request_type, "correction")
            self.assertEqual(submission.status, "pending")
            self.assertEqual(submission.user, self.user)

    def test_approval_creates_one_grave_and_metadata(self):
        submission = self.missing()
        self.client.force_login(self.moderator)
        url = reverse("moderator-request-detail", args=[submission.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(Grave.objects.count(), 1)
        response = self.client.post(url, {"decision": "approved", "admin_response": " Potwierdzono "})
        self.assertRedirects(response, url)
        submission.refresh_from_db()
        result = submission.resulting_grave
        self.assertEqual((result.section, result.row, result.number), (self.section, "2", "3"))
        self.assertEqual(submission.status, "approved")
        self.assertEqual(submission.reviewed_by, self.moderator)
        self.assertIsNotNone(submission.reviewed_at)
        self.assertEqual(submission.admin_response, "Potwierdzono")
        for decision in ["approved", "rejected"]:
            response = self.client.post(url, {"decision": decision, "admin_response": "Zmieniono"})
            self.assertContains(response, "już rozpatrzone")
        submission.refresh_from_db()
        self.assertEqual(submission.status, "approved")
        self.assertEqual(submission.admin_response, "Potwierdzono")
        self.assertEqual(Grave.objects.count(), 2)
        self.assertEqual(Burial.objects.count(), 0)
        self.assertEqual(Deceased.objects.count(), 1)
        self.client.force_login(self.user)
        response = self.client.get(submission.get_absolute_url())
        self.assertContains(response, result.get_absolute_url())
        self.assertContains(response, self.moderator.username)
        self.assertContains(response, "Potwierdzono")

    def test_rejection_and_corrections_do_not_create_records(self):
        for submission, decision in [(self.missing(), "rejected"), (self.correction(), "approved"),
                                     (self.correction(deceased=self.deceased, grave=None), "rejected")]:
            review_request(submission.pk, self.moderator, decision, "Odpowiedź")
            submission.refresh_from_db()
            self.assertEqual(submission.status, decision)
            self.assertIsNone(submission.resulting_grave)
            self.assertEqual(submission.reviewed_by, self.moderator)
        self.assertEqual(Grave.objects.count(), 1)
        self.assertEqual(Burial.objects.count(), 0)
        self.assertEqual(Deceased.objects.count(), 1)

    def test_review_requires_response_and_valid_decision(self):
        submission = self.missing()
        self.client.force_login(self.moderator)
        for payload in [{"decision": "approved", "admin_response": " "},
                        {"decision": "pending", "admin_response": "Opis"},
                        {"decision": "rejected", "admin_response": "x" * 4001}]:
            response = self.client.post(reverse("moderator-request-detail", args=[submission.pk]), payload)
            self.assertTrue(response.context["form"].errors)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "pending")
        self.assertIsNone(submission.reviewed_by)

    def test_approval_rechecks_duplicate_and_rolls_back_review(self):
        submission = self.missing()
        existing = Grave.objects.create(section=self.section, row="2", number="3")
        self.client.force_login(self.moderator)
        response = self.client.post(reverse("moderator-request-detail", args=[submission.pk]), {
            "decision": "approved", "admin_response": "Tak",
        })
        self.assertContains(response, "pozostaje oczekujące")
        self.assertContains(response, existing.get_absolute_url())
        submission.refresh_from_db()
        self.assertEqual(submission.status, "pending")
        self.assertEqual(submission.admin_response, "")
        self.assertIsNone(submission.reviewed_by)
        self.assertIsNone(submission.reviewed_at)
        self.assertIsNone(submission.resulting_grave)
        review_request(submission.pk, self.moderator, "rejected", "Duplikat")
        self.assertEqual(Grave.objects.count(), 2)

    def test_two_pending_requests_for_same_location(self):
        first, second = self.missing(), self.missing()
        review_request(first.pk, self.moderator, "approved", "Tak")
        with self.assertRaises(ReviewConflict):
            review_request(second.pk, self.moderator, "approved", "Tak")
        second.refresh_from_db()
        self.assertEqual(second.status, "pending")
        self.assertEqual(Grave.objects.count(), 2)

    def test_dashboard_counts_filters_order_and_pagination(self):
        CorrectionRequest.objects.all().delete()
        first = self.missing()
        for i in range(21):
            self.missing(proposed_number=str(i + 10))
        self.correction()
        approved = self.correction(status="approved")
        self.correction(status="rejected")
        CorrectionRequest.objects.filter(pk=approved.pk).update(created_at=timezone.now() - timedelta(days=8))
        self.client.force_login(self.moderator)
        url = reverse("moderator-dashboard")
        response = self.client.get(url)
        self.assertEqual(response.context["stats"], dict(total=25, pending=23, approved=1, rejected=1, recent=24))
        self.assertEqual(response.context["object_list"][0], first)
        self.assertEqual(len(response.context["object_list"]), 20)
        self.assertContains(response, "status=pending&amp;page=2")
        response = self.client.get(url, {"status": "pending", "request_type": "missing_grave", "page": 2})
        self.assertEqual(len(response.context["object_list"]), 2)
        self.assertContains(response, "status=pending&amp;request_type=missing_grave&amp;page=1")
        self.assertEqual(response.context["stats"]["total"], 25)
        response = self.client.get(url, {"status": "", "request_type": "correction"})
        self.assertEqual(len(response.context["object_list"]), 3)
        response = self.client.get(url, {"status": "approved"})
        self.assertEqual(list(response.context["object_list"]), [approved])
        response = self.client.get(url, {"status": "rejected", "request_type": "missing_grave"})
        self.assertContains(response, "Nie ma zgłoszeń")
        response = self.client.get(url, {"status": "invalid"})
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(len(response.context["object_list"]), 0)

    def test_database_target_constraints(self):
        for fields in [dict(user=self.user, description="Bad"),
                       dict(user=self.user, description="Bad", deceased=self.deceased, grave=self.grave),
                       dict(user=self.user, description="Bad", request_type="missing_grave", proposed_section=self.section),
                       dict(user=self.user, description="Bad", grave=self.grave, proposed_row="2"),
                       dict(user=self.user, description="Bad", request_type="missing_grave", proposed_section=self.section,
                            proposed_row="2", proposed_number="3", status="approved")]:
            with self.subTest(fields=fields), self.assertRaises(IntegrityError), transaction.atomic():
                CorrectionRequest.objects.create(**fields)

    def test_admin_cannot_bypass_decisions(self):
        submission = self.missing()
        self.client.force_login(self.superuser)
        url = reverse("admin:snippets_correctionrequest_change", args=[submission.pk])
        response = self.client.get(url)
        self.assertContains(response, reverse("moderator-request-detail", args=[submission.pk]))
        self.client.post(url, {"status": "approved", "admin_response": "Forged", "_save": "Zapisz"})
        submission.refresh_from_db()
        self.assertEqual(submission.status, "pending")
        self.assertEqual(submission.admin_response, "")
        self.assertIsNone(submission.resulting_grave)
        model_admin = admin.site._registry[CorrectionRequest]
        self.assertIn("status", model_admin.readonly_fields)
        self.assertIn("reviewed_by", model_admin.readonly_fields)


class ConcurrentReviewTests(TransactionTestCase):
    def test_concurrent_reviews_create_exactly_one_grave(self):
        if connection.vendor == "sqlite" and connection.is_in_memory_db():
            self.skipTest("SQLite shared-memory tables use immediate table locks; run with a file-backed test database.")
        user = User.objects.create_user("owner")
        moderator = User.objects.create_user("reviewer")
        group, _ = Group.objects.get_or_create(name="Moderators")
        moderator.groups.add(group)
        cemetery = Cemetery.objects.create(name="Test")
        section = Section.objects.create(cemetery=cemetery, name="A")
        submission = CorrectionRequest.objects.create(user=user, request_type="missing_grave",
            proposed_section=section, proposed_row="1", proposed_number="1", description="Opis")
        barrier = Barrier(2)

        def decide():
            close_old_connections()
            try:
                reviewer = User.objects.get(pk=moderator.pk)
                barrier.wait(timeout=10)
                try:
                    review_request(submission.pk, reviewer, "approved", "Tak")
                    return "approved"
                except ReviewConflict:
                    return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: decide(), range(2)))
        self.assertCountEqual(outcomes, ["approved", "conflict"])
        self.assertEqual(Grave.objects.count(), 1)
        submission.refresh_from_db()
        self.assertEqual(submission.resulting_grave, Grave.objects.get())
        self.assertEqual(submission.status, "approved")
