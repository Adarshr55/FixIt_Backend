from django.db   import models
from django.conf import settings


class Booking(models.Model):

    STATUS_CHOICES = [
        ('requested',   'Requested'),
        ('accepted',    'Accepted'),
        ('on_the_way',  'On The Way'),
        ('arrived',     'Arrived'),
        ('in_progress', 'In Progress'),
        ('completed',   'Completed'),
        ('cancelled',   'Cancelled'),
        ('rejected',    'Rejected'),
        ('disputed',    'Disputed'),
    ]

    BOOKING_TYPE_CHOICES = [
        ('instant',   'Instant'),
        ('scheduled', 'Scheduled'),
    ]

    CANCEL_BY_CHOICES = [
        ('customer', 'Customer'),
        ('provider', 'Provider'),
        ('system',   'System'),    # reserved for Celery auto-cancel later
    ]

    PAYMENT_METHOD_CHOICES = [
    ('razorpay', 'Razorpay'),
    ('cash',     'Cash'),
    ]

    PAYMENT_STATUS_CHOICES = [
    ('unpaid',   'Unpaid'),
    ('paid',     'Paid'),
    ('refunded', 'Refunded'),
    ]


    # ── Relations ────────────────────────────────────────────────
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='customer_bookings',
    )
    provider = models.ForeignKey(
        'profiles.ProviderProfile',
        on_delete=models.SET_NULL,
        null=True,
        related_name='provider_bookings',
    )
    service = models.ForeignKey(
        'services.ProviderService',
        on_delete=models.SET_NULL,
        null=True,
        related_name='bookings',
        # SET_NULL so old bookings survive if provider removes a service
    )
    category = models.ForeignKey(
        'services.ServiceCategory',
        on_delete=models.SET_NULL,
        null=True,
        related_name='bookings',
        # Denormalized — admin can filter "all Electrician bookings"
        # without joining through ProviderService
        # Also survives if ProviderService is deleted
    )

    # ── Booking info ─────────────────────────────────────────────
    booking_type      = models.CharField(max_length=20, choices=BOOKING_TYPE_CHOICES, default='instant')
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested', db_index=True)
    issue_description = models.TextField()
    issue_photo       = models.ImageField(upload_to='booking_issues/', blank=True, null=True)

    # ── Customer location ────────────────────────────────────────
    customer_address   = models.TextField(blank=True)
    customer_latitude  = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    customer_longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    # ── Scheduling ───────────────────────────────────────────────
    scheduled_at = models.DateTimeField(null=True, blank=True)
    # Celery will use this later to send reminder 1 hour before

    # ── Pricing snapshot ─────────────────────────────────────────
    agreed_base_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    agreed_hourly_rate = models.DecimalField(max_digits=8,  decimal_places=2, null=True, blank=True)
    final_amount= models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_status = models.CharField(max_length=20,choices=PAYMENT_STATUS_CHOICES,default='unpaid',db_index=True,)
    payment_method = models.CharField(max_length=20,choices=PAYMENT_METHOD_CHOICES,default='razorpay',)
    # final_amount set by provider when completing
    # Payments phase uses this to calculate commission

    # ── Cancellation ─────────────────────────────────────────────
    cancelled_by  = models.CharField(max_length=20, choices=CANCEL_BY_CHOICES, blank=True)
    cancel_reason = models.TextField(blank=True)

    # ── Rejection ────────────────────────────────────────────────
    reject_reason = models.TextField(blank=True)

    # ── Dispute ──────────────────────────────────────────────────
    dispute_reason = models.TextField(blank=True)

    # ── Event timestamps ─────────────────────────────────────────
    accepted_at  = models.DateTimeField(null=True, blank=True)
    started_at   = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # accepted_at  → used for provider response speed (AI ranking)
    # started_at   → used for job duration calculation
    # completed_at → used for payment trigger (Phase 4)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bookings'
        ordering = ['-created_at']

    def __str__(self):
        return f'Booking#{self.id} — {self.customer.email} → {self.provider.full_name} [{self.status}]'

    # ── Helper properties ─────────────────────────────────────────
    @property
    def is_active(self):
        return self.status in ['requested', 'accepted', 'on_the_way', 'arrived', 'in_progress']

    @property
    def is_completed(self):
        return self.status == 'completed'

    @property
    def is_cancellable(self):
        # can only cancel before work actually starts
        return self.status in ['requested', 'accepted', 'on_the_way', 'arrived']


class BookingStatusHistory(models.Model):
    """
    One row per status change — full audit trail.
    Used for admin dispute resolution and future AI analytics.
    changed_by = None when system (Celery) changes status.
    """
    booking    = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='status_history')
    status     = models.CharField(max_length=20, choices=Booking.STATUS_CHOICES)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='booking_status_changes',
    )
    note      = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'booking_status_history'
        ordering = ['timestamp']

    def __str__(self):
        return f'Booking#{self.booking_id} → {self.status} at {self.timestamp}'