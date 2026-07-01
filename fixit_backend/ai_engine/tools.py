"""
Tool functions — the actual actions the AI can perform.
Every function receives `request` so we always know
who is calling and enforce the same permission rules
as the normal REST API.
"""

import logging

logger = logging.getLogger(__name__)


def geocode_location(address: str) -> dict:
    """
    Convert a place name to coordinates.
    Used when AI needs to understand "Kakkanad", "near Infopark" etc.
    """
    from bookings.geocoding import geocode_address

    coords = geocode_address(address)
    if not coords:
        return {'success': False, 'error': f'Could not find location: {address}'}

    return {
        'success':   True,
        'address':   address,
        'latitude':  coords['latitude'],
        'longitude': coords['longitude'],
    }

def search_providers(
    category_name: str,
    lat: float = None,
    lng: float = None,
    booking_type: str = 'instant',
) -> dict:
    from services.models import ServiceCategory, ProviderService
    from bookings.models import Booking
    from django.db.models import Q

    try:
        category = ServiceCategory.objects.filter(
            name__icontains=category_name, is_active=True
        ).first()

        if not category:
            return {
                'success': False,
                'error':   f'No service category found matching "{category_name}".'
            }

        busy_provider_ids = Booking.objects.filter(
            Q(status__in=['on_the_way', 'arrived', 'in_progress']) |
            Q(booking_type='instant', status='accepted')
        ).values_list('provider_id', flat=True)

        services = ProviderService.objects.filter(
            category                  = category,
            verification_status       = 'verified',
            is_active                 = True,
            provider__approval_status = 'approved',
            provider__is_online       = True,
        ).exclude(
            provider_id__in=busy_provider_ids
        ).select_related('provider', 'category')

        if lat and lng:
            from customer.location_backends import HaversineLocationBackend
            backend = HaversineLocationBackend()
            ranked  = backend.find_nearby(services, float(lat), float(lng))
            results = ranked[:5]

            providers_list = [{
                'service_id':   item['service'].id,
                'rating':       float(item['service'].provider.overall_rating or 0),
                'distance_km':  item['distance_km'],
                'base_charge':  float(item['service'].base_charge),
                'total_jobs':   item['service'].total_jobs,
            } for item in results]
        else:
            services = services.order_by('-provider__overall_rating')[:5]
            providers_list = [{
                'service_id':   s.id,
                'rating':       float(s.provider.overall_rating or 0),
                'distance_km':  None,
                'base_charge':  float(s.base_charge),
                'total_jobs':   s.total_jobs,
            } for s in services]

        # pricing context — reused from context_builder
        from .context_builder import build_pricing_context
        pricing = build_pricing_context(category.id)

        return {
            'success':   True,
            'category':  category.name,
            'count':     len(providers_list),
            'providers': providers_list,
            'pricing':   pricing,
        }

    except Exception as e:
        logger.error(f'search_providers tool failed: {e}')
        return {'success': False, 'error': 'Search failed. Try again.'}

def get_provider_detail(service_id: int) -> dict:
    """Get full details about one specific provider service."""
    from services.models import ProviderService

    try:
        service = ProviderService.objects.select_related(
            'provider', 'category'
        ).get(
            pk=service_id,
            verification_status='verified',
            is_active=True,
        )

        return {
            'success':          True,
            'service_id':       service.id,
            'provider_name':    service.provider.full_name,
            'category':         service.category.name,
            'rating':           float(service.provider.overall_rating or 0),
            'base_charge':      float(service.base_charge),
            'hourly_rate':      float(service.hourly_rate),
            'skills':           service.skills,
            'total_jobs':       service.total_jobs,
            'is_online':        service.provider.is_online,
            'experience_years': service.provider.experience_years,
        }

    except ProviderService.DoesNotExist:
        return {'success': False, 'error': 'Provider service not found.'}
    except Exception as e:
        logger.error(f'get_provider_detail tool failed: {e}')
        return {'success': False, 'error': 'Could not fetch provider details.'}


def create_booking(
    request,
    service_id: int,
    address: str,
    issue_description: str,
    booking_type: str = 'instant',
    scheduled_at: str = None,
) -> dict:
    """
    Create a real booking — same validation as the normal API.
    request.user must be authenticated customer.
    """
    if not request or not request.user.is_authenticated:
        return {'success': False, 'error': 'You must be logged in to book a service.'}

    if not request.user.is_customer:
        return {'success': False, 'error': 'Only customers can create bookings.'}

    from bookings.serializers import BookingCreateSerializer
    from notifications.services import notify_booking_requested

    data = {
        'service_id':        service_id,
        'booking_type':      booking_type,
        'issue_description': issue_description,
        'customer_address':  address,
    }
    if scheduled_at:
        data['scheduled_at'] = scheduled_at

    serializer = BookingCreateSerializer(data=data, context={'request': request})

    if not serializer.is_valid():
        return {
            'success': False,
            'error':   '; '.join([str(v) for v in serializer.errors.values()]),
        }

    booking = serializer.save()
    notify_booking_requested(booking)

    # trigger auto-cancel for instant bookings
    if booking.booking_type == 'instant':
        from bookings.tasks import auto_cancel_booking
        auto_cancel_booking.apply_async(args=[booking.id], countdown=120)

    return {
        'success':    True,
        'booking_id': booking.id,
        'status':     booking.status,
        'message':    'Booking created successfully. Waiting for provider response.',
    }


def get_my_bookings(request, status_filter: str = None) -> dict:
    """List the authenticated customer's own bookings — never other users' data."""
    if not request or not request.user.is_authenticated:
        return {'success': False, 'error': 'You must be logged in.'}

    from bookings.models import Booking

    bookings = Booking.objects.filter(
        customer=request.user
    ).select_related('provider', 'category').order_by('-created_at')[:10]

    if status_filter:
        bookings = bookings.filter(status=status_filter)

    results = [{
        'booking_id':   b.id,
        'category':     b.category.name if b.category else '',
        'provider':     b.provider.full_name if b.provider else 'Not assigned',
        'status':       b.status,
        'final_amount': float(b.final_amount) if b.final_amount else None,
        'created_at':   b.created_at.isoformat(),
    } for b in bookings]

    return {'success': True, 'count': len(results), 'bookings': results}


def cancel_booking(request, booking_id: int, reason: str) -> dict:
    """Cancel a booking — only the owning customer can do this."""
    if not request or not request.user.is_authenticated:
        return {'success': False, 'error': 'You must be logged in.'}

    from bookings.models import Booking
    from bookings.serializers import BookingStatusUpdateSerializer
    from notifications.services import notify_booking_cancelled

    try:
        booking = Booking.objects.get(pk=booking_id, customer=request.user)
    except Booking.DoesNotExist:
        return {'success': False, 'error': 'Booking not found or does not belong to you.'}

    serializer = BookingStatusUpdateSerializer(
        data    = {'new_status': 'cancelled', 'cancel_reason': reason},
        context = {'request': request, 'booking': booking}
    )

    if not serializer.is_valid():
        return {
            'success': False,
            'error':   '; '.join([str(v) for v in serializer.errors.values()]),
        }

    booking.status        = 'cancelled'
    booking.cancelled_by  = 'customer'
    booking.cancel_reason = reason
    booking.save()
    notify_booking_cancelled(booking)

    return {'success': True, 'message': f'Booking #{booking_id} has been cancelled.'}


def get_booking_status(request, booking_id: int) -> dict:
    """Check status of a specific booking — owner only."""
    if not request or not request.user.is_authenticated:
        return {'success': False, 'error': 'You must be logged in.'}

    from bookings.models import Booking

    try:
        booking = Booking.objects.select_related('provider', 'category').get(
            pk=booking_id, customer=request.user
        )
    except Booking.DoesNotExist:
        return {'success': False, 'error': 'Booking not found.'}

    return {
        'success':      True,
        'booking_id':   booking.id,
        'status':       booking.status,
        'category':     booking.category.name if booking.category else '',
        'provider':     booking.provider.full_name if booking.provider else 'Not assigned',
        'is_active':    booking.is_active,
        'final_amount': float(booking.final_amount) if booking.final_amount else None,
    }


def get_category_list() -> dict:
    """List all available service categories."""
    from services.models import ServiceCategory

    categories = ServiceCategory.objects.filter(is_active=True).values_list(
        'name', flat=True
    )
    return {'success': True, 'categories': list(categories)}