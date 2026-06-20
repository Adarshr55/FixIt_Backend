"""
Central notification creation service.
All notification creation goes through this file.
Never create Notification objects directly in views or signals.
"""

from .models import Notification
import logging


logger = logging.getLogger(__name__)


def notify(user,notification_type,title,message,booking=None):
    """
    Create a notification for a user.
    Safe to call from anywhere — signals, views, tasks.
    """
    notification=Notification.objects.create(
        user=user,
        notification_type = notification_type,
        title=title,
        message=message,
        booking=booking,
        )
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer=get_channel_layer()
        group_name    = f'user_{user.id}_notifications'
        unread_count = Notification.objects.filter(
            user=user, is_read=False
        ).count()

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type':              'notification.new',  # → calls notification_new() in consumer
                'id':                notification.id,
                'notification_type': notification_type,
                'title':             title,
                'message':           message,
                'booking_id':        booking.id if booking else None,
                'created_at':        notification.created_at.isoformat(),
                'unread_count':      unread_count,
            }
        )
    except Exception as e:
        # Never let WebSocket push failure break the notification
        # DB save already succeeded — REST fallback still works
        logger.warning(f'WebSocket push failed for user {user.id}: {e}')

    return notification

    

def notify_booking_requested(booking):
     """Provider receives new booking alert."""
     from django.utils import timezone
     from datetime import timedelta
     
     address_str = booking.customer_address
     if booking.booking_type == 'scheduled' and booking.scheduled_at:
         if booking.scheduled_at > timezone.now() + timedelta(hours=1):
             address_str = "[Masked until 1 hour before service]"
             
     notify(
          user=booking.provider.user,
          notification_type='booking_requested',
          title='New Booking Request',
          message=(
                f'{booking.customer.customer_profile.full_name} wants to book '
                f'{booking.category.name}. '
                f'Base charge: ₹{booking.agreed_base_charge}. '
                f'Address: {address_str}.'
          ),
          booking=booking
      )

def notify_booking_accepted(booking):
      """Customer knows provider accepted."""
      notify(
           user=booking.customer,
           notification_type='booking_accepted',
           title='Booking Accepted',
           message=(
            f'{booking.provider.full_name} has accepted your '
            f'{booking.category.name} booking. '
            f'They will be on their way shortly.'
           ),
           booking=booking
      )

def notify_booking_rejected(booking):
     """Customer knows provider rejected."""
     notify(
          user=booking.customer,
          notification_type='booking_rejected',
          title='Booking Rejected',
          message        = (
            f'Your {booking.category.name} booking was declined. '
            f'Reason: {booking.reject_reason}. '
            f'Please try another provider.'
           ),
           booking=booking
     )

def notify_booking_cancelled(booking):
     """Both parties notified on cancellation."""
     if booking.cancelled_by == 'customer':
            notify(
            user= booking.provider.user,
            notification_type='booking_cancelled',
            title= 'Booking Cancelled',
            message = (
                f'Customer cancelled the {booking.category.name} booking. '
                f'Reason: {booking.cancel_reason}.'
            ),
            booking= booking,
        )
     elif booking.cancelled_by == 'provider':
           notify(
            user= booking.customer,
            notification_type='booking_cancelled',
            title= 'Booking Cancelled by Provider',
            message= (
                f'Your provider cancelled the {booking.category.name} booking. '
                f'Reason: {booking.cancel_reason}. '
                f'Please book another provider.'
            ),
            booking= booking,
           )
     elif booking.cancelled_by == 'system':
        # notify customer — auto-cancel
        notify(
            user= booking.customer,
            notification_type='booking_auto_cancelled', 
            title= 'Booking Auto-Cancelled',
            message= (
                f'Your {booking.category.name} booking was automatically '
                f'cancelled because no provider responded within 2 minutes. '
                f'Please try again.'
            ),
            booking= booking,
        )
    

def notify_booking_on_the_way(booking):
     """Customer knows provider is moving."""
     notify(
        user = booking.customer,
        notification_type='booking_on_the_way',
        title = 'Provider On The Way',
        message = (
            f'{booking.provider.full_name} is on the way to your location. '
            f'Track their location in the app.'
        ),
        booking = booking,
    )
def notify_booking_arrived(booking):
    """Customer knows provider arrived."""
    notify(
        user = booking.customer,
        notification_type='booking_arrived',
        title = 'Provider Arrived',
        message = (
            f'{booking.provider.full_name} has arrived at your location.'
        ),
        booking= booking,
    )

def notify_booking_completed(booking):
    """Both parties notified on completion."""
    # notify customer
    notify(
        user= booking.customer,
        notification_type='booking_completed',
        title= 'Service Completed',
        message= (
            f'Your {booking.category.name} service is complete. '
            f'Final amount: ₹{booking.final_amount}. '
            f'Please rate your experience.'
        ),
        booking= booking,
    )
    # notify provider
    notify(
        user=booking.provider.user,
        notification_type='booking_completed',
        title='Job Completed',
        message= (
            f'You have completed the {booking.category.name} job. '
            f'Earnings will be credited after commission deduction.'
        ),
        booking= booking,
    )

def notify_booking_disputed(booking):
    """Provider notified customer raised dispute."""
    notify(
        user= booking.provider.user,
        notification_type='booking_disputed',
        title = 'Booking Disputed',
        message= (
            f'Customer raised a dispute for your {booking.category.name} job. '
            f'Reason: {booking.dispute_reason}. '
            f'Admin will review and resolve.'
        ),
        booking= booking,
    )

def notify_booking_reminder(booking):
    """Provider reminder for upcoming scheduled booking."""
    notify(
        user= booking.provider.user,
        notification_type='booking_reminder',
        title= 'Upcoming Booking Reminder',
        message= (
            f'You have a {booking.category.name} booking in 1 hour. '
            f'Address: {booking.customer_address}. '
            f'Be ready on time.'
        ),
        booking= booking,
    )

def notify_customer_booking_reminder(booking):
    """Customer reminder for upcoming scheduled booking."""
    notify(
        user=booking.customer,
        notification_type='booking_reminder_customer',
        title='Upcoming Booking Reminder',
        message=(
            f'Your {booking.category.name} booking with {booking.provider.full_name} '
            f'is scheduled for {booking.scheduled_at.strftime("%I:%M %p")}. '
            f'Provider will start travel shortly.'
        ),
        booking=booking,
    )



def notify_provider_approved(provider_profile):
    """Provider learns their account was approved."""
    notify(
        user= provider_profile.user,
        notification_type='provider_approved',
        title= 'Account Approved',
        message= (
            f'Congratulations! Your provider account has been approved. '
            f'Go online to start receiving bookings.'
        ),
    )

def notify_provider_rejected(provider_profile):
    """Provider learns their account was rejected."""
    notify(
        user= provider_profile.user,
        notification_type='provider_rejected',
        title= 'Account Rejected',
        message= (
            f'Your provider account was rejected. '
            f'Reason: {provider_profile.rejection_reason}. '
            f'Please update your profile and resubmit.'
        ),
    )

def notify_provider_suspended(provider_profile):
     notify(
          user=provider_profile.user,
          notification_type='provider_suspended',
          title='Account Suspended',
          message=(
                f'Your provider account has been suspended. '
                f'Please contact support for more information.'
          )
     )
def notify_provider_reactivated(provider_profile):
     notify(
          user=provider_profile.user,
          notification_type='provider_reactivated',
          title='Account Reactivated',
          message=(
               f'Account has been reactivated'
          )
     )
     

def notify_document_approved(document):
    """Provider learns their document was approved."""
    notify(
        user= document.provider.user,
        notification_type='document_approved',
        title= 'Document Approved',
        message= (
            f'Your {document.get_doc_type_display()} has been approved. '
            f'Your service verification is progressing.'
        ),
    )    


def notify_document_rejected(document):
    """Provider learns their document was rejected."""
    notify(
        user= document.provider.user,
        notification_type='document_rejected',
        title= 'Document Rejected',
        message= (
            f'Your {document.get_doc_type_display()} was rejected. '
            f'Reason: {document.reject_reason}. '
            f'Please re-upload a clearer document.'
        ),
    ) 


def notify_service_verified(service):
    notify(
        user=service.provider.user,
        notification_type='service_verified',
        title='Service Verified',
        message=(
            f'Your {service.category.name} service has been verified. '
            f'You can now receive bookings.'
        ),
    )

def notify_service_rejected(service):
    notify(
        user=service.provider.user,
        notification_type='service_rejected',
        title='Service Rejected',
        message=(
            f'Your {service.category.name} service verification was rejected. '
            f'Please review your documents and try again.'
        ),
    )



def notify_review_submitted(review):
    """Provider learns they received a new review."""
    stars = '★' * review.rating + '☆' * (5 - review.rating)
    notify(
        user              = review.provider.user,
        notification_type = 'review_received',
        title             = 'New Review Received',
        message           = (
            f'You received a {review.rating}-star review '
            f'{stars} for your {review.service.category.name if review.service else "service"}. '
            f'"{review.comment[:80]}{"..." if len(review.comment) > 80 else ""}"'
        ),
        booking=review.booking,
    )


def notify_kyc_submitted(kyc):
    """All admins notified when a provider submits KYC."""
    from accounts.models import User
    admins = User.objects.filter(role='admin', is_active=True)
    for admin in admins:
        notify(
            user=admin,
            notification_type='kyc_submitted',
            title='New KYC Submission',
            message=(
                f'{kyc.provider.full_name} has submitted KYC documents '
                f'(PAN + Aadhaar) for verification.'
            ),
        )

def notify_kyc_pan_approved(provider):
    notify(
        user=provider.user,
        notification_type='kyc_pan_approved',
        title='PAN Card Approved',
        message='Your PAN card has been verified successfully.',
    )

def notify_kyc_pan_rejected(provider, reason):
    notify(
        user=provider.user,
        notification_type='kyc_pan_rejected',
        title='PAN Card Rejected',
        message=(
            f'Your PAN card verification was rejected. '
            f'Reason: {reason}. Please resubmit with a clearer document.'
        ),
    )

def notify_kyc_aadhaar_approved(provider):
    notify(
        user=provider.user,
        notification_type='kyc_aadhaar_approved',
        title='Aadhaar Verified',
        message='Your Aadhaar document has been verified successfully.',
    )

def notify_kyc_aadhaar_rejected(provider, reason):
    notify(
        user=provider.user,
        notification_type='kyc_aadhaar_rejected',
        title='Aadhaar Rejected',
        message=(
            f'Your Aadhaar verification was rejected. '
            f'Reason: {reason}. Please resubmit with a clearer document.'
        ),
    )

def notify_kyc_fully_verified(provider):
    notify(
        user=provider.user,
        notification_type='kyc_verified',
        title='KYC Fully Verified',
        message=(
            'Your KYC is complete. You can now add your bank account '
            'and request withdrawals once verified.'
        ),
    )

def notify_bank_account_submitted(bank):
    """All admins notified when provider submits bank details."""
    from accounts.models import User
    admins = User.objects.filter(role='admin', is_active=True)
    for admin in admins:
        notify(
            user=admin,
            notification_type='bank_submitted',
            title='Bank Account Pending Verification',
            message=(
                f'{bank.provider.full_name} submitted bank account '
                f'({bank.bank_name} — {bank.ifsc_code}) for verification.'
            ),
        )

def notify_bank_account_approved(bank):
    notify(
        user=bank.provider.user,
        notification_type='bank_approved',
        title='Bank Account Verified',
        message=(
            f'Your bank account ({bank.bank_name}) has been verified. '
            f'You can now request withdrawals.'
        ),
    )

def notify_bank_account_rejected(bank, reason):
    notify(
        user=bank.provider.user,
        notification_type='bank_rejected',
        title='Bank Account Rejected',
        message=(
            f'Your bank account verification was rejected. '
            f'Reason: {reason}. Please resubmit with correct details.'
        ),
    )


     
