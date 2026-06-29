from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated,AllowAny
from rest_framework.response import Response
from rest_framework import status

from accounts.permissions import IsPlatformAdmin
from profiles.models import ProviderProfile
from services.models import ProviderService

from .fraud_detection import run_full_provider_fraud_check
from .ranking  import get_provider_score_breakdown
from .search_service import(search_categories,search_with_providers,find_duplicate_services)
from rest_framework.throttling import AnonRateThrottle


class AdminProviderFraudCheckView(APIView):
    """
    GET /api/ai/admin/fraud-check/{provider_id}/
    Runs fraud check on a specific provider and returns results.
    Admin only.
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request, provider_id):
        try:
            provider = ProviderProfile.objects.get(pk=provider_id)
        except ProviderProfile.DoesNotExist:
            return Response(
                {'error': 'Provider not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        result = run_full_provider_fraud_check(provider)
        return Response(result)


class AdminAllFraudRiskView(APIView):
    """
    GET /api/ai/admin/fraud-risk/
    GET /api/ai/admin/fraud-risk/?risk=high
    GET /api/ai/admin/fraud-risk/?risk=critical

    Returns fraud risk assessment for all providers.
    Expensive — cached for 1 hour in production.
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        from django.core.cache import cache

        risk_filter = request.query_params.get('risk')
        CACHE_KEY   = f'fraud_risk_all_{risk_filter or "all"}'
        cached      = cache.get(CACHE_KEY)

        if cached:
            return Response(cached)

        providers = ProviderProfile.objects.filter(
            approval_status='approved'
        ).select_related('user')

        results = []
        for provider in providers:
            result = run_full_provider_fraud_check(provider)
            if risk_filter:
                if result['overall_risk'] == risk_filter:
                    results.append(result)
            else:
                if result['overall_risk'] != 'low':
                    results.append(result)

        # sort by risk level
        risk_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        results.sort(key=lambda x: risk_order.get(x['overall_risk'], 4))

        response_data = {
            'count':   len(results),
            'results': results,
        }

        cache.set(CACHE_KEY, response_data, 3600)
        return Response(response_data)


class AdminProviderScoreBreakdownView(APIView):
    """
    GET /api/ai/admin/score/{provider_id}/?lat=9.93&lng=76.26

    Shows detailed breakdown of why a provider ranks where they do.
    Useful for admin to understand ranking and for debugging.
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request, provider_id):
        lat = request.query_params.get('lat', 0)
        lng = request.query_params.get('lng', 0)

        try:
            lat = float(lat)
            lng = float(lng)
        except ValueError:
            lat = lng = 0

        try:
            provider = ProviderProfile.objects.get(pk=provider_id)
        except ProviderProfile.DoesNotExist:
            return Response(
                {'error': 'Provider not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        services = ProviderService.objects.filter(
            provider=provider,
            verification_status='verified',
            is_active=True,
        ).select_related('category','provider')

        if not services.exists():
            return Response(
                {'error': 'Provider has no verified services.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # calculate distance if coordinates provided
        distance_km = 0
        if lat and lng and provider.latitude and provider.longitude:
            from customer.location_backends import HaversineLocationBackend
            backend     = HaversineLocationBackend()
            distance_km = backend._distance_km(
                lat, lng,
                float(provider.latitude),
                float(provider.longitude)
            )

        breakdowns = []
        for service in services:
            breakdown = get_provider_score_breakdown(service, distance_km)
            breakdown['service_id']       = service.id
            breakdown['service_category'] = service.category.name
            breakdowns.append(breakdown)

        return Response({
            'provider_id':   provider_id,
            'provider_name': provider.full_name,
            'distance_km':   round(distance_km, 2),
            'services':      breakdowns,
        })


class AdminReviewFraudCheckView(APIView):
    """
    POST /api/ai/admin/review-fraud-check/
    Body: { "review_id": 5 }
    Runs fraud check on a specific review.
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def post(self, request):
        from reviews.models import Review
        from .fraud_detection import run_full_review_fraud_check

        review_id = request.data.get('review_id')
        if not review_id:
            return Response(
                {'error': 'review_id is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            review = Review.objects.select_related(
                'customer__customer_profile',
                'provider',
            ).get(pk=review_id)
        except Review.DoesNotExist:
            return Response(
                {'error': 'Review not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        result = run_full_review_fraud_check(review)
        return Response(result)
    
class AdminDuplicateServicesView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        from django.core.cache import cache

        threshold = float(request.query_params.get('threshold', 90)) / 100
        CACHE_KEY = f'duplicate_services_{int(threshold * 100)}'
        cached    = cache.get(CACHE_KEY)

        if cached:
            return Response(cached)

        groups = find_duplicate_services(similarity_threshold=threshold)

        result = {
            'count':      len(groups),
            'threshold':  int(threshold * 100),
            'groups':     groups,
        }

        cache.set(CACHE_KEY, result, 3600)
        return Response(result)


class AdminCustomerAbuseListView(APIView):
    """
    GET /api/ai_engine/admin/customer-abuse/
    Lists customers who have cancelled an excessive percentage of bookings.
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        from accounts.models import User
        from .fraud_detection import check_customer_booking_abuse

        customers = User.objects.filter(role='customer')
        results = []
        for cust in customers:
            check = check_customer_booking_abuse(cust)
            if check.get('is_abusive'):
                results.append({
                    'customer_id':    cust.id,
                    'customer_email': cust.email,
                    'customer_name':  getattr(getattr(cust, 'customer_profile', None), 'full_name', cust.email),
                    'cancel_rate':    check['rate'],
                    'cancels':        check['cancels'],
                    'total':          check['total'],
                    'is_active':      cust.is_active,
                })
        return Response({
            'count': len(results),
            'results': results
        })
    


class SearchRateThrottle(AnonRateThrottle):
     scope = 'public_search'

class PublicSemanticSearchView(APIView):
    """
    POST /api/public/search/

    Semantic search for landing page.
    No auth required.
    Converts natural language query to category suggestions.
    """
    permission_classes = [AllowAny]
    throttle_classes = [SearchRateThrottle] 

    def post(self, request):
        query = request.data.get('query', '').strip()

        if not query:
            return Response(
                {'error': 'query is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(query) < 3:
            return Response(
                {'error': 'query must be at least 3 characters.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from ai_engine.search_service import search_categories
        from bookings.models import Booking
        from django.db.models import Q

        results = search_categories(query, limit=3, min_confidence=40)

        if not results:
            return Response({
                'query':   query,
                'results': [],
                'message': 'No matching services found. Try different keywords.',
            })

        # add available provider count to each result
        busy_provider_ids = Booking.objects.filter(
            Q(status__in=['on_the_way', 'arrived', 'in_progress']) |
            Q(booking_type='instant', status='accepted')
        ).values_list('provider_id', flat=True)

        from services.models import ProviderService
        for result in results:
            count = ProviderService.objects.filter(
                category_id               = result['category_id'],
                verification_status       = 'verified',
                is_active                 = True,
                provider__approval_status = 'approved',
                provider__is_online       = True,
            ).exclude(
                provider_id__in=busy_provider_ids
            ).count()
            result['providers_available'] = count

        return Response({
            'query':      query,
            'top_match':  results[0]['category_name'],
            'results':    results,
        })



