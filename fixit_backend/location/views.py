from django.utils               import timezone
from rest_framework.views       import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response    import Response
from rest_framework             import status

from bookings.models  import Booking
from .models          import ProviderLocation
from .serializers     import ProviderLocationUpdateSerializer, ProviderLocationSerializer


class ProviderLocationUpdateView(APIView):
    """
    POST /api/location/update/

    Provider sends their current GPS coordinates.
    Called by provider app every 10-15 seconds while on active booking.
    Creates or updates single ProviderLocation row (upsert).

    Phase 5: Replace with WebSocket push — no polling needed.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can update location.'},
                status=status.HTTP_403_FORBIDDEN
            )

        profile = request.user.provider_profile

        if not profile.is_approved:
            return Response(
                {'error': 'Provider must be approved to share location.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ProviderLocationUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data       = serializer.validated_data
        booking_id = data.get('booking_id')
        booking    = None

        # validate booking belongs to this provider and is active
        if booking_id:
            try:
                booking = Booking.objects.get(
                    pk       = booking_id,
                    provider = profile,
                    status__in = ['on_the_way', 'arrived'],
                )
            except Booking.DoesNotExist:
                return Response(
                    {'error': 'Booking not found or not active for this provider.'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # upsert — one row per provider, updated in place
        location, _ = ProviderLocation.objects.update_or_create(
            provider = profile,
            defaults = {
                'latitude':  data['latitude'],
                'longitude': data['longitude'],
                'booking':   booking,
            }
        )

        return Response({
            'message':    'Location updated.',
            'latitude':   str(location.latitude),
            'longitude':  str(location.longitude),
            'updated_at': location.updated_at,
        })


class CustomerTrackProviderView(APIView):
    """
    GET /api/location/booking/{booking_id}/

    Customer polls provider's live location during active booking.
    Called every 10-15 seconds from customer frontend.

    Returns provider's last known position.
    Phase 5: Replace with WebSocket stream — no polling needed.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, booking_id):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can track providers.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # verify booking belongs to this customer
        try:
            booking = Booking.objects.get(
                pk       = booking_id,
                customer = request.user,
            )
        except Booking.DoesNotExist:
            return Response(
                {'error': 'Booking not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # only track during active stages
        if booking.status not in ['on_the_way', 'arrived']:
            return Response({
                'message':   f'Tracking not available — booking status is {booking.status}.',
                'status':    booking.status,
                'location':  None,
            })

        try:
            location = booking.provider.live_location
            serializer = ProviderLocationSerializer(location)
            return Response({
                'status':   booking.status,
                'location': serializer.data,
            })
        except ProviderLocation.DoesNotExist:
            return Response({
                'message':  'Provider has not shared location yet.',
                'status':   booking.status,
                'location': None,
            })


class ProviderCurrentLocationView(APIView):
    """
    GET /api/location/me/

    Provider checks their own last recorded location.
    Useful for provider dashboard to confirm GPS is being received.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            location = request.user.provider_profile.live_location
            return Response(ProviderLocationSerializer(location).data)
        except ProviderLocation.DoesNotExist:
            return Response({
                'message':  'No location recorded yet.',
                'location': None,
            })