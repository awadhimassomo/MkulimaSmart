from django.db import migrations, models


def clean_emails(apps, schema_editor):
    """
    Blank emails become NULL and the rest are lower-cased. Email is about to become the sign-in
    identifier and unique, but the old column allowed repeats, so when several accounts share one
    address the oldest account keeps it and the others are set to NULL. Nobody is deleted, and each
    account that loses its address is printed so it can be fixed by hand.
    """
    User = apps.get_model("website", "User")
    seen = {}
    for user_id, current_email in User.objects.exclude(email__isnull=True).order_by("pk").values_list("pk", "email"):
        email = (current_email or "").strip().lower()
        if email and email in seen:
            print(f"\n  email {email!r}: account {user_id} loses it (account {seen[email]} keeps it)")
            email = ""
        elif email:
            seen[email] = user_id
        if (email or None) != current_email:
            User.objects.filter(pk=user_id).update(email=email or None)


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0006_seed_supplier_categories"),
    ]

    operations = [
        # The column must accept NULL before blank emails can be turned into NULL, and it cannot be
        # unique while several blanks or repeats still exist, so: nullable first, clean the data, then unique.
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True, verbose_name="Email Address"),
        ),
        migrations.RunPython(clean_emails, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True, unique=True, verbose_name="Email Address"),
        ),
        migrations.AlterField(
            model_name="user",
            name="phone_number",
            field=models.CharField(blank=True, max_length=15, null=True, unique=True, verbose_name="Phone Number"),
        ),
    ]
