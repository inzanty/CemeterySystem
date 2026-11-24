from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RequestMigrationTests(TransactionTestCase):
    def test_preserves_existing_corrections_ids_targets_statuses_and_responses(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([("snippets", "0001_initial")])
            old = executor.loader.project_state([("snippets", "0001_initial")]).apps
            user = old.get_model("auth", "User").objects.create(username="legacy")
            cemetery = old.get_model("snippets", "Cemetery").objects.create(name="Legacy")
            section = old.get_model("snippets", "Section").objects.create(cemetery=cemetery, name="A")
            grave = old.get_model("snippets", "Grave").objects.create(section=section, row="1", number="1")
            deceased = old.get_model("snippets", "Deceased").objects.create(
                name="Jan", surname="Test", birth_date="1900-01-01", death_date="1980-01-01")
            ids = []
            for status in ["pending", "approved", "rejected"]:
                item = old.get_model("snippets", "CorrectionRequest").objects.create(
                    user=user, grave=grave if status == "pending" else None,
                    deceased=deceased if status != "pending" else None,
                    description=f"Opis {status}", status=status,
                    admin_response="Historyczna odpowiedź" if status != "pending" else "")
                ids.append((item.pk, item.created_at, item.updated_at, status))
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            for model_name in ("RecordChange", "GravePhoto", "SavedGrave"):
                self.assertEqual(apps.get_model("snippets", model_name).objects.count(), 0)
            Request = apps.get_model("snippets", "CorrectionRequest")
            for pk, created, updated, status in ids:
                item = Request.objects.get(pk=pk)
                self.assertEqual(item.request_type, "correction")
                self.assertEqual(item.status, status)
                self.assertEqual(item.description, f"Opis {status}")
                self.assertEqual(item.created_at, created)
                self.assertEqual(item.updated_at, updated)
                self.assertEqual(item.user_id, user.pk)
                self.assertEqual(item.grave_id, grave.pk if status == "pending" else None)
                self.assertEqual(item.deceased_id, deceased.pk if status != "pending" else None)
                self.assertIsNone(item.reviewed_by_id)
                self.assertIsNone(item.reviewed_at)
                self.assertEqual(item.admin_response, "Historyczna odpowiedź" if status != "pending" else "")
            self.assertTrue(apps.get_model("auth", "Group").objects.filter(name="Moderators").exists())
            with self.assertRaises(IntegrityError), transaction.atomic():
                Request.objects.create(user_id=user.pk, description="Brak celu")
            Request.objects.create(user_id=user.pk, request_type="missing_grave", description="Nowy",
                proposed_section_id=section.pk, proposed_row="2", proposed_number="2")
        finally:
            MigrationExecutor(connection).migrate(latest)
