from django.db import migrations


def create_moderators(apps, schema_editor):
    apps.get_model("auth", "Group").objects.using(schema_editor.connection.alias).get_or_create(name="Moderators")


class Migration(migrations.Migration):
    dependencies = [
        ("snippets", "0002_alter_correctionrequest_options_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    operations = [migrations.RunPython(create_moderators, migrations.RunPython.noop)]
