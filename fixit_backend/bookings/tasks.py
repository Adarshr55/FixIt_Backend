from celery import shared_task
import logging

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
     logger.info(f'Booking #{booking_id} auto-cancelled — no provider response.')

