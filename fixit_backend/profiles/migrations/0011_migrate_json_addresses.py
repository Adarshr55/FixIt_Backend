from django.db import migrations

def migrate_addresses(apps, schema_editor):
    CustomerProfile = apps.get_model('profiles', 'CustomerProfile')
    CustomerAddress = apps.get_model('profiles', 'CustomerAddress')

    for profile in CustomerProfile.objects.all():
        saved = profile.saved_addresses
        if isinstance(saved, list):
            for idx, item in enumerate(saved):
                if isinstance(item, dict) and 'address' in item:
                    # Handle both 'latitude'/'longitude' and standard 'lat'/'lng'
                    lat = item.get('latitude') or item.get('lat')
                    lng = item.get('longitude') or item.get('lng')
                    
                    CustomerAddress.objects.create(
                        customer=profile,
                        label=item.get('label', 'Other') or 'Other',
                        address=item.get('address'),
                        latitude=lat,
                        longitude=lng,
                        is_default=(idx == 0)
                    )

def rollback_addresses(apps, schema_editor):
    CustomerAddress = apps.get_model('profiles', 'CustomerAddress')
    CustomerAddress.objects.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0010_customeraddress'),
    ]

    operations = [
        migrations.RunPython(migrate_addresses, rollback_addresses),
    ]
