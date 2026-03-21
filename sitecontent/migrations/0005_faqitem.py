from django.db import migrations, models
import django_ckeditor_5.fields


def seed_initial_faqs(apps, schema_editor):
    FAQItem = apps.get_model("sitecontent", "FAQItem")
    if FAQItem.objects.exists():
        return

    seed_data = [
        (
            "How long is the adoption process?",
            "The adoption process can vary depending on the type of adoption. Foster care adoption tends to be the least lengthy at between 6 to 18 months. Domestic infant adoption can take from 9 to 12 months or even a couple of years. The lengthiest is usually international adoption, which can take multiple years to finalize.",
            1,
        ),
        (
            "What is the cost of adopting? Do I need a lawyer?",
            "The cost of adoption can vary depending on the type-private, agency, or independent. A lawyer helps ensure all legal requirements are met and protects your rights throughout the process.",
            2,
        ),
        (
            "What is the difference between adoption and guardianship?",
            "Adoption permanently transfers parental rights to the adoptive parent, while guardianship is typically temporary and can be ended by the court. Adoption creates a lifelong legal parent-child relationship; guardianship does not.",
            3,
        ),
        (
            "What are the different types of adoptions?",
            "Common types include agency, independent (private), stepparent, relative (kinship), and international adoptions. Each has its own legal process, requirements, and level of court involvement.",
            4,
        ),
    ]

    for question, answer, display_order in seed_data:
        FAQItem.objects.create(
            question=question,
            answer=f"<p>{answer}</p>",
            display_order=display_order,
            is_active=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("sitecontent", "0004_delete_article_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="FAQItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question", models.CharField(blank=True, max_length=255)),
                ("answer", django_ckeditor_5.fields.CKEditor5Field(blank=True)),
                ("display_order", models.PositiveIntegerField(db_index=True, default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["display_order", "id"]},
        ),
        migrations.RunPython(seed_initial_faqs, migrations.RunPython.noop),
    ]
