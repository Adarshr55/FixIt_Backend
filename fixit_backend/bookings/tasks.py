from celery import shared_task
import logging
from notifications.services import(
     notify_booking_cancelled,notify_booking_reminder
)
logger=logging.getLogger(__name__)

@shared_task(bind=True,max_retries=3)
def auto_cancel_booking(self,booking_id):
     
     """
    Fires 2 minutes after an INSTANT booking is created.
    If provider still hasn't accepted → auto-cancel.

    bind=True    → gives access to self for retries
    max_retries=3 → retry up to 3 times on DB errors

    Fires 2 minutes after an INSTANT booking is created.
    If provider still hasn't accepted → auto-cancel.

    bind=True    → gives access to self for retries
    max_retries=3 → retry up to 3 times on DB errors
    """
     from .models import Booking,BookingStatusHistory

     try:
          booking=Booking.objects.get(id=booking_id)
     except Booking.DoesNotExist:
          logger.warning(f'auto_cancel_booking: Booking #{booking_id} not found.')
          return
     
     if booking.status != 'requested':
          logger.info(
               f'auto_cancel_booking: Booking #{booking_id} is already '
                f'{booking.status} — skipping auto-cancel.'
          )
          return
     booking.status='cancelled'
     booking.cancelled_by='system'
     booking.cancel_reason=(
           'Provider did not respond within 2 minutes.'
     )
     booking.save(update_fields=['status', 'cancelled_by', 'cancel_reason', 'updated_at'])
     


     BookingStatusHistory.objects.create(
          booking=booking,
          status='cancelled',
          changed_by=None,
          note='Auto-cancelled: provider did not respond.',

        )
     try:
          notify_booking_cancelled(booking)
     except Exception as e:
           logger.error(f'notify failed for auto-cancel Booking #{booking_id}: {e}')
     
     logger.info(f'Booking #{booking_id} auto-cancelled — no provider response.')


@shared_task(bind=True,max_retries=3)
def send_scheduled_booking_reminder(self,booking_id):
       """
    Fires 1 hour before a SCHEDULED booking's scheduled_at time.
    Creates a notification for the provider.

    Connected to Celery Beat in Phase 3C when Notification model is built.
    For now just logs — notification hook added in next phase.
    """
       from .models import Booking
       try:
             booking = Booking.objects.select_related(
            'provider__user', 'customer', 'category'
        ).get(id=booking_id)
       except Booking.DoesNotExist:
             logger.warning(f'send_scheduled_booking_reminder: Booking #{booking_id} not found.')
             return
       
       if booking.status not in ['requested', 'accepted']:
        logger.info(
            f'send_scheduled_booking_reminder: Booking #{booking_id} '
            f'is {booking.status} — skipping reminder.'
        )
        return
       
       notify_booking_reminder(booking)
       logger.info(
        f'Reminder: Booking #{booking_id} is in 1 hour. '
        f'Provider: {booking.provider.full_name}'
    )