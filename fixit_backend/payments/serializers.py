from rest_framework import serializers
from django.conf    import settings
from .models        import Payment, ProviderWallet, WalletTransaction, WithdrawalRequest
from bookings.models import Booking


# ── Wallet ────────────────────────────────────────────────────────

class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = WalletTransaction
        fields = [
            'id', 'transaction_type', 'amount',
            'balance_after', 'description', 'created_at',
        ]


class ProviderWalletSerializer(serializers.ModelSerializer):
    transactions = WalletTransactionSerializer(many=True, read_only=True)

    class Meta:
        model  = ProviderWallet
        fields = [
            'id', 'balance', 'total_earned',
            'total_withdrawn', 'transactions',
            'created_at', 'updated_at',
        ]


# ── Payment ───────────────────────────────────────────────────────

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Payment
        fields = [
            'id', 'booking', 'method', 'status',
            'amount', 'platform_commission', 'provider_earning',
            'razorpay_order_id', 'paid_at', 'created_at',
        ]


class CreateRazorpayOrderSerializer(serializers.Serializer):
    """Customer initiates Razorpay payment for a completed booking."""
    booking_id = serializers.IntegerField()

    def validate_booking_id(self, value):
        user = self.context['request'].user
        try:
            booking = Booking.objects.select_related(
                'provider', 'customer', 'category'
            ).get(id=value, customer=user)
        except Booking.DoesNotExist:
            raise serializers.ValidationError('Booking not found.')

        if booking.status != 'completed':
            raise serializers.ValidationError(
                'Payment is only allowed for completed bookings.'
            )

        if booking.payment_status == 'paid':
            raise serializers.ValidationError(
                'This booking has already been paid.'
            )

        if not booking.final_amount:
            raise serializers.ValidationError(
                'Final amount not set by provider yet.'
            )

        self._booking = booking
        return value


class CashPaymentSerializer(serializers.Serializer):
    """Provider marks cash collected for a completed booking."""
    booking_id = serializers.IntegerField()

    def validate_booking_id(self, value):
        user = self.context['request'].user
        try:
            provider = user.provider_profile
            booking  = Booking.objects.select_related(
                'provider', 'customer', 'category'
            ).get(id=value, provider=provider)
        except Exception:
            raise serializers.ValidationError('Booking not found.')

        if booking.status != 'completed':
            raise serializers.ValidationError(
                'Can only mark cash payment for completed bookings.'
            )

        if booking.payment_status == 'paid':
            raise serializers.ValidationError(
                'This booking is already marked as paid.'
            )

        self._booking = booking
        return value


# ── Withdrawal ────────────────────────────────────────────────────

class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model  = WithdrawalRequest
        fields = [
            'id', 'amount', 'payout_method',
            'upi_id', 'account_holder_name', 'account_number',
            'ifsc_code', 'bank_name',
            'status', 'admin_note',
            'requested_at', 'processed_at',
        ]


class CreateWithdrawalSerializer(serializers.Serializer):
    """Provider requests a withdrawal."""
    amount        = serializers.DecimalField(max_digits=10, decimal_places=2)
    payout_method = serializers.ChoiceField(choices=['bank', 'upi'])

    def validate(self, attrs):
        user    = self.context['request'].user
        profile = user.provider_profile
        wallet  = profile.wallet

        # KYC must be verified
        try:
            if not profile.kyc.kyc_verified:
                raise serializers.ValidationError(
                    'Complete KYC verification before requesting withdrawal.'
                )
        except Exception:
            raise serializers.ValidationError(
                'Complete KYC verification before requesting withdrawal.'
            )

        # payout method must be verified
        payout_method = attrs['payout_method']
        if payout_method == 'bank':
            try:
                if not profile.bank_account.is_verified:
                    raise serializers.ValidationError(
                        'Your bank account is not verified yet.'
                    )
            except Exception:
                raise serializers.ValidationError(
                    'Add and verify your bank account first.'
                )
        elif payout_method == 'upi':
            if not profile.upi_verified:
                raise serializers.ValidationError(
                    'Your UPI ID is not verified yet.'
                )

        # amount must not exceed balance
        amount = attrs['amount']
        if amount <= 0:
            raise serializers.ValidationError(
                'Withdrawal amount must be greater than zero.'
            )

        min_withdrawal = getattr(settings, 'FIXIT_MIN_WITHDRAWAL', 100)
        if amount < min_withdrawal:
            raise serializers.ValidationError(
                f'Minimum withdrawal amount is ₹{min_withdrawal}.'
            )

        if amount > wallet.balance:
            raise serializers.ValidationError(
                f'Insufficient balance. Available: ₹{wallet.balance}.'
            )

        # no pending withdrawal allowed simultaneously
        if WithdrawalRequest.objects.filter(
            provider=profile,
            status__in=['pending', 'approved']
        ).exists():
            raise serializers.ValidationError(
                'You already have a pending withdrawal request.'
            )

        attrs['wallet']   = wallet
        attrs['profile']  = profile
        return attrs

    def create(self, validated_data):
        profile = validated_data['profile']
        wallet  = validated_data['wallet']
        method  = validated_data['payout_method']

        # snapshot payout details at time of request
        upi_id = account_holder = account_number = ifsc = bank_name = ''

        if method == 'upi':
            upi_id = profile.upi_id
        elif method == 'bank':
            bank   = profile.bank_account
            account_holder = bank.account_holder_name
            account_number = bank.account_number
            ifsc           = bank.ifsc_code
            bank_name      = bank.bank_name

        return WithdrawalRequest.objects.create(
            wallet              = wallet,
            provider            = profile,
            amount              = validated_data['amount'],
            payout_method       = method,
            upi_id              = upi_id,
            account_holder_name = account_holder,
            account_number      = account_number,
            ifsc_code           = ifsc,
            bank_name           = bank_name,
            status              = 'pending',
        )


class AdminWithdrawalActionSerializer(serializers.Serializer):
    action     = serializers.ChoiceField(choices=['approve', 'reject', 'process'])
    admin_note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['action'] in ['reject'] and not attrs.get('admin_note', '').strip():
            raise serializers.ValidationError(
                {'admin_note': 'admin_note is required when rejecting.'}
            )
        return attrs