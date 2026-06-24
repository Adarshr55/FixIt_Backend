from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
# Create your models here.



class Review(models.Model):
      RATING_CHOICES = [
        (1, '1 — Poor'),
        (2, '2 — Below Average'),
        (3, '3 — Average'),
        (4, '4 — Good'),
        (5, '5 — Excellent'),
    ]
      booking  = models.OneToOneField('bookings.Booking',on_delete=models.CASCADE,related_name='review',)
        # OneToOneField — one review per booking, enforced at DB level
      customer = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='reviews_given',)
      provider = models.ForeignKey('profiles.ProviderProfile',on_delete=models.CASCADE,related_name='reviews_received')
      service  = models.ForeignKey('services.ProviderService',on_delete=models.SET_NULL,null=True,related_name='reviews',)
        # SET_NULL — review survives even if provider removes service
      rating=models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)],db_index=True)
      comment=models.TextField(blank=True)
      is_flagged = models.BooleanField(default=False)
      created_at=models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)

      class Meta:
            db_table='reviews'
            ordering = ['-created_at']
      
      def __str__(self):
        return (f'Review by {self.customer.email} 'f'for {self.provider.full_name} 'f'— {self.rating}★')
      

class Report(models.Model):
    """
    Customer reports a provider for bad behavior.
    Goes to admin review queue.

    3+ fraud reports in 30 days → provider auto-flagged.
    This check runs in the serializer after each report is saved.
    """

    REASON_CHOICES = [
        ('overcharging',   'Overcharging'),
        ('no_show',        'Provider Did Not Show Up'),
        ('rude_behavior',  'Rude or Aggressive Behavior'),
        ('fraud',          'Fraud or Scam'),
        ('poor_quality',   'Poor Quality Work'),
        ('other',          'Other'),
    ]

    STATUS_CHOICES = [
        ('pending',   'Pending Review'),
        ('reviewed',  'Under Review'),
        ('resolved',  'Resolved'),
        ('dismissed', 'Dismissed'),
    ]

    booking  = models.ForeignKey('bookings.Booking',on_delete=models.CASCADE,related_name='reports',)
        # ForeignKey not OneToOne — customer could report
        # multiple issues for same booking (rare but allowed
    customer = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='reports_filed',)
    provider = models.ForeignKey('profiles.ProviderProfile',on_delete=models.CASCADE,related_name='reports_against',)
    reason      = models.CharField(max_length=20, choices=REASON_CHOICES)
    description = models.TextField()
    # Customer explains the issue in detail
    status      = models.CharField( max_length=20,choices=STATUS_CHOICES,default='pending',db_index=True,)
    admin_note  = models.TextField(blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True, blank=True,related_name='reports_resolved',)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    class Meta:
        db_table = 'reports'
        ordering = ['-created_at']
    def __str__(self):return (f'Report by {self.customer.email} 'f'against {self.provider.full_name} 'f'— {self.reason} ({self.status})')




    