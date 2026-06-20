from services.models             import ProviderService, ServiceCategory
from .location_backends          import HaversineLocationBackend


class ProviderDiscoveryService:
    """
    Business logic layer — owns the provider search and ranking.
    Views call this. Views never touch ProviderService queries directly.

    To swap to PostGIS in Phase 5:
        ProviderDiscoveryService(backend=PostGISLocationBackend())
    or set it globally in settings:
        LOCATION_BACKEND = 'customer.location_backends.PostGISLocationBackend'
    """

    def __init__(self, backend=None):
        self.backend = backend or HaversineLocationBackend()

    def get_nearby_providers(self, category_id, customer_lat, customer_lng):
        """
        Returns (category, ranked_results)
        ranked_results = [{ service, distance_km, score }, ...]
        """
        try:
            category = ServiceCategory.objects.get(pk=category_id, is_active=True)
        except ServiceCategory.DoesNotExist:
            raise

        from bookings.models import Booking
        from django.db.models import Q

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

        ranked = self.backend.find_nearby(services, customer_lat, customer_lng)
        return category, ranked