from django.db import migrations


PRACTICE_AREAS = [
    (1, 'Step-Parent Adoption'),
    (2, 'Adult Adoption'),
    (3, 'Guardianship'),
    (4, 'Guardianship to Adoption'),
    (5, 'Independent Adoption'),
]


def seed_practice_areas(apps, schema_editor):
    PracticeAreaItem = apps.get_model('sitecontent', 'PracticeAreaItem')
    # Only seed if the table is empty (don't overwrite existing data)
    if PracticeAreaItem.objects.exists():
        return
    for order, title in PRACTICE_AREAS:
        PracticeAreaItem.objects.create(
            title=title,
            description='',
            display_order=order,
            is_active=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('sitecontent', '0006_practiceareaitem_remove_websitecontent_practice_fields'),
    ]

    operations = [
        migrations.RunPython(seed_practice_areas, migrations.RunPython.noop),
    ]
