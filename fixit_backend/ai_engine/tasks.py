"""
Celery tasks for AI Engine.
These run on a schedule, not triggered by user actions.
"""

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3)
def run_nightly_fraud_scan(self):
    """
    Runs fraud detection on all active providers.
    Schedule: every night at 2am.
    Notifies admins of any new high-risk providers found.
    """
    from profiles.models import ProviderProfile
    from notifications.services import notify
    from accounts.models import User
    from .fraud_detection import run_full_provider_fraud_check

    try:
        providers = ProviderProfile.objects.filter(
            approval_status='approved'
        ).select_related('user')

        high_risk = []
        critical  = []

        for provider in providers:
            result = run_full_provider_fraud_check(provider)

            if result['overall_risk'] == 'critical':
                critical.append(result)
            elif result['overall_risk'] == 'high':
                high_risk.append(result)

        if critical or high_risk:
            admins = User.objects.filter(role='admin', is_active=True)

            for admin in admins:
                message_parts = []

                if critical:
                    names = ', '.join([r['provider_name'] for r in critical])
                    message_parts.append(
                        f'{len(critical)} CRITICAL risk providers: {names}'
                    )

                if high_risk:
                    names = ', '.join([r['provider_name'] for r in high_risk])
                    message_parts.append(
                        f'{len(high_risk)} high risk providers: {names}'
                    )

                notify(
                    user=admin,
                    notification_type='provider_flagged',
                    title='Nightly Fraud Scan Results',
                    message=' | '.join(message_parts),
                )

        logger.info(
            f'Nightly fraud scan complete: '
            f'{len(critical)} critical, {len(high_risk)} high risk, '
            f'{len(providers)} total checked'
        )

        return {
            'total_checked': len(providers),
            'critical':      len(critical),
            'high_risk':     len(high_risk),
        }

    except Exception as e:
        logger.error(f'Nightly fraud scan failed: {e}')
        raise self.retry(exc=e, countdown=300)


@shared_task(bind=True)
def check_new_review_fraud(self, review_id):
    """
    Runs immediately after a new review is created.
    Auto-flags suspicious reviews.
    """
    from reviews.models import Review
    from .fraud_detection import run_full_review_fraud_check

    try:
        review = Review.objects.select_related(
            'customer__customer_profile',
            'provider',
            'service',
        ).get(id=review_id)

        result = run_full_review_fraud_check(review)

        if result['should_flag']:
            review.is_flagged = True
            review.save(update_fields=['is_flagged'])

            logger.warning(
                f'Review#{review_id} auto-flagged. '
                f'Flags: {[f["rule"] for f in result["flags"]]}'
            )

            from notifications.services import notify
            from accounts.models import User

            admins = User.objects.filter(role='admin', is_active=True)
            for admin in admins:
                notify(
                    user=admin,
                    notification_type='review_received',
                    title='Suspicious Review Flagged',
                    message=(
                        f'Review#{review_id} was auto-flagged. '
                        f'Reasons: {", ".join([f["rule"] for f in result["flags"]])}'
                    ),
                )

        return result

    except Review.DoesNotExist:
        logger.warning(f'check_new_review_fraud: Review#{review_id} not found')
    except Exception as e:
        logger.error(f'check_new_review_fraud failed: {e}')


@shared_task(bind=True)
def update_provider_completion_rates(self):
    """
    Recalculates completion_rate for all ProviderService records.
    Schedule: every 6 hours.

    completion_rate = completed / (completed + cancelled_by_provider + disputed)
    """
    from services.models import ProviderService
    from bookings.models import Booking

    try:
        services = ProviderService.objects.select_related('provider').all()
        updated  = 0

        for service in services:
            total_accepted = Booking.objects.filter(
                service=service,
                status__in=['completed', 'cancelled', 'disputed'],
            ).exclude(
                cancelled_by='customer'
            ).count()

            if total_accepted == 0:
                continue

            completed = Booking.objects.filter(
                service=service,
                status='completed',
            ).count()

            rate = completed / total_accepted

            service.completion_rate = round(rate, 4)
            service.save(update_fields=['completion_rate', 'updated_at'])
            updated += 1

        logger.info(f'Completion rates updated for {updated} services')
        return {'updated': updated}

    except Exception as e:
        logger.error(f'update_provider_completion_rates failed: {e}')
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3)
def update_provider_ranking_signals(self):
    """
    Recomputes the four cached behavioral signals used by
    ai_engine.ranking.calculate_ranking_score:
        cached_response_speed, cached_cancellation_rate,
        cached_repeat_bonus, cached_recency_score

    Schedule: every 6 hours (offset 15 min after completion-rate task).

    IMPORTANT: each signal is computed with ONE aggregation query across
    ALL providers (via .values().annotate()), not one query per provider.
    This is what keeps the live ranking path (calculate_ranking_score)
    free of per-request DB calls — see ai_engine/ranking.py docstring.
    Total query cost of this task is O(1) in provider count: 4 aggregate
    queries + 1 bulk_update, regardless of whether there are 10 or 10,000
    approved providers.
    """
    from django.utils import timezone
    from django.db.models import Count, Avg, Max, F, ExpressionWrapper, fields
    from datetime import timedelta
    from profiles.models import ProviderProfile
    from bookings.models import Booking

    try:
        now = timezone.now()
        ninety_days_ago = now - timedelta(days=90)

        providers = list(
            ProviderProfile.objects.filter(approval_status='approved')
        )
        provider_ids = [p.id for p in providers]

        if not provider_ids:
            logger.info('update_provider_ranking_signals: no approved providers, skipping')
            return {'updated': 0}

        # ── Signal 1: response speed ──────────────────────────────
        # avg seconds-to-accept per provider, last 90 days, instant bookings only
        response_qs = (
            Booking.objects.filter(
                provider_id__in=provider_ids,
                booking_type='instant',
                status__in=['accepted', 'completed'],
                accepted_at__isnull=False,
                created_at__gte=ninety_days_ago,
            )
            .annotate(
                response_seconds=ExpressionWrapper(
                    F('accepted_at') - F('created_at'),
                    output_field=fields.DurationField(),
                )
            )
            .values('provider_id')
            .annotate(avg_seconds=Avg('response_seconds'))
        )
        response_map = {
            row['provider_id']: row['avg_seconds'].total_seconds()
            for row in response_qs if row['avg_seconds'] is not None
        }

        # ── Signal 2: cancellation rate ───────────────────────────
        total_accepted_qs = (
            Booking.objects.filter(
                provider_id__in=provider_ids,
                status__in=['accepted', 'on_the_way', 'arrived',
                             'in_progress', 'completed', 'cancelled'],
                accepted_at__gte=ninety_days_ago,
            )
            .values('provider_id')
            .annotate(total=Count('id'))
        )
        total_accepted_map = {row['provider_id']: row['total'] for row in total_accepted_qs}

        provider_cancels_qs = (
            Booking.objects.filter(
                provider_id__in=provider_ids,
                status='cancelled',
                cancelled_by='provider',
                accepted_at__gte=ninety_days_ago,
            )
            .values('provider_id')
            .annotate(cancels=Count('id'))
        )
        cancels_map = {row['provider_id']: row['cancels'] for row in provider_cancels_qs}

        # ── Signal 3: repeat booking bonus ────────────────────────
        # customers with >1 completed booking, per provider, in one query
        repeat_qs = (
            Booking.objects.filter(
                provider_id__in=provider_ids,
                status='completed',
            )
            .values('provider_id', 'customer_id')
            .annotate(booking_count=Count('id'))
            .filter(booking_count__gt=1)
            .values('provider_id')
            .annotate(repeat_customers=Count('customer_id'))
        )
        repeat_map = {row['provider_id']: row['repeat_customers'] for row in repeat_qs}

        # ── Signal 4: recency ──────────────────────────────────────
        recency_qs = (
            Booking.objects.filter(
                provider_id__in=provider_ids,
                status='completed',
            )
            .values('provider_id')
            .annotate(last_completed=Max('completed_at'))
        )
        last_completed_map = {
            row['provider_id']: row['last_completed']
            for row in recency_qs if row['last_completed'] is not None
        }

        # ── Combine into per-provider field updates ───────────────
        for provider in providers:
            pid = provider.id

            # response speed: 60s = 1.0, 1800s (30min) = 0.0, no data = 0.5
            avg_seconds = response_map.get(pid)
            if avg_seconds is None:
                provider.cached_response_speed = 0.5
            else:
                provider.cached_response_speed = round(
                    1.0 - min(avg_seconds / 1800.0, 1.0), 4
                )

            # cancellation rate: <5 accepted bookings = no penalty (new provider)
            total = total_accepted_map.get(pid, 0)
            if total < 5:
                provider.cached_cancellation_rate = 0.0
            else:
                cancels = cancels_map.get(pid, 0)
                provider.cached_cancellation_rate = round(min(cancels / total, 1.0), 4)

            # repeat bonus: 20+ repeat customers = 1.0
            repeat_customers = repeat_map.get(pid, 0)
            provider.cached_repeat_bonus = round(min(repeat_customers / 20.0, 1.0), 4)

            # recency
            last_completed = last_completed_map.get(pid)
            if last_completed is None:
                provider.cached_recency_score = 0.1
            else:
                days_ago = (now - last_completed).days
                if days_ago <= 7:
                    provider.cached_recency_score = 1.0
                elif days_ago <= 14:
                    provider.cached_recency_score = 0.8
                elif days_ago <= 30:
                    provider.cached_recency_score = 0.6
                elif days_ago <= 60:
                    provider.cached_recency_score = 0.3
                elif days_ago <= 90:
                    provider.cached_recency_score = 0.1
                else:
                    provider.cached_recency_score = 0.0

            provider.ranking_signals_updated_at = now

        ProviderProfile.objects.bulk_update(
            providers,
            [
                'cached_response_speed',
                'cached_cancellation_rate',
                'cached_repeat_bonus',
                'cached_recency_score',
                'ranking_signals_updated_at',
            ],
            batch_size=500,
        )

        logger.info(f'Ranking signals updated for {len(providers)} providers')
        return {'updated': len(providers)}

    except Exception as e:
        logger.error(f'update_provider_ranking_signals failed: {e}')
        raise self.retry(exc=e, countdown=60)