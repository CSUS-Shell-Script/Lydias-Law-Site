from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finances", "0004_invoice_status_and_webhook_event"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="stripe_invoice_number",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
