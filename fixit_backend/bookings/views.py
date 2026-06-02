from django.utils               import timezone
from rest_framework.views       import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response    import Response
from rest_framework             import status

from accounts.permissions import IsPlatformAdmin
from .models      import Booking, BookingStatusHistory
from .serializers import (
    BookingSerializer,
    BookingListSerializer,
    BookingCreateSerializer,
    BookingStatusUpdateSerializer,
)


def _log_status(booking, new_status, user, note=''):
    BookingStatusHistory.objects.create(
        booking    = booking,
        status     = new_status,
        changed_by = user,
        note       = note,
    )


def _get_provider_booking(user, pk):
    try:
        provider = user.provider_profile
        return Booking.objects.get(id=pk, provider=provider)
    except Exception:
        return None


def _get_customer_booking(user, pk):
    try:
        return Booking.objects.get(id=pk, customer=user)
    except Booking.DoesNotExist:
        return None


# ── Customer ──────────────────────────────────────────────────────

class CustomerBookingListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_customer:
            return Response({'error': 'Only customers can access this.'}, status=status.HTTP_403_FORBIDDEN)

        bookings = Booking.objects.filter(
            customer=request.user
        ).select_related('provider', 'category')

        status_filter = request.query_params.get('status')
        if status_filter:
            bookings = bookings.filter(status=status_filter)

        return Response(BookingListSerializer(bookings, many=True).data)

    def post(self, request):
        if not request.user.is_customer:
            return Response({'error': 'Only customers can create bookings.'}, status=status.HTTP_403_FORBIDDEN)

        if not request.user.is_profile_complete:
            return Response(
                {'error': 'Complete your profile before booking.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = BookingCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            booking = serializer.save()
            # NOTE: auto_cancel Celery task goes here in Phase 3
            # auto_cancel_booking.apply_async(args=[booking.id], countdown=120)
            return Response({
                'message': 'Booking request sent. Waiting for provider.',
                'booking': BookingSerializer(booking).data,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Provider ──────────────────────────────────────────────────────

class ProviderBookingListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_provider:
            return Response({'error': 'Only providers can access this.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            provider = request.user.provider_profile
        except Exception:
            return Response({'error': 'Complete your profile first.'}, status=status.HTTP_404_NOT_FOUND)

        bookings = Booking.objects.filter(
            provider=provider
        ).select_related('customer', 'category')

        status_filter = request.query_params.get('status')
        if status_filter:
            bookings = bookings.filter(status=status_filter)

        return Response(BookingListSerializer(bookings, many=True).data)


# ── Booking detail ────────────────────────────────────────────────

class BookingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_booking(self, request, pk):
        user = request.user
        if user.is_customer:
            return _get_customer_booking(user, pk)
        if user.is_provider:
            return _get_provider_booking(user, pk)
        # admin can see any booking
        if user.is_admin_user:
            try:
                return Booking.objects.get(pk=pk)
            except Booking.DoesNotExist:
                return None
        return None

    def get(self, request, pk):
        booking = self._get_booking(request, pk)
        if not booking:
            return Response({'error': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(BookingSerializer(booking).data)


# ── Status update — single view handles all transitions ──────────

class BookingStatusUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        user = request.user

        # get booking depending on role
        if user.is_customer:
            booking = _get_customer_booking(user, pk)
        elif user.is_provider:
            booking = _get_provider_booking(user, pk)
        else:
            return Response({'error': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)

        if not booking:
            return Response({'error': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = BookingStatusUpdateSerializer(
            data    = request.data,
            context = {'request': request, 'booking': booking}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data       = serializer.validated_data
        new_status = data['new_status']
        role       = data['role']
        now        = timezone.now()

        booking.status = new_status

        if new_status == 'accepted':
            booking.accepted_at = now

        elif new_status == 'in_progress':
            booking.started_at = now

        elif new_status == 'completed':
            booking.completed_at = now
            booking.final_amount = data.get('final_amount')
            # increment service job count — feeds AI ranking later
            if booking.service:
                booking.service.total_jobs += 1
                booking.service.save(update_fields=['total_jobs', 'updated_at'])

        elif new_status == 'cancelled':
            booking.cancelled_by  = role
            booking.cancel_reason = data.get('cancel_reason', '')

        elif new_status == 'rejected':
            booking.reject_reason = data.get('reject_reason', '')

        elif new_status == 'disputed':
            booking.dispute_reason = data.get('dispute_reason', '')

        booking.save()

        note = (
            data.get('cancel_reason') or data.get('reject_reason') or
            data.get('dispute_reason') or data.get('note', '')
        )
        _log_status(booking, new_status, request.user, note)

        # NOTE: WebSocket notification goes here in Phase 3
        # notify_booking_update(booking)

        return Response({
            'message': f'Booking status updated to {new_status}.',
            'booking': BookingSerializer(booking).data,
        })


# ── Admin ─────────────────────────────────────────────────────────

class AdminBookingListView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        bookings = Booking.objects.select_related(
            'customer', 'provider', 'category'
        ).all()

        status_filter = request.query_params.get('status')
        if status_filter:
            bookings = bookings.filter(status=status_filter)

        return Response({
            'count':   bookings.count(),
            'results': BookingListSerializer(bookings, many=True).data,
        })


class AdminBookingActionView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def patch(self, request, pk):
        try:
            booking = Booking.objects.get(pk=pk)
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get('action')

        if action == 'force_cancel':
            reason = request.data.get('cancel_reason', '').strip()
            if not reason:
                return Response({'error': 'cancel_reason is required.'}, status=status.HTTP_400_BAD_REQUEST)
            booking.status       = 'cancelled'
            booking.cancelled_by = 'system'
            booking.cancel_reason = reason
            booking.save()
            _log_status(booking, 'cancelled', request.user, f'Admin force-cancel: {reason}')
            return Response({'message': 'Booking force-cancelled.'})

        elif action == 'resolve_dispute':
            note = request.data.get('note', '').strip()
            if not note:
                return Response({'error': 'note is required for dispute resolution.'}, status=status.HTTP_400_BAD_REQUEST)
            booking.status = 'completed'
            booking.save()
            _log_status(booking, 'completed', request.user, f'Dispute resolved: {note}')
            return Response({'message': 'Dispute resolved, booking marked completed.'})

        return Response(
            {'error': 'action must be "force_cancel" or "resolve_dispute".'},
            status=status.HTTP_400_BAD_REQUEST
        )