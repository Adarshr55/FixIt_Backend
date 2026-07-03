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
    
class CustomerSemanticSearchView(APIView):
    """
    POST /api/customer/search/

    Semantic search for authenticated customer dashboard.
    Returns category suggestion + nearby providers.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )

        query = request.data.get('query', '').strip()
        lat   = request.data.get('lat')
        lng   = request.data.get('lng')

        if not query:
            return Response(
                {'error': 'query is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # fallback to saved address if no coordinates provided
        if not lat or not lng:
            try:
                profile = request.user.customer_profile
                if profile.saved_addresses:
                    first = profile.saved_addresses[0]
                    lat   = first.get('latitude')
                    lng   = first.get('longitude')
            except Exception:
                pass

        if not lat or not lng:
            # no location — return category suggestions only
            from ai_engine.search_service import search_categories
            results = search_categories(query, limit=3, min_confidence=40)
            return Response({
                'query':          query,
                'top_category':   results[0] if results else None,
                'alternatives':   results[1:] if len(results) > 1 else [],
                'providers':      [],
                'location_needed': True,
            })

        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError):
            return Response(
                {'error': 'lat and lng must be valid numbers.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from ai_engine.search_service import search_with_providers
        from customer.serializers import ProviderCardSerializer

        result = search_with_providers(query, lat, lng)

        # serialize providers
        providers_data = []
        if result['providers']:
            serializer = ProviderCardSerializer(
                result['providers'],
                many=True,
                context={
                    'request':      request,
                    'distance_map': result.get('distance_map', {}),
                }
            )
            providers_data = serializer.data

        return Response({
            'query':        query,
            'top_category': result['top_category'],
            'alternatives': result['alternatives'],
            'providers':    providers_data,
        })
    


# class CustomerAssistView(APIView):
#     """
#     POST /api/customer/assist/

#     Authenticated RAG assistant with full location context.
#     Used on customer dashboard.
#     """
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         if not request.user.is_customer:
#             return Response(
#                 {'error': 'Only customers can access this.'},
#                 status=status.HTTP_403_FORBIDDEN
#             )

#         query = request.data.get('query', '').strip()
#         lat   = request.data.get('lat')
#         lng   = request.data.get('lng')

#         if not query:
#             return Response(
#                 {'error': 'query is required.'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         # fallback to saved address
#         if not lat or not lng:
#             try:
#                 profile = request.user.customer_profile
#                 if profile.saved_addresses:
#                     first = profile.saved_addresses[0]
#                     lat   = first.get('latitude')
#                     lng   = first.get('longitude')
#             except Exception:
#                 pass

#         try:
#             if lat:
#                 lat = float(lat)
#             if lng:
#                 lng = float(lng)
#         except (TypeError, ValueError):
#             lat = lng = None

#         # get customer city for context
#         city = ''
#         try:
#             city = request.user.customer_profile.saved_addresses[0].get(
#                 'city', ''
#             ) if request.user.customer_profile.saved_addresses else ''
#         except Exception:
#             pass

#         from ai_engine.rag_service import get_rag_response
#         from customer.serializers  import ProviderCardSerializer

#         result = get_rag_response(
#             query = query,
#             lat   = lat,
#             lng   = lng,
#             city  = city,
#         )

#         providers_data = []
#         if result['providers']:
#             serializer = ProviderCardSerializer(
#                 result['providers'],
#                 many=True,
#                 context={
#                     'request':      request,
#                     'distance_map': result['distance_map'],
#                 }
#             )
#             providers_data = serializer.data

#         return Response({
#             'query':              result['query'],
#             'ai_response':        result['ai_response'],
#             'suggested_category': result['suggested_category'],
#             'alternatives':       result['alternatives'],
#             'providers':          providers_data,
#             'pricing':            result['pricing'],
#         })
    




from rest_framework.throttling import UserRateThrottle

class CustomerChatRateThrottle(UserRateThrottle):
    rate = '10/min'

class CustomerChatView(APIView):
    """
    POST /api/customer/chat/
    Body: { "session_id": "uuid-string", "message": "...", "latitude": ..., "longitude": ... }

    Full AI booking assistant — can search, book, cancel, check status.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [CustomerChatRateThrottle]

    def post(self, request):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )

        message    = request.data.get('message', '').strip()
        session_id = request.data.get('session_id')
        latitude   = request.data.get('latitude')
        longitude  = request.data.get('longitude')

        if not message:
            return Response(
                {'error': 'message is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from ai_engine.models import ChatSession
        from ai_engine.chat_service import process_chat_message
        import uuid

        if session_id:
            session, _ = ChatSession.objects.get_or_create(
                session_id = session_id,
                defaults   = {'user': request.user}
            )
        else:
            session = ChatSession.objects.create(
                session_id = uuid.uuid4(),
                user       = request.user,
            )

        ai_response = process_chat_message(
            session          = session,
            user_message     = message,
            request          = request,
            is_authenticated = True,
            lat              = latitude,
            lng              = longitude,
        )

        return Response({
            'session_id':  str(session.session_id),
            'response':    ai_response,
        })