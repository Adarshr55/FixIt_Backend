from django.db.models import Avg

def update_service_rating(provider_service):
    """
    Recalculate and save ProviderService.service_rating.
    Called after every new review is created.
    Uses DB average — accurate and race-condition safe.
    """
    from .models import Review

    avg=Review.objects.filter(
        service=provider_service
    ).aggregate( avg_rating=Avg('rating'))['avg_rating']

    provider_service.service_rating = round(avg or 0, 2)
    provider_service.save(update_fields=['service_rating', 'updated_at'])

def update_provider_overall_rating(provider_profile):
    from .models import Review

    avg = Review.objects.filter(
        provider=provider_profile
    ).aggregate(
        avg_rating=Avg('rating')  # ← 'rating' not 'service_rating'
    )['avg_rating']

    provider_profile.overall_rating = round(avg or 0, 2)
    provider_profile.save(update_fields=['overall_rating', 'updated_at'])

def check_and_flag_provider(provider_profile):
    """
    Auto-flag provider if they have 3+ fraud reports in 30 days.
    Called after every new Report is created.
    """
    from .models        import Report
    from django.utils   import timezone
    from datetime       import timedelta

    thirty_days_ago = timezone.now() - timedelta(days=30)

    fraud_count = Report.objects.filter(
        provider   = provider_profile,
        reason     = 'fraud',
        created_at__gte = thirty_days_ago,
    ).count()

    if fraud_count >= 3:
        # Notify admin about this provider
        from notifications.services import notify
        from accounts.models         import User

        admins = User.objects.filter(role='admin', is_active=True)
        for admin in admins:
            notify(
                user              = admin,
                notification_type = 'provider_flagged',
                title             = 'Provider Auto-Flagged',
                message           = (
                    f'{provider_profile.full_name} has received '
                    f'{fraud_count} fraud reports in the last 30 days. '
                    f'Please review immediately.'
                ),
            )
