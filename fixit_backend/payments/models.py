from django.db   import models
from django.conf import settings


class ProviderWallet(models.Model):
    """
    One wallet per provider.
    Created automatically when provider is approved.
    Balance is updated after every payment webhook.
    """
    provider       = models.OneToOneField(
        'profiles.ProviderProfile',
        on_delete=models.CASCADE,
        related_name='wallet',
    )
    balance         = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_earned    = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_withdrawn = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'provider_wallets'

    def __str__(self):
        return f'Wallet — {self.provider.full_name} [₹{self.balance}]'


class WalletTransaction(models.Model):
    """
    One row per money movement.
    Full audit trail — never delete these.
    """
    TRANSACTION_TYPES = [
        ('credit',      'Credit'),       # payment received from customer
        ('debit',       'Debit'),        # withdrawal processed
        ('commission',  'Commission'),   # platform commission deducted
        ('refund',      'Refund'),       # refund issued
    ]

    wallet           = models.ForeignKey(
        ProviderWallet,
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    booking          = models.ForeignKey(
        'bookings.Booking',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='wallet_transactions',
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount           = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after    = models.DecimalField(max_digits=12, decimal_places=2)
    description      = models.TextField(blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'wallet_transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.transaction_type} ₹{self.amount} — {self.wallet.provider.full_name}'


class Payment(models.Model):
    """
    One payment per booking.
    Razorpay order created here, webhook updates status.
    """
    STATUS_CHOICES = [
        ('pending',  'Pending'),
        ('paid',     'Paid'),
        ('failed',   'Failed'),
        ('refunded', 'Refunded'),
    ]
    METHOD_CHOICES = [
        ('razorpay', 'Razorpay'),
        ('cash',     'Cash'),
    ]

    booking              = models.OneToOneField(
        'bookings.Booking',
        on_delete=models.CASCADE,
        related_name='payment',
    )
    customer             = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='payments',
    )
    provider             = models.ForeignKey(
        'profiles.ProviderProfile',
        on_delete=models.SET_NULL,
        null=True,
        related_name='payments_received',
    )

    method               = models.CharField(max_length=20, choices=METHOD_CHOICES, default='razorpay')
    status               = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    amount               = models.DecimalField(max_digits=10, decimal_places=2)
    platform_commission  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    provider_earning     = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Razorpay fields — blank for cash payments
    razorpay_order_id    = models.CharField(max_length=100, blank=True)
    razorpay_payment_id  = models.CharField(max_length=100, blank=True)
    razorpay_signature   = models.CharField(max_length=255, blank=True)

    paid_at              = models.DateTimeField(null=True, blank=True)
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments'
        ordering = ['-created_at']

    def __str__(self):
        return f'Payment#{self.id} — ₹{self.amount} [{self.status}]'


class WithdrawalRequest(models.Model):
    """
    Provider requests withdrawal of wallet balance.
    Admin processes manually and marks as processed.
    Gated behind kyc_verified + bank_account.is_verified.
    """
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
        ('processed', 'Processed'),
    ]

    wallet        = models.ForeignKey(
        ProviderWallet,
        on_delete=models.CASCADE,
        related_name='withdrawal_requests',
    )
    provider      = models.ForeignKey(
        'profiles.ProviderProfile',
        on_delete=models.CASCADE,
        related_name='withdrawal_requests',
    )

    amount        = models.DecimalField(max_digits=10, decimal_places=2)

    # snapshot of payout details at time of request
    # in case provider updates bank later
    payout_method = models.CharField(
        max_length=20,
        choices=[('bank', 'Bank Transfer'), ('upi', 'UPI')],
        default='bank',
    )
    upi_id              = models.CharField(max_length=100, blank=True)
    account_holder_name = models.CharField(max_length=100, blank=True)
    account_number      = models.CharField(max_length=20, blank=True)
    ifsc_code           = models.CharField(max_length=11, blank=True)
    bank_name           = models.CharField(max_length=100, blank=True)

    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_note    = models.TextField(blank=True)

    processed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='withdrawals_processed',
    )
    requested_at  = models.DateTimeField(auto_now_add=True)
    processed_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'withdrawal_requests'
        ordering = ['-requested_at']

    def __str__(self):
        return f'Withdrawal#{self.id} — ₹{self.amount} [{self.status}]'