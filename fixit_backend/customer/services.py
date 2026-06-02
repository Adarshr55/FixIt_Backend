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

        services = ProviderService.objects.filter(
            category                  = category,
            verification_status       = 'verified',
            is_active                 = True,
            provider__approval_status = 'approved',
            provider__is_online       = True,
        ).select_related('provider', 'category')

        ranked = self.backend.find_nearby(services, customer_lat, customer_lng)
        return category, ranked