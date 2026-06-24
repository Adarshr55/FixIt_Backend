import hmac
import hashlib
import razorpay
import logging

from decimal          import Decimal
from django.conf      import settings
from django.utils     import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators      import method_decorator

from rest_framework.views       import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response    import Response
from rest_framework             import status

from accounts.permissions import IsPlatformAdmin
from bookings.models      import Booking
from .models              import Payment, ProviderWallet, WalletTransaction, WithdrawalRequest
from .serializers         import (
    PaymentSerializer,
    CreateRazorpayOrderSerializer,
    CashPaymentSerializer,
    ProviderWalletSerializer,
    WithdrawalRequestSerializer,
    CreateWithdrawalSerializer,
    AdminWithdrawalActionSerializer,
)
from notifications.services import (
    notify_payment_received,
    notify_withdrawal_requested,
    notify_withdrawal_approved,
    notify_withdrawal_rejected,
    notify_withdrawal_processed,
    notify_cash_payment_confirmed,
)

logger = logging.getLogger(__name__)

COMMISSION_RATE = Decimal(str(getattr(settings, 'FIXIT_COMMISSION_RATE', 0.10)))


def _get_razorpay_client():
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def _credit_provider_wallet(booking, amount, payment):
    """
    Credit provider wallet after successful payment.
    Creates wallet if it doesn't exist.
    Records two transactions — commission debit and earning credit.
    """
    commission  = (amount * COMMISSION_RATE).quantize(Decimal('0.01'))
    earning     = amount - commission

    wallet, _ = ProviderWallet.objects.get_or_create(provider=booking.provider)

    # credit earning
    wallet.balance      += earning
    wallet.total_earned += earning
    wallet.save(update_fields=['balance', 'total_earned', 'updated_at'])

    WalletTransaction.objects.create(
        wallet           = wallet,
        booking          = booking,
        transaction_type = 'credit',
        amount           = earning,
        balance_after    = wallet.balance,
        description      = (
            f'Earning from Booking#{booking.id} — '
            f'{booking.category.name} '
            f'(after {int(COMMISSION_RATE * 100)}% commission)'
        ),
    )

    return earning, commission


# ── View 1 — Customer creates Razorpay order ──────────────────────

class CreateRazorpayOrderView(APIView):
    """
    POST /api/payments/create-order/

    Customer calls this after booking is completed.
    Returns Razorpay order_id + key for frontend checkout modal.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can initiate payments.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CreateRazorpayOrderSerializer(
            data=request.data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        booking = serializer._booking
        amount  = booking.final_amount

        # amount in paise for Razorpay
        amount_paise = int(amount * 100)

        try:
            client = _get_razorpay_client()
            order  = client.order.create({
                'amount':   amount_paise,
                'currency': 'INR',
                'receipt':  f'booking_{booking.id}',
                'notes': {
                    'booking_id':   str(booking.id),
                    'customer_id':  str(request.user.id),
                    'provider_id':  str(booking.provider.id),
                },
            })
        except Exception as e:
            logger.error(f'Razorpay order creation failed: {e}')
            return Response(
                {'error': 'Payment service unavailable. Try again.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        commission  = (amount * COMMISSION_RATE).quantize(Decimal('0.01'))
        earning     = amount - commission

        # create or update Payment record
        payment, _ = Payment.objects.update_or_create(
            booking=booking,
            defaults={
                'customer':            request.user,
                'provider':            booking.provider,
                'method':              'razorpay',
                'status':              'pending',
                'amount':              amount,
                'platform_commission': commission,
                'provider_earning':    earning,
                'razorpay_order_id':   order['id'],
            }
        )

        return Response({
            'razorpay_order_id': order['id'],
            'razorpay_key':      settings.RAZORPAY_KEY_ID,
            'amount':            amount_paise,
            'currency':          'INR',
            'booking_id':        booking.id,
            'provider_name':     booking.provider.full_name,
            'category':          booking.category.name,
        })

class VerifyRazorpayPaymentView(APIView):
    """
    POST /api/payments/verify/

    Customer calls this to verify Razorpay checkout payment signature synchronously.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        booking_id = request.data.get('booking_id')
        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature = request.data.get('razorpay_signature')

        if not all([booking_id, razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return Response(
                {'error': 'Missing required payment details.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not (request.user == booking.customer or request.user.role == 'admin'):
            return Response({'error': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)

        if booking.payment_status == 'paid':
            return Response({'status': 'ok', 'message': 'Payment already verified.'})

        # Verify signature
        msg = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode('utf-8'),
            msg.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, razorpay_signature):
            logger.warning(f'Razorpay checkout signature mismatch for Booking#{booking.id}')
            return Response(
                {'error': 'Invalid payment signature. Verification failed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create Payment record
        try:
            payment = Payment.objects.get(booking=booking, razorpay_order_id=razorpay_order_id)
        except Payment.DoesNotExist:
            commission = (booking.final_amount * COMMISSION_RATE).quantize(Decimal('0.01'))
            earning = booking.final_amount - commission
            payment = Payment.objects.create(
                booking=booking,
                customer=booking.customer,
                provider=booking.provider,
                method='razorpay',
                status='pending',
                amount=booking.final_amount,
                platform_commission=commission,
                provider_earning=earning,
                razorpay_order_id=razorpay_order_id,
            )

        if payment.status == 'paid':
            booking.payment_status = 'paid'
            booking.payment_method = 'razorpay'
            booking.save(update_fields=['payment_status', 'payment_method', 'updated_at'])
            return Response({'status': 'ok', 'message': 'Payment already processed.'})

        payment.razorpay_payment_id = razorpay_payment_id
        payment.status = 'paid'
        payment.paid_at = timezone.now()
        payment.save(update_fields=['razorpay_payment_id', 'status', 'paid_at', 'updated_at'])

        booking.payment_status = 'paid'
        booking.payment_method = 'razorpay'
        booking.save(update_fields=['payment_status', 'payment_method', 'updated_at'])

        earning, commission = _credit_provider_wallet(booking, payment.amount, payment)
        notify_payment_received(payment, earning)

        logger.info(f'Payment verified synchronously: Booking#{booking.id} | Amount: ₹{payment.amount}')
        return Response({'status': 'ok', 'message': 'Payment verified and captured successfully.'})


# ── View 2 — Razorpay webhook ─────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class RazorpayWebhookView(APIView):
    """
    POST /api/payments/webhook/

    Razorpay posts payment events here.
    MUST verify signature before crediting anything.
    No authentication required — Razorpay calls this directly.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        payload   = request.body
        signature = request.headers.get('X-Razorpay-Signature', '')
        secret    = settings.RAZORPAY_WEBHOOK_SECRET

        # verify signature
        expected = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            logger.warning('Razorpay webhook signature mismatch')
            return Response(
                {'error': 'Invalid signature.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            import json
            data       = json.loads(payload)
            event      = data.get('event')
            payment_data = data.get('payload', {}).get('payment', {}).get('entity', {})
            order_id   = payment_data.get('order_id')
            payment_id = payment_data.get('id')
        except Exception as e:
            logger.error(f'Webhook parse error: {e}')
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if event != 'payment.captured':
            # acknowledge other events without processing
            return Response({'status': 'ignored'})

        try:
            payment = Payment.objects.select_related(
                'booking__provider__user',
                'booking__category',
                'customer',
            ).get(razorpay_order_id=order_id)
        except Payment.DoesNotExist:
            logger.error(f'Payment not found for order: {order_id}')
            return Response(status=status.HTTP_404_NOT_FOUND)

        if payment.status == 'paid':
            # idempotent — already processed
            return Response({'status': 'already_processed'})

        # update payment record
        payment.razorpay_payment_id = payment_id
        payment.status              = 'paid'
        payment.paid_at             = timezone.now()
        payment.save(update_fields=[
            'razorpay_payment_id', 'status', 'paid_at', 'updated_at'
        ])

        # update booking payment status
        booking = payment.booking
        booking.payment_status = 'paid'
        booking.payment_method = 'razorpay'
        booking.save(update_fields=['payment_status', 'payment_method', 'updated_at'])

        # credit provider wallet
        earning, commission = _credit_provider_wallet(
            booking, payment.amount, payment
        )

        # notify both parties
        notify_payment_received(payment, earning)

        logger.info(
            f'Payment captured: Booking#{booking.id} '
            f'₹{payment.amount} | Provider earning: ₹{earning}'
        )

        return Response({'status': 'ok'})


# ── View 3 — Cash payment (provider marks collected) ──────────────

class CashPaymentView(APIView):
    """
    POST /api/payments/cash/

    Provider marks cash as collected.
    Commission deducted from provider wallet balance.
    If wallet balance goes negative, it's recorded as debt.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can mark cash payments.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CashPaymentSerializer(
            data=request.data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        booking = serializer._booking
        amount  = booking.final_amount

        commission = (amount * COMMISSION_RATE).quantize(Decimal('0.01'))
        earning    = amount - commission

        # create payment record
        payment = Payment.objects.create(
            booking            = booking,
            customer           = booking.customer,
            provider           = booking.provider,
            method             = 'cash',
            status             = 'paid',
            amount             = amount,
            platform_commission= commission,
            provider_earning   = earning,
            paid_at            = timezone.now(),
        )

        # update booking
        booking.payment_status = 'paid'
        booking.payment_method = 'cash'
        booking.save(update_fields=['payment_status', 'payment_method', 'updated_at'])

        # for cash: deduct commission from wallet, don't credit earning
        # provider already has the cash in hand
        wallet, _ = ProviderWallet.objects.get_or_create(provider=booking.provider)
        wallet.balance      -= commission
        wallet.total_earned += earning
        wallet.save(update_fields=['balance', 'total_earned', 'updated_at'])

        WalletTransaction.objects.create(
            wallet           = wallet,
            booking          = booking,
            transaction_type = 'commission',
            amount           = commission,
            balance_after    = wallet.balance,
            description      = (
                f'Commission deducted for cash Booking#{booking.id} — '
                f'{booking.category.name}'
            ),
        )

        notify_cash_payment_confirmed(payment, earning)

        return Response({
            'message':    'Cash payment confirmed.',
            'amount':     str(amount),
            'commission': str(commission),
            'earning':    str(earning),
            'payment':    PaymentSerializer(payment).data,
        })


# ── View 4 — Provider wallet ──────────────────────────────────────

class ProviderWalletView(APIView):
    """
    GET /api/payments/wallet/

    Provider sees their balance and last 20 transactions.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access wallet.'},
                status=status.HTTP_403_FORBIDDEN
            )

        wallet, _ = ProviderWallet.objects.get_or_create(
            provider=request.user.provider_profile
        )

        # return last 20 transactions only
        transactions = wallet.transactions.order_by('-created_at')[:20]
        data = ProviderWalletSerializer(wallet).data
        data['transactions'] = [
            {
                'id':               t.id,
                'transaction_type': t.transaction_type,
                'amount':           str(t.amount),
                'balance_after':    str(t.balance_after),
                'description':      t.description,
                'created_at':       t.created_at.isoformat(),
            }
            for t in transactions
        ]
        return Response(data)


# ── View 5 — Provider requests withdrawal ────────────────────────

class WithdrawalRequestView(APIView):
    """
    POST /api/payments/withdraw/    — provider creates request
    GET  /api/payments/withdraw/    — provider sees their requests
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )

        requests_qs = WithdrawalRequest.objects.filter(
            provider=request.user.provider_profile
        ).order_by('-requested_at')

        return Response(
            WithdrawalRequestSerializer(requests_qs, many=True).data
        )

    def post(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can request withdrawals.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CreateWithdrawalSerializer(
            data=request.data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        withdrawal = serializer.save()
        notify_withdrawal_requested(withdrawal)

        return Response({
            'message':    'Withdrawal request submitted. Admin will process within 24-48 hours.',
            'withdrawal': WithdrawalRequestSerializer(withdrawal).data,
        }, status=status.HTTP_201_CREATED)


# ── View 6 — Admin manages withdrawals ───────────────────────────

class AdminWithdrawalListView(APIView):
    """
    GET /api/payments/admin/withdrawals/
    GET /api/payments/admin/withdrawals/?status=pending
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        withdrawals = WithdrawalRequest.objects.select_related(
            'provider', 'wallet'
        ).all()

        status_filter = request.query_params.get('status')
        if status_filter:
            withdrawals = withdrawals.filter(status=status_filter)

        return Response({
            'count':   withdrawals.count(),
            'results': WithdrawalRequestSerializer(withdrawals, many=True).data,
        })


class AdminWithdrawalActionView(APIView):
    """
    PATCH /api/payments/admin/withdrawals/{pk}/

    approve  → admin confirms they will process it
    reject   → admin rejects with reason, balance refunded
    process  → admin confirms money has been sent
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def patch(self, request, pk):
        try:
            withdrawal = WithdrawalRequest.objects.select_related(
                'wallet', 'provider__user'
            ).get(pk=pk)
        except WithdrawalRequest.DoesNotExist:
            return Response(
                {'error': 'Withdrawal request not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = AdminWithdrawalActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action     = serializer.validated_data['action']
        admin_note = serializer.validated_data.get('admin_note', '')

        if action == 'approve':
            if withdrawal.status != 'pending':
                return Response(
                    {'error': 'Only pending requests can be approved.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Debit wallet balance on approval
            wallet = withdrawal.wallet
            if wallet.balance < withdrawal.amount:
                return Response(
                    {'error': f'Insufficient balance in provider wallet. Available: ₹{wallet.balance}.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            wallet.balance -= withdrawal.amount
            wallet.save(update_fields=['balance', 'updated_at'])

            WalletTransaction.objects.create(
                wallet           = wallet,
                transaction_type = 'debit',
                amount           = withdrawal.amount,
                balance_after    = wallet.balance,
                description      = (
                    f'Withdrawal#{withdrawal.id} approved — '
                    f'₹{withdrawal.amount} pending transfer to '
                    f'{withdrawal.upi_id or withdrawal.account_number}'
                ),
            )

            withdrawal.status     = 'approved'
            withdrawal.admin_note = admin_note
            withdrawal.processed_by = request.user
            withdrawal.save(update_fields=['status', 'admin_note', 'processed_by', 'processed_at'])
            notify_withdrawal_approved(withdrawal)
            message = 'Withdrawal approved and amount debited from wallet.'

        elif action == 'reject':
            if withdrawal.status not in ['pending', 'approved']:
                return Response(
                    {'error': 'Cannot reject this request.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Refund ONLY if it was already approved (and thus debited)
            if withdrawal.status == 'approved':
                wallet = withdrawal.wallet
                wallet.balance += withdrawal.amount
                wallet.save(update_fields=['balance', 'updated_at'])

                WalletTransaction.objects.create(
                    wallet           = wallet,
                    transaction_type = 'refund',
                    amount           = withdrawal.amount,
                    balance_after    = wallet.balance,
                    description      = f'Withdrawal#{withdrawal.id} rejected — amount refunded to wallet.',
                )
                message = 'Withdrawal rejected and amount refunded.'
            else:
                message = 'Withdrawal request rejected.'

            withdrawal.status       = 'rejected'
            withdrawal.admin_note   = admin_note
            withdrawal.processed_by = request.user
            withdrawal.processed_at = timezone.now()
            withdrawal.save(update_fields=[
                'status', 'admin_note', 'processed_by', 'processed_at'
            ])
            notify_withdrawal_rejected(withdrawal)

        elif action == 'process':
            if withdrawal.status != 'approved':
                return Response(
                    {'error': 'Only approved requests can be marked as processed.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Increment total_withdrawn only (balance was already deducted on approval)
            wallet = withdrawal.wallet
            wallet.total_withdrawn  += withdrawal.amount
            wallet.save(update_fields=['total_withdrawn', 'updated_at'])

            withdrawal.status       = 'processed'
            withdrawal.admin_note   = admin_note
            withdrawal.processed_by = request.user
            withdrawal.processed_at = timezone.now()
            withdrawal.save(update_fields=[
                'status', 'admin_note', 'processed_by', 'processed_at'
            ])
            notify_withdrawal_processed(withdrawal)
            message = 'Withdrawal marked as processed.'

        return Response({
            'message':    message,
            'withdrawal': WithdrawalRequestSerializer(withdrawal).data,
        })