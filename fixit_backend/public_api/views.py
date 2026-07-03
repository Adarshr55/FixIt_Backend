from django.shortcuts import render

# Create your views here.
import logging
import requests as http_requests

from decimal import Decimal

from django.conf import settings
from django.db.models import Avg, Count

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework  import status

from services.models import ServiceCategory, ProviderService
from reviews.models  import Review
from bookings.models import Booking
from profiles.models import ProviderProfile
from rest_framework.throttling import AnonRateThrottle

from customer.services  import ProviderDiscoveryService
from .serializers import (
    PublicCategorySerializer,
    PublicProviderCardSerializer,
    PublicReviewSerializer,
    PublicProviderDetailSerializer,
)

logger = logging.getLogger(__name__)

NOMINATIM_URL   = 'https://nominatim.openstreetmap.org/search'
NOMINATIM_REVERSE = 'https://nominatim.openstreetmap.org/reverse'
DEFAULT_COUNTRY = 'India'


# ── View 1 — Public Geocode ───────────────────────────────────────

class PublicGeocodeView(APIView):
    """
    POST /api/public/geocode/

    Converts address text to coordinates.
    Used by landing page location bar — no login needed.

    Body: { "address": "Kakkanad, Kochi" }
    Returns: { "latitude", "longitude", "display_name", "city" }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        address = request.data.get('address', '').strip()
        if not address:
            return Response(
                {'error': 'address is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        full_query = f"{address}, {DEFAULT_COUNTRY}"

        try:
            response = http_requests.get(
                NOMINATIM_URL,
                params={
                    'q':              full_query,
                    'format':         'json',
                    'limit':          1,
                    'addressdetails': 1,
                    'countrycodes':   'in',
                },
                headers={'User-Agent': 'FixIt-ServiceMarketplace/1.0'},
                timeout=10,
            )
            response.raise_for_status()
            results = response.json()

            if not results:
                return Response(
                    {'error': 'Location not found. Try adding city name.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            best         = results[0]
            address_data = best.get('address', {})

            # extract city name from result
            city = (
                address_data.get('city') or
                address_data.get('town') or
                address_data.get('village') or
                address_data.get('county') or
                address_data.get('state_district') or
                ''
            )

            return Response({
                'latitude':     round(float(best['lat']), 6),
                'longitude':    round(float(best['lon']), 6),
                'display_name': best.get('display_name', address),
                'city':         city,
            })

        except http_requests.Timeout:
            logger.error(f'Geocoding timeout for: {address}')
            return Response(
                {'error': 'Location service timed out. Try again.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except http_requests.RequestException as e:
            logger.error(f'Geocoding request failed: {e}')
            return Response(
                {'error': 'Location service unavailable.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            logger.error(f'Geocoding unexpected error: {e}')
            return Response(
                {'error': 'Something went wrong. Try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ── View 2 — Public Reverse Geocode ──────────────────────────────

class PublicReverseGeocodeView(APIView):
    """
    POST /api/public/reverse-geocode/

    Converts GPS coordinates to a human-readable address.
    Used when user clicks "Use my location" on landing page.

    Body: { "latitude": 9.93, "longitude": 76.26 }
    Returns: { "display_name", "city", "latitude", "longitude" }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        latitude  = request.data.get('latitude')
        longitude = request.data.get('longitude')

        if latitude is None or longitude is None:
            return Response(
                {'error': 'latitude and longitude are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            lat = float(latitude)
            lng = float(longitude)
        except (TypeError, ValueError):
            return Response(
                {'error': 'latitude and longitude must be valid numbers.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            response = http_requests.get(
                NOMINATIM_REVERSE,
                params={
                    'lat':    lat,
                    'lon':    lng,
                    'format': 'json',
                    'zoom':   14,
                    'addressdetails': 1,
                },
                headers={'User-Agent': 'FixIt-ServiceMarketplace/1.0'},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            if 'error' in data:
                return Response(
                    {'error': 'Could not determine location from coordinates.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            address_data = data.get('address', {})
            city = (
                address_data.get('city') or
                address_data.get('town') or
                address_data.get('village') or
                address_data.get('county') or
                address_data.get('state_district') or
                ''
            )

            # build a short display name
            suburb = address_data.get('suburb', '')
            short_name = f"{suburb}, {city}".strip(', ') if suburb else city

            return Response({
                'latitude':     lat,
                'longitude':    lng,
                'display_name': short_name or data.get('display_name', ''),
                'city':         city,
                'full_address': data.get('display_name', ''),
            })

        except http_requests.Timeout:
            return Response(
                {'error': 'Location service timed out.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            logger.error(f'Reverse geocoding error: {e}')
            return Response(
                {'error': 'Location service unavailable.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


# ── View 3 — Public Provider Search ──────────────────────────────

class PublicProviderSearchView(APIView):
    """
    GET /api/public/providers/

    Params:
      lat, lng          required
      category_id       optional
      min_rating        optional  e.g. 4.0
      max_distance_km   optional  e.g. 10
      sort_by           optional  score|price|rating|distance
      limit             optional  default 6, max 20
    """
    permission_classes = [AllowAny]

    def get(self, request):
        lat           = request.query_params.get('lat')
        lng           = request.query_params.get('lng')
        category_id   = request.query_params.get('category_id')
        q             = request.query_params.get('q')
        min_rating    = request.query_params.get('min_rating')
        max_distance  = request.query_params.get('max_distance_km')
        sort_by       = request.query_params.get('sort_by', 'score')
        limit         = request.query_params.get('limit', 6)

        if not lat or not lng:
            return Response(
                {'error': 'lat and lng are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            lat   = float(lat)
            lng   = float(lng)
            limit = min(int(limit), 20)
        except (TypeError, ValueError):
            return Response(
                {'error': 'lat and lng must be valid numbers.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from django.db.models import Q
            from customer.location_backends import HaversineLocationBackend

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

            if category_id:
                services = services.filter(category_id=category_id)

            if q:
                q = q.strip()
                services = services.filter(
                    Q(category__name__icontains=q) |
                    Q(skills__icontains=q)
                )

            if min_rating:
                try:
                    services = services.filter(
                        provider__overall_rating__gte=float(min_rating)
                    )
                except ValueError:
                    pass

            # run haversine ranking
            backend = HaversineLocationBackend()
            ranked  = backend.find_nearby(services, lat, lng)

            # filter by max distance after ranking
            if max_distance:
                try:
                    ranked = [
                        item for item in ranked
                        if item['distance_km'] <= float(max_distance)
                    ]
                except ValueError:
                    pass

            # sort
            if sort_by == 'price':
                ranked.sort(key=lambda x: float(x['service'].base_charge))
            elif sort_by == 'rating':
                ranked.sort(
                    key=lambda x: float(x['service'].provider.overall_rating),
                    reverse=True
                )
            elif sort_by == 'distance':
                ranked.sort(key=lambda x: x['distance_km'])
            else:
                ranked.sort(key=lambda x: x['score'], reverse=True)

            ranked = ranked[:limit]

            if not ranked:
                return Response({
                    'count':     0,
                    'message':   'No providers available in this area right now.',
                    'providers': [],
                })

            distance_map = {item['service'].id: item['distance_km'] for item in ranked}
            service_list = [item['service'] for item in ranked]

            serializer = PublicProviderCardSerializer(
                service_list,
                many=True,
                context={
                    'request':      request,
                    'distance_map': distance_map,
                }
            )

            return Response({
                'count':     len(ranked),
                'providers': serializer.data,
            })

        except Exception as e:
            logger.error(f'Public provider search error: {e}')
            return Response(
                {'error': 'Search failed. Try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ── View 4 — Public Categories ────────────────────────────────────

class PublicCategoryListView(APIView):
    """
    GET /api/public/categories/
    GET /api/public/categories/?group=home
    GET /api/public/categories/?group=automotive

    Public category list for landing page grid.
    Same data as /api/customer/categories/ but explicitly public.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        categories = ServiceCategory.objects.filter(is_active=True)

        group = request.query_params.get('group')
        if group:
            categories = categories.filter(group=group)

        return Response(
            PublicCategorySerializer(categories, many=True).data
        )


# ── View 5 — Public Stats ─────────────────────────────────────────

class PublicStatsView(APIView):
    """
    GET /api/public/stats/
    Cached for 15 minutes via Django cache framework (Redis).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from django.core.cache import cache
        from django.db.models  import Avg, Sum

        CACHE_KEY = 'public_landing_stats'
        stats     = cache.get(CACHE_KEY)

        if not stats:
            total_providers = ProviderProfile.objects.filter(
                approval_status='approved'
            ).count()

            total_jobs_completed = ProviderService.objects.aggregate(
                total=Sum('total_jobs')
            )['total'] or 0

            avg_rating = Review.objects.filter(
                is_flagged=False
            ).aggregate(avg=Avg('rating'))['avg']
            avg_rating = round(float(avg_rating), 1) if avg_rating else 0.0

            total_categories = ServiceCategory.objects.filter(
                is_active=True
            ).count()

            total_reviews = Review.objects.filter(
                is_flagged=False
            ).count()

            stats = {
                'total_providers':      total_providers,
                'total_jobs_completed': total_jobs_completed,
                'average_rating':       avg_rating,
                'total_categories':     total_categories,
                'total_reviews':        total_reviews,
            }
            cache.set(CACHE_KEY, stats, 900)  # 15 minutes

        return Response(stats)
# ── View 6 — Public Reviews ───────────────────────────────────────

class PublicReviewListView(APIView):
    """
    GET /api/public/reviews/
    GET /api/public/reviews/?limit=6
    GET /api/public/reviews/?category_id=1

    Public reviews for landing page testimonials.
    Only shows 4-5 star non-flagged reviews.
    Customer privacy protected — first name only.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        limit       = request.query_params.get('limit', 6)
        category_id = request.query_params.get('category_id')

        try:
            limit = min(int(limit), 20)
        except (TypeError, ValueError):
            limit = 6

        reviews = Review.objects.filter(
            rating__gte=4,
            is_flagged=False,
            comment__isnull=False,
        ).exclude(
            comment=''
        ).select_related(
            'customer__customer_profile',
            'provider',
            'service__category',
            'booking__category',
        ).order_by('-created_at')

        if category_id:
            reviews = reviews.filter(service__category_id=category_id)

        reviews = reviews[:limit]

        serializer = PublicReviewSerializer(reviews, many=True)
        return Response({
            'count':   reviews.count(),
            'reviews': serializer.data,
        })


# ── View 7 — Public Location Autocomplete ────────────────────────
class PublicLocationSuggestView(APIView):
    """
    GET /api/public/location-suggest/?q=kakkanad

    Returns location suggestions as user types in location bar.
    Cached for 1 hour per query — prevents Nominatim rate limiting.
    Frontend must debounce 500ms before calling this.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from django.core.cache import cache

        query = request.query_params.get('q', '').strip()

        if not query or len(query) < 3:
            return Response({'suggestions': []})

        # check cache first — key is unique per query string
        CACHE_KEY = f'location_suggest_{query.lower()}'
        cached    = cache.get(CACHE_KEY)

        if cached is not None:
            return Response({'suggestions': cached, 'cached': True})

        full_query = f"{query}, India"

        try:
            response = http_requests.get(
                NOMINATIM_URL,
                params={
                    'q':              full_query,
                    'format':         'json',
                    'limit':          5,
                    'addressdetails': 1,
                    'countrycodes':   'in',
                    'featuretype':    'city',
                },
                headers={'User-Agent': 'FixIt-ServiceMarketplace/1.0'},
                timeout=5,
            )
            response.raise_for_status()
            results = response.json()

            suggestions = []
            for result in results:
                address_data = result.get('address', {})
                city = (
                    address_data.get('city') or
                    address_data.get('town') or
                    address_data.get('village') or
                    address_data.get('county') or
                    ''
                )
                state = address_data.get('state', '')

                label_parts = [p for p in [city, state] if p]
                label       = ', '.join(label_parts) if label_parts else result.get('display_name', '')

                suggestions.append({
                    'label':     label,
                    'latitude':  round(float(result['lat']), 6),
                    'longitude': round(float(result['lon']), 6),
                    'city':      city,
                })

            # save to cache — 1 hour TTL
            # "kochi" and "kochiKL" are different keys so no collision
            cache.set(CACHE_KEY, suggestions, 3600)

            return Response({'suggestions': suggestions, 'cached': False})

        except http_requests.Timeout:
            return Response({'suggestions': []})
        except Exception as e:
            logger.error(f'Location suggest error: {e}')
            return Response({'suggestions': []})


class PublicProviderDetailView(APIView):
    """
    GET /api/public/providers/<int:service_id>/
    Safe public version of provider detail profile.
    No login required. Strips sensitive PII.
    """
    permission_classes = [AllowAny]

    def get(self, request, service_id):
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

        serializer = PublicProviderDetailSerializer(service, context={'request': request})
        return Response(serializer.data)
    



class PublicAssistView(APIView):
    """
    POST /api/public/assist/

    Public RAG assistant — no login needed.
    Used on landing page chat widget.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        query = request.data.get('query', '').strip()
        lat   = request.data.get('lat')
        lng   = request.data.get('lng')
        city  = request.data.get('city', '')

        if not query:
            return Response(
                {'error': 'query is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(query) < 5:
            return Response(
                {'error': 'query must be at least 5 characters.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if lat:
                lat = float(lat)
            if lng:
                lng = float(lng)
        except (TypeError, ValueError):
            lat = lng = None

        from ai_engine.rag_service import get_rag_response
        result = get_rag_response(
            query = query,
            lat   = lat,
            lng   = lng,
            city  = city,
        )

        # serialize providers for public response
        providers_data = []
        if result['providers']:
            from .serializers import PublicProviderCardSerializer
            serializer = PublicProviderCardSerializer(
                result['providers'],
                many=True,
                context={
                    'request':      request,
                    'distance_map': result['distance_map'],
                }
            )
            providers_data = serializer.data

        return Response({
            'query':              result['query'],
            'ai_response':        result['ai_response'],
            'suggested_category': result['suggested_category'],
            'alternatives':       result['alternatives'],
            'providers':          providers_data,
            'pricing':            result['pricing'],
        })



from rest_framework.throttling import AnonRateThrottle

class PublicChatRateThrottle(AnonRateThrottle):
    rate = '3/min'

class PublicChatView(APIView):
    """
    POST /api/public/chat/
    Body: { "session_id": "uuid-string", "message": "...", "latitude": ..., "longitude": ... }

    Limited AI assistant for anonymous visitors — search only, no booking.
    """
    permission_classes = [AllowAny]
    throttle_classes = [PublicChatRateThrottle]

    def post(self, request):
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
                defaults   = {'user': None}
            )
        else:
            session = ChatSession.objects.create(session_id=uuid.uuid4())

        ai_response = process_chat_message(
            session          = session,
            user_message     = message,
            request          = None,
            is_authenticated = False,
            lat              = latitude,
            lng              = longitude,
        )

        return Response({
            'session_id': str(session.session_id),
            'response':   ai_response,
        })