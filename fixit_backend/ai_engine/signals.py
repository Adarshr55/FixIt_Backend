"""
Django signals that trigger embedding creation automatically.
Every time a category or service is saved, embedding updates in background.
"""

from django.db.models.signals import post_save
from django.dispatch  import receiver
import logging

logger = logging.getLogger(__name__)


def connect_signals():
    """
    Called from ai_engine/apps.py ready() method.
    Delayed import avoids circular imports at startup.
    """
    from services.models import ServiceCategory, ProviderService
    from bookings.models import Booking

    @receiver(post_save, sender=ServiceCategory)
    def on_category_save(sender, instance, **kwargs):
        """Re-embed category whenever admin updates it."""
        from ai_engine.tasks import embed_category_async
        embed_category_async.delay(instance.id)
        logger.info(f'Queued embedding for category id={instance.id}')

    @receiver(post_save, sender=ProviderService)
    def on_service_save(sender, instance, **kwargs):
        """Embed service when provider creates or updates it."""
        if instance.verification_status == 'verified':
            from ai_engine.tasks import embed_service_async
            embed_service_async.delay(instance.id)

    @receiver(post_save, sender=Booking)
    def on_booking_complete(sender, instance, **kwargs):
        """Embed issue description when booking is completed."""
        if instance.status == 'completed' and instance.issue_description:
            from ai_engine.tasks import embed_issue_async
            embed_issue_async.delay(instance.id)

    from reviews.models import Review

    @receiver(post_save, sender=Review)
    def on_review_save(sender, instance, **kwargs):
        """Auto-scan review for fake reviews / bombing."""
        from ai_engine.tasks import check_new_review_fraud
        check_new_review_fraud.delay(instance.id)