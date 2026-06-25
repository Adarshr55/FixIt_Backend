"""
FixIt Fraud Detection Engine — Phase 1
Pure Python rule-based fraud detection.
Zero external dependencies.

Rules implemented:
1. Review bombing — too many reviews in short time
2. Fake review detection — pattern analysis on text
3. Provider cancellation abuse
4. Customer booking abuse
5. Report clustering — multiple reports from same area
6. Self-review detection
"""

from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


# ── Thresholds ────────────────────────────────────────────────────
THRESHOLDS = {
    'review_bomb_count':         5,    # reviews in review_bomb_window = suspicious
    'review_bomb_window_hours':  2,    # hours to check for review bombing
    'min_review_length':        20,    # chars — shorter is suspicious
    'generic_review_phrases': [        # common fake review phrases
        'good service', 'nice work', 'great job', 'very good',
        'excellent', 'perfect', 'best', 'ok', 'okay', 'fine',
        'good', 'nice', 'great', 'awesome', 'superb', 'wonderful',
    ],
    'cancellation_abuse_rate':   0.5,  # 50% cancel rate = abuse
    'cancellation_abuse_min':    5,    # minimum bookings before checking
    'booking_abuse_window_hours': 24,  # hours
    'booking_abuse_count':        3,   # bookings then cancellations
    'fraud_report_window_days':  30,   # days
    'fraud_report_threshold':     3,   # fraud reports before auto-flag
}


# ── Main fraud check functions ────────────────────────────────────

def check_review_bombing(provider_profile):
    """
    Detects if a provider is receiving an unusual number of reviews
    in a very short time window — sign of coordinated fake reviews.

    Called after every new review is saved.
    Returns: { 'is_suspicious': bool, 'reason': str, 'count': int }
    """
    from reviews.models import Review

    window_start = timezone.now() - timedelta(
        hours=THRESHOLDS['review_bomb_window_hours']
    )

    recent_count = Review.objects.filter(
        provider=provider_profile,
        created_at__gte=window_start,
        is_flagged=False,
    ).count()

    if recent_count >= THRESHOLDS['review_bomb_count']:
        logger.warning(
            f'Review bombing detected: provider={provider_profile.id} '
            f'received {recent_count} reviews in '
            f'{THRESHOLDS["review_bomb_window_hours"]} hours'
        )
        return {
            'is_suspicious': True,
            'reason': f'Received {recent_count} reviews in {THRESHOLDS["review_bomb_window_hours"]} hours',
            'count': recent_count,
            'rule': 'review_bombing',
        }

    return {'is_suspicious': False}


def check_fake_review(review):
    """
    Analyzes a single review for signs of being fake.

    Signals checked:
    - Very short comment (under 20 chars)
    - Generic phrases that add no information
    - 5 stars but negative sentiment keywords
    - Same customer reviewing same provider multiple times

    Returns: { 'is_suspicious': bool, 'reasons': list }
    """
    from reviews.models import Review

    reasons = []

    # Check 1 — comment too short
    comment = (review.comment or '').strip()
    if len(comment) < THRESHOLDS['min_review_length'] and comment:
        reasons.append(f'Comment too short ({len(comment)} chars)')

    # Check 2 — generic phrase detection
    if comment:
        comment_lower = comment.lower()
        matched_phrases = [
            phrase for phrase in THRESHOLDS['generic_review_phrases']
            if comment_lower == phrase or comment_lower == phrase + '.'
        ]
        if matched_phrases:
            reasons.append(f'Generic phrase detected: "{matched_phrases[0]}"')

    # Check 3 — 5 stars but comment contains negative keywords
    negative_keywords = [
        'bad', 'terrible', 'worst', 'horrible', 'disappointed',
        'never again', 'waste', 'fraud', 'cheated', 'rude',
        'late', 'unprofessional', 'not good', 'poor'
    ]
    if review.rating == 5 and comment:
        comment_lower = comment.lower()
        found_negatives = [kw for kw in negative_keywords if kw in comment_lower]
        if found_negatives:
            reasons.append(
                f'5-star rating but negative keywords found: {found_negatives}'
            )

    # Check 4 — same customer reviewing same provider multiple times
    duplicate_count = Review.objects.filter(
        customer=review.customer,
        provider=review.provider,
    ).exclude(id=review.id).count()

    if duplicate_count > 0:
        reasons.append(
            f'Customer has {duplicate_count} other review(s) for same provider'
        )

    # Check 5 — customer has no profile (ghost account)
    try:
        profile = review.customer.customer_profile
        if not profile.full_name or len(profile.full_name.strip()) < 2:
            reasons.append('Customer has incomplete profile')
    except Exception:
        reasons.append('Customer has no profile')

    return {
        'is_suspicious': len(reasons) > 0,
        'reasons': reasons,
        'rule': 'fake_review',
    }


def check_provider_cancellation_abuse(provider_profile):
    """
    Detects providers who accept bookings then cancel them repeatedly.
    This wastes customer time and indicates unreliable behavior.

    Returns: { 'is_abusive': bool, 'rate': float, 'action': str }
    """
    from bookings.models import Booking

    thirty_days_ago = timezone.now() - timedelta(days=30)

    total = Booking.objects.filter(
        provider=provider_profile,
        accepted_at__gte=thirty_days_ago,
        status__in=['accepted', 'on_the_way', 'arrived',
                    'in_progress', 'completed', 'cancelled'],
    ).count()

    if total < THRESHOLDS['cancellation_abuse_min']:
        return {'is_abusive': False, 'rate': 0.0}

    provider_cancels = Booking.objects.filter(
        provider=provider_profile,
        cancelled_by='provider',
        accepted_at__gte=thirty_days_ago,
    ).count()

    rate = provider_cancels / total

    if rate >= THRESHOLDS['cancellation_abuse_rate']:
        logger.warning(
            f'Cancellation abuse: provider={provider_profile.id} '
            f'cancellation rate={rate:.1%} ({provider_cancels}/{total})'
        )

        # decide action based on severity
        if rate >= 0.8:
            action = 'suspend'
        elif rate >= 0.6:
            action = 'warn_and_flag'
        else:
            action = 'warn'

        return {
            'is_abusive': True,
            'rate': round(rate, 4),
            'cancels': provider_cancels,
            'total': total,
            'action': action,
            'rule': 'cancellation_abuse',
        }

    return {'is_abusive': False, 'rate': round(rate, 4)}


def check_customer_booking_abuse(customer_user):
    """
    Detects customers who repeatedly create and cancel bookings
    — wastes provider time and blocks slots for real customers.

    Returns: { 'is_abusive': bool, 'rate': float }
    """
    from bookings.models import Booking

    thirty_days_ago = timezone.now() - timedelta(days=30)

    total = Booking.objects.filter(
        customer=customer_user,
        created_at__gte=thirty_days_ago,
    ).count()

    if total < 5:
        return {'is_abusive': False}

    customer_cancels = Booking.objects.filter(
        customer=customer_user,
        status='cancelled',
        cancelled_by='customer',
        created_at__gte=thirty_days_ago,
    ).count()

    rate = customer_cancels / total

    if rate >= 0.7:  # cancels 70%+ of bookings
        logger.warning(
            f'Customer booking abuse: user={customer_user.id} '
            f'cancel rate={rate:.1%}'
        )
        return {
            'is_abusive': True,
            'rate': round(rate, 4),
            'cancels': customer_cancels,
            'total': total,
            'rule': 'booking_abuse',
        }

    return {'is_abusive': False, 'rate': round(rate, 4)}


def check_report_clustering(provider_profile):
    """
    Detects if a provider is receiving multiple fraud reports
    in a short time window — sign of systematic fraud.
    Existing check_and_flag_provider in reviews/utils.py handles
    the 3-report threshold. This adds pattern analysis.

    Returns: { 'is_clustered': bool, 'pattern': str }
    """
    from reviews.models import Report

    seven_days_ago  = timezone.now() - timedelta(days=7)
    thirty_days_ago = timezone.now() - timedelta(days=30)

    # check for rapid report clustering in last 7 days
    recent_reports = Report.objects.filter(
        provider=provider_profile,
        created_at__gte=seven_days_ago,
    ).count()

    # check fraud specifically
    fraud_reports_30d = Report.objects.filter(
        provider=provider_profile,
        reason='fraud',
        created_at__gte=thirty_days_ago,
    ).count()

    # check overcharging pattern
    overcharge_reports = Report.objects.filter(
        provider=provider_profile,
        reason='overcharging',
        created_at__gte=thirty_days_ago,
    ).count()

    patterns = []

    if recent_reports >= 3:
        patterns.append(f'{recent_reports} reports in 7 days')

    if fraud_reports_30d >= 2:
        patterns.append(f'{fraud_reports_30d} fraud reports in 30 days')

    if overcharge_reports >= 3:
        patterns.append(f'{overcharge_reports} overcharging reports in 30 days')

    if patterns:
        return {
            'is_clustered': True,
            'pattern': ' | '.join(patterns),
            'rule': 'report_clustering',
        }

    return {'is_clustered': False}


def run_full_provider_fraud_check(provider_profile):
    """
    Runs all fraud checks for a provider in one call.
    Used by admin panel and Celery periodic task.

    Returns combined result with all signals.
    """
    results = {
        'provider_id':       provider_profile.id,
        'provider_name':     provider_profile.full_name,
        'checked_at':        timezone.now().isoformat(),
        'flags':             [],
        'overall_risk':      'low',
        'recommended_action': 'none',
    }

    # run each check
    cancellation = check_provider_cancellation_abuse(provider_profile)
    if cancellation['is_abusive']:
        results['flags'].append(cancellation)

    report_cluster = check_report_clustering(provider_profile)
    if report_cluster['is_clustered']:
        results['flags'].append(report_cluster)

    # determine overall risk level
    flag_count = len(results['flags'])

    if flag_count == 0:
        results['overall_risk']       = 'low'
        results['recommended_action'] = 'none'
    elif flag_count == 1:
        results['overall_risk']       = 'medium'
        results['recommended_action'] = 'monitor'
    elif flag_count == 2:
        results['overall_risk']       = 'high'
        results['recommended_action'] = 'warn_provider'
    else:
        results['overall_risk']       = 'critical'
        results['recommended_action'] = 'suspend'

    return results


def run_full_review_fraud_check(review):
    """
    Runs all review fraud checks for a single review.
    Called after every new review is created.
    """
    results = {
        'review_id':   review.id,
        'flags':       [],
        'should_flag': False,
    }

    # check the review itself
    fake_check = check_fake_review(review)
    if fake_check['is_suspicious']:
        results['flags'].append(fake_check)

    # check for review bombing on the provider
    bomb_check = check_review_bombing(review.provider)
    if bomb_check['is_suspicious']:
        results['flags'].append(bomb_check)

    results['should_flag'] = len(results['flags']) > 0
    return results