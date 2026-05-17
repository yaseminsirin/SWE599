from django.db import migrations, models


def copy_user_emails_to_alert(apps, schema_editor):
    JobAlert = apps.get_model("alerts", "JobAlert")
    for alert in JobAlert.objects.select_related("user").iterator():
        user = getattr(alert, "user", None)
        if user and getattr(user, "email", None) and not alert.notify_email:
            alert.notify_email = user.email
            alert.save(update_fields=["notify_email"])


def drop_authtoken_table(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TABLE IF EXISTS authtoken_token CASCADE;")


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0003_alertdeliverylog"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobalert",
            name="notify_email",
            field=models.EmailField(blank=True, db_index=True, default=""),
            preserve_default=False,
        ),
        migrations.RunPython(copy_user_emails_to_alert, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name="jobalert",
            name="alerts_joba_user_id_7bb6c7_idx",
        ),
        migrations.RemoveIndex(
            model_name="jobalert",
            name="alerts_joba_user_id_99de6b_idx",
        ),
        migrations.RemoveIndex(
            model_name="alertdeliverylog",
            name="alerts_aler_user_id_9d807d_idx",
        ),
        migrations.RemoveField(
            model_name="alertdeliverylog",
            name="user",
        ),
        migrations.RemoveField(
            model_name="jobalert",
            name="user",
        ),
        migrations.AddIndex(
            model_name="jobalert",
            index=models.Index(fields=["is_active"], name="alerts_joba_is_acti_idx"),
        ),
        migrations.AddIndex(
            model_name="jobalert",
            index=models.Index(fields=["-created_at"], name="alerts_joba_created_idx"),
        ),
        migrations.RunPython(drop_authtoken_table, migrations.RunPython.noop),
    ]
