from rest_framework.views       import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response    import Response
from rest_framework             import status

from services.models import ServiceCategory, ProviderService
from .serializers    import (
    CategoryCardSerializer,
    ProviderCardSerializer,
    ProviderDetailSerializer,
)
from .services import ProviderDiscoveryService
from .location_backends import HaversineLocationBackend


class CustomerCategoryListView(APIView):
    """
    GET /api/customer/categories/
    GET /api/customer/categories/?group=home
    GET /api/customer/categories/?group=automotive
    Public — no login needed to browse.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        categories = ServiceCategory.objects.filter(is_active=True)
        group = request.query_params.get('group')
        if group:
            categories = categories.filter(group=group)
        return Response(CategoryCardSerializer(categories, many=True, context={'request': request}).data)


class CustomerProviderListView(APIView):
    """
    GET /api/customer/providers/?category_id=1&lat=9.93&lng=76.26
    Returns ranked list of nearby verified providers for a category.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )

        category_id  = request.query_params.get('category_id')
        customer_lat = request.query_params.get('lat')
        customer_lng = request.query_params.get('lng')

        if not all([category_id, customer_lat, customer_lng]):
            return Response(
                {'error': 'category_id, lat, and lng are all required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            customer_lat = float(customer_lat)
            customer_lng = float(customer_lng)
        except ValueError:
            return Response(
                {'error': 'lat and lng must be valid numbers.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            category, ranked = ProviderDiscoveryService().get_nearby_providers(
                category_id, customer_lat, customer_lng
            )
        except ServiceCategory.DoesNotExist:
            return Response(
                {'error': 'Category not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if not ranked:
            return Response({
                'category': CategoryCardSerializer(category, context={'request': request}).data,
                'count':    0,
                'message':  'No providers available in your area right now.',
                'providers': [],
            })

        # build distance_map so serializer can attach distance per provider
        distance_map = {item['service'].id: item['distance_km'] for item in ranked}
        services     = [item['service'] for item in ranked]

        serializer = ProviderCardSerializer(
            services,
            many=True,
            context={
                'request':request,
                'customer_lat':  customer_lat,
                'customer_lng':  customer_lng,
                'distance_map':  distance_map,
            }
        )

        return Response({
            'category':  CategoryCardSerializer(category, context={'request': request}).data,
            'count':     len(ranked),
            'providers': serializer.data,
        })


class CustomerProviderDetailView(APIView):
    """
    GET /api/customer/providers/{service_id}/
    Full provider detail before customer books.
    Includes availability schedule.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, service_id):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            service = ProviderService.objects.select_related(
                'provider', 'category'
            ).prefetch_related(
                'provider__availability'
            ).get(
                pk                        = service_id,
                verification_status       = 'verified',
                is_active                 = True,
                provider__approval_status = 'approved',
            )
        except ProviderService.DoesNotExist:
            return Response(
                {'error': 'Provider not found or not available.'},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(ProviderDetailSerializer(service).data)


class CustomerRecommendedProvidersView(APIView):
    """
    GET /api/customer/providers/recommended/?lat=9.93&lng=76.26
    Returns a ranked list of top nearby providers across all categories.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )

        customer_lat = request.query_params.get('lat')
        customer_lng = request.query_params.get('lng')

        # Fallback to default address if parameters are empty
        if not customer_lat or not customer_lng:
            try:
                profile = request.user.customer_profile
                default_addr = profile.addresses.filter(is_default=True).first() or profile.addresses.first()
                if default_addr and default_addr.latitude and default_addr.longitude:
                    customer_lat = default_addr.latitude
                    customer_lng = default_addr.longitude
            except Exception:
                pass

        # Global system fallback (Kochi center coordinates)
        if not customer_lat or not customer_lng:
            customer_lat = 9.931233
            customer_lng = 76.267303

        try:
            customer_lat = float(customer_lat)
            customer_lng = float(customer_lng)
        except ValueError:
            return Response(
                {'error': 'lat and lng must be valid numbers.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from bookings.models import Booking
        from django.db.models import Q

        busy_provider_ids = Booking.objects.filter(
            Q(status__in=['on_the_way', 'arrived', 'in_progress']) |
            Q(booking_type='instant', status='accepted')
        ).values_list('provider_id', flat=True)

        services = ProviderService.objects.filter(
            verification_status       = 'verified',
            is_active                 = True,
            provider__approval_status = 'approved',
            provider__is_online       = True,
        ).exclude(
            provider_id__in=busy_provider_ids
        ).select_related('provider', 'category')

        ranked = HaversineLocationBackend().find_nearby(services, customer_lat, customer_lng)
        ranked = ranked[:6]

        if not ranked:
            return Response({
                'count': 0,
                'message': 'No providers available in your area right now.',
                'providers': [],
            })

        distance_map = {item['service'].id: item['distance_km'] for item in ranked}
        services_list = [item['service'] for item in ranked]

        serializer = ProviderCardSerializer(
            services_list,
            many=True,
            context={
                'request': request,
                'customer_lat': customer_lat,
                'customer_lng': customer_lng,
                'distance_map': distance_map,
            }
        )

        return Response({
            'count': len(ranked),
            'providers': serializer.data,
        })