from django.db import migrations, models
import django_ckeditor_5.fields


def copy_practice_areas_to_items(apps, schema_editor):
    WebsiteContent = apps.get_model('sitecontent', 'WebsiteContent')
    PracticeAreaItem = apps.get_model('sitecontent', 'PracticeAreaItem')

    content = WebsiteContent.objects.order_by('-versionNumber').first()
    if not content:
        return

    areas = [
        (1, 'Step-Parent Adoption',      content.stepParentAdoptionDescription),
        (2, 'Adult Adoption',             content.adultAdoptionDescription),
        (3, 'Guardianship',               content.guardianshipDescription),
        (4, 'Guardianship to Adoption',   content.guardianshipToAdoptionDescription),
        (5, 'Independent Adoption',       content.independentAdoptionDescription),
    ]

    for order, title, description in areas:
        PracticeAreaItem.objects.create(
            title=title,
            description=description or '',
            display_order=order,
            is_active=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('sitecontent', '0005_faqitem'),
    ]

    operations = [
        migrations.CreateModel(
            name='PracticeAreaItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, max_length=255)),
                ('description', django_ckeditor_5.fields.CKEditor5Field(blank=True, config_name='default')),
                ('display_order', models.PositiveIntegerField(db_index=True, default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['display_order', 'id'],
            },
        ),
        # Copy existing descriptions into PracticeAreaItem rows before dropping columns
        migrations.RunPython(copy_practice_areas_to_items, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='websitecontent',
            name='stepParentAdoptionDescription',
        ),
        migrations.RemoveField(
            model_name='websitecontent',
            name='adultAdoptionDescription',
        ),
        migrations.RemoveField(
            model_name='websitecontent',
            name='guardianshipDescription',
        ),
        migrations.RemoveField(
            model_name='websitecontent',
            name='guardianshipToAdoptionDescription',
        ),
        migrations.RemoveField(
            model_name='websitecontent',
            name='independentAdoptionDescription',
        ),
    ]
