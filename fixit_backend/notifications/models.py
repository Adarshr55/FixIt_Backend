from django.db import models
from django.conf import settings
# Create your models here.
class Notification(models.Model):
     NOTIFICATION_TYPES = [
        # Booking events
        ('booking_requested',   'New Booking Request'),
        ('booking_accepted',    'Booking Accepted'),
        ('booking_rejected',    'Booking Rejected'),
        ('booking_cancelled',   'Booking Cancelled'),
        ('booking_on_the_way',  'Provider On The Way'),
        ('booking_arrived',     'Provider Arrived'),
        ('booking_in_progress', 'Work In Progress'),
        ('booking_completed',   'Booking Completed'),
        ('booking_disputed',    'Booking Disputed'),
        ('booking_auto_cancelled', 'Booking Auto Cancelled'),

        # Provider account events
        ('provider_approved',   'Provider Approved'),
        ('provider_rejected',   'Provider Rejected'),
        ('provider_suspended',  'Account Suspended'),
        ('provider_reactivated', 'Account Reactivated'),

        # Document events
        ('document_approved',   'Document Approved'),
        ('document_rejected',   'Document Rejected'),

        # Booking reminders
        ('booking_reminder',    'Booking Reminder'),
         
         #service
        ('service_verified', 'Service Verified'),
        ('service_rejected', 'Service Rejected'),

        # Payment events (Phase 4)
        ('payment_received',    'Payment Received'),
        ('withdrawal_approved', 'Withdrawal Approved'),
        ('withdrawal_rejected', 'Withdrawal Rejected'),

        ('provider_flagged', 'Provider Auto-Flagged'),
        ('review_received', 'Review Received'),
        ('booking_reminder_customer', 'Customer Booking Reminder'),

        ('kyc_submitted', 'KYC Submitted'),
        ('kyc_pan_approved','PAN Approved'),
        ('kyc_pan_rejected','PAN Rejected'),
        ('kyc_aadhaar_approved','Aadhaar Approved'),
        ('kyc_aadhaar_rejected','Aadhaar Rejected'),
        ('kyc_verified','KYC Fully Verified'),
        ('bank_submitted','Bank Account Submitted'),
        ('bank_approved','Bank Account Approved'),
        ('bank_rejected','Bank Account Rejected'),
            ]
    
     user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='notifications')
     notification_type=models.CharField(max_length=30,choices=NOTIFICATION_TYPES,db_index=True)
     title=models.CharField(max_length=225)
     message=models.TextField()
     booking= models.ForeignKey('bookings.Booking',on_delete=models.SET_NULL,null=True, blank=True,related_name='notifications')
     is_read=models.BooleanField(default=False)
     created_at=models.DateTimeField(auto_now_add=True)

     class Meta:
        db_table='notifications'
        ordering=['-created_at']
     def __str__(self):
         return f'{self.user.email} — {self.title} — {"read" if self.is_read else "unread"}'