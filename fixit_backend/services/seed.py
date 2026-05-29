from services.models import ServiceCategory


def seed():
    categories = [
        {
            "name": "Electrician",
            "group": "home",
            "icon": "⚡",
            "skill_tags": [
                "Wiring", "Switchboard Repair", "Fan Installation",
                "Short Circuit Fix", "Solar Panel", "MCB/DB Work",
                "Light Fitting", "Inverter/UPS Setup"
            ]
        },
        {
            "name": "Plumber",
            "group": "home",
            "icon": "🔧",
            "skill_tags": [
                "Pipe Fitting", "Tap Repair", "Water Tank Repair",
                "Drain Cleaning", "Geyser Fix", "Bathroom Fitting",
                "Overhead Tank", "Motor Pump Repair"
            ]
        },
        {
            "name": "Bike Mechanic",
            "group": "automotive",
            "icon": "🏍️",
            "skill_tags": [
                "Engine Repair", "Oil Change", "Brake Repair",
                "Chain Replacement", "Tyre Puncture", "Battery Replacement"
            ]
        },
        {
            "name": "Towing",
            "group": "automotive",
            "icon": "🚛",
            "skill_tags": [
                "Bike Towing", "Car Towing", "Flatbed Towing",
                "Highway Rescue", "Accident Recovery"
            ]
        },
    ]

    created = 0
    skipped = 0

    for data in categories:
        obj, was_created = ServiceCategory.objects.get_or_create(
            name=data["name"],
            defaults={
                "group": data["group"],
                "icon": data["icon"],
                "skill_tags": data["skill_tags"],
            }
        )
        if was_created:
            created += 1
        else:
            skipped += 1

    print("Seeding complete.")
    print(f"Created: {created}")
    print(f"Skipped: {skipped}")