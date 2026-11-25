from django.db import migrations


# Old role value  ->  new sub_role value
# role becomes 'admin' for all of these.
OLD_TO_SUB = {
    'exam_admin': 'exam_admin',
    'accounts_admin': 'accounts_admin',
    'academic_admin': 'academic_admin',
    'iqac_admin': 'iqac_admin',
}


def forwards(apps, schema_editor):
    User = apps.get_model('users', 'User')
    for old_role, sub in OLD_TO_SUB.items():
        User.objects.filter(role=old_role).update(role='admin', sub_role=sub)


def backwards(apps, schema_editor):
    # reverse: put the sub_role value back into role, clear sub_role
    User = apps.get_model('users', 'User')
    for old_role, sub in OLD_TO_SUB.items():
        User.objects.filter(role='admin', sub_role=sub).update(role=old_role, sub_role=None)


class Migration(migrations.Migration):

    dependencies = [
        # this must match your latest users migration (the 0012 one you just applied)
        ('users', '0012_parentprofile_occupation_parentprofile_phone_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]