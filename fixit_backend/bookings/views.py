from django.utils               import timezone
from rest_framework.views       import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response    import Response
from rest_framework             import status
from .geocoding import geocode_address
from accounts.permissions import IsPlatformAdmin
from .models      import Booking, BookingStatusHistory
from .serializers import (
    BookingSerializer,
    BookingListSerializer,
    BookingCreateSerializer,
    BookingStatusUpdateSerializer,
)
from .tasks import auto_cancel_booking
from notifications.services import (
    notify_booking_requested,notify_booking_accepted,
    notify_booking_rejected,notify_booking_cancelled,
    notify_booking_on_the_way,notify_booking_arrived,
    notify_booking_completed,notify_booking_disputed,
    notify_booking_reminder
)

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


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
    

def _push_booking_event(booking, event_type):
    """Push a booking event to the provider's live booking stream."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'provider_{booking.provider_id}_bookings',
        {
            'type':       'booking_event',   # maps to booking_event() handler in the consumer
            'event_type': event_type,
            'booking':    BookingListSerializer(booking).data,
        }
    )


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
            notify_booking_requested(booking)
            _push_booking_event(booking,'created')
            # NOTE: auto_cancel Celery task goes here in Phase 3
            # auto_cancel_booking.apply_async(args=[booking.id], countdown=120)
                # ── AI category mismatch hint ──────────────────────────
            ai_hint = None
            try:
                from ai_engine.search_service import detect_category_mismatch
                mismatch = detect_category_mismatch(
                    issue_description    = booking.issue_description,
                    selected_category_id = booking.category_id,
                    )
                if mismatch.get('mismatch'):
                    ai_hint = mismatch
            except Exception:
                pass  # never block booking creation for AI errors

            if booking.booking_type=='instant':
                auto_cancel_booking.apply_async(
                     args     = [booking.id],
                     countdown = 120
                )

            if booking.booking_type=='scheduled' and booking.scheduled_at:
                from .tasks import send_scheduled_booking_reminder
                from django.utils import timezone

                reminder_time = booking.scheduled_at - timezone.timedelta(hours=1)

                if reminder_time > timezone.now():
                    send_scheduled_booking_reminder.apply_async(
                    args    = [booking.id],
                    eta     = reminder_time
                )

            return Response({
                    'message': 'Booking request sent. Waiting for provider.',
                    'booking': BookingSerializer(booking, context={'request': request}).data,
                    'ai_hint': ai_hint,  # ← None if no mismatch, dict if mismatch
                }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
          


# bookings/views.py — add this view

class GeocodeAddressView(APIView):
    """
    POST /api/bookings/geocode/
    Lets the frontend preview where an address will pin on the map
    before the customer confirms the booking.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        address = request.data.get('address', '').strip()
        if not address:
            return Response(
                {'error': 'address is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        coords = geocode_address(address)
        if not coords:
            return Response(
                {'error': 'Could not locate this address. Try adding city and state.'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )

        return Response({
            'address':   address,
            'latitude':  coords['latitude'],
            'longitude': coords['longitude'],
        })


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
        booking_type_filter = request.query_params.get('booking_type') 
        if status_filter:
            bookings = bookings.filter(status=status_filter)
        if booking_type_filter:                                             # ← add
            bookings = bookings.filter(booking_type=booking_type_filter)# ←

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
        return Response(BookingSerializer(booking, context={'request': request}).data)


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
            _push_booking_event(booking, 'completed_review_prompt')

        elif new_status == 'cancelled':
            booking.cancelled_by  = role
            booking.cancel_reason = data.get('cancel_reason', '')

        elif new_status == 'rejected':
            booking.reject_reason = data.get('reject_reason', '')
         

        elif new_status == 'disputed':
            booking.dispute_reason = data.get('dispute_reason', '')

        booking.save()
        _push_booking_event(booking,'new_status')
        if new_status == 'accepted':
            notify_booking_accepted(booking)

        elif new_status == 'rejected':
            notify_booking_rejected(booking)

        elif new_status == 'cancelled':
            notify_booking_cancelled(booking)

        elif new_status == 'on_the_way':
            notify_booking_on_the_way(booking)

        elif new_status == 'arrived':
            notify_booking_arrived(booking)

        elif new_status == 'completed':
            notify_booking_completed(booking)

        elif new_status == 'disputed':
            notify_booking_disputed(booking)

        note = (
            data.get('cancel_reason') or data.get('reject_reason') or
            data.get('dispute_reason') or data.get('note', '')
        )
        _log_status(booking, new_status, request.user, note)

        # NOTE: WebSocket notification goes here in Phase 3
        # notify_booking_update(booking)

        return Response({
            'message': f'Booking status updated to {new_status}.',
            'booking': BookingSerializer(booking, context={'request': request}).data,
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
            notify_booking_cancelled(booking)
            _log_status(booking, 'cancelled', request.user, f'Admin force-cancel: {reason}')
            return Response({'message': 'Booking force-cancelled.'})

        elif action == 'resolve_dispute':
            note = request.data.get('note', '').strip()
            if not note:
                return Response({'error': 'note is required for dispute resolution.'}, status=status.HTTP_400_BAD_REQUEST)
            booking.status = 'completed'
            booking.save()
            if booking.service:
                booking.service.total_jobs += 1
                booking.service.save(update_fields=['total_jobs', 'updated_at'])    
            _log_status(booking, 'completed', request.user, f'Dispute resolved: {note}')
            notify_booking_completed(booking) 
            return Response({'message': 'Dispute resolved, booking marked completed.'})

        return Response(
            {'error': 'action must be "force_cancel" or "resolve_dispute".'},
            status=status.HTTP_400_BAD_REQUEST
        )