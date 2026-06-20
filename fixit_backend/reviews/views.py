from django.shortcuts import render

# Create your views here.
# reviews/views.py

from rest_framework.views       import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response    import Response
from rest_framework             import status

from accounts.permissions import IsPlatformAdmin
from .models       import Review, Report
from .serializers  import (
    ReviewSerializer,
    ReviewCreateSerializer,
    ReportSerializer,
    ReportCreateSerializer,
    ReportAdminUpdateSerializer,
)


# ------------------------------------------------------------------
# View 1 — Customer submits a review
# POST /api/reviews/
# ------------------------------------------------------------------
class ReviewCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can submit reviews.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ReviewCreateSerializer(
            data    = request.data,
            context = {'request': request}
        )
        if serializer.is_valid():
            review = serializer.save()
            return Response({
                'message': 'Review submitted. Thank you for your feedback.',
                'review':  ReviewSerializer(review).data,
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ------------------------------------------------------------------
# View 2 — Get all reviews for a specific provider service
# GET /api/reviews/provider/{service_id}/
# Public — anyone can see provider reviews
# ------------------------------------------------------------------
class ProviderReviewListView(APIView):
    permission_classes = []  # public

    def get(self, request, service_id):
        reviews = Review.objects.filter(
            service_id = service_id,
            is_flagged = False,
        ).select_related(
            'customer__customer_profile',
            'provider',
            'service__category',
        )

        serializer = ReviewSerializer(reviews, many=True)
        return Response({
            'count':   reviews.count(),
            'results': serializer.data,
        }, status=status.HTTP_200_OK)


# ------------------------------------------------------------------
# View 3 — Check if customer can review a booking
# GET /api/reviews/can-review/{booking_id}/
# ------------------------------------------------------------------
class CanReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, booking_id):
        if not request.user.is_customer:
            return Response({'can_review': False})

        from bookings.models import Booking

        try:
            booking = Booking.objects.get(
                id       = booking_id,
                customer = request.user,
            )
        except Booking.DoesNotExist:
            return Response({'can_review': False})

        already_reviewed = Review.objects.filter(
            booking=booking
        ).exists()

        return Response({
            'can_review':       booking.status == 'completed' and not already_reviewed,
            'already_reviewed': already_reviewed,
            'booking_status':   booking.status,
        })


# ------------------------------------------------------------------
# View 4 — Customer reports a provider
# POST /api/reviews/report/
# ------------------------------------------------------------------
class ReportCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can file reports.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ReportCreateSerializer(
            data    = request.data,
            context = {'request': request}
        )
        if serializer.is_valid():
            report = serializer.save()
            return Response({
                'message': (
                    'Report submitted. Our team will review it within 24 hours.'
                ),
                'report_id': report.id,
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ------------------------------------------------------------------
# View 5 — Admin views all reports
# GET /api/reviews/admin/reports/
# GET /api/reviews/admin/reports/?status=pending
# ------------------------------------------------------------------
class AdminReportListView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        reports = Report.objects.select_related(
            'customer', 'provider', 'booking'
        ).all()

        status_filter = request.query_params.get('status')
        if status_filter:
            reports = reports.filter(status=status_filter)

        reason_filter = request.query_params.get('reason')
        if reason_filter:
            reports = reports.filter(reason=reason_filter)

        serializer = ReportSerializer(reports, many=True)
        return Response({
            'count':   reports.count(),
            'results': serializer.data,
        })


# ------------------------------------------------------------------
# View 6 — Admin resolves a report
# PATCH /api/reviews/admin/reports/{id}/
# ------------------------------------------------------------------
class AdminReportActionView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def patch(self, request, pk):
        try:
            report = Report.objects.get(pk=pk)
        except Report.DoesNotExist:
            return Response(
                {'error': 'Report not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ReportAdminUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        report.status     = serializer.validated_data['action']
        report.admin_note = serializer.validated_data.get('admin_note', '')
        report.resolved_by = request.user
        report.save()

        return Response({
            'message': f'Report marked as {report.status}.',
            'report':  ReportSerializer(report).data,
        })


# ------------------------------------------------------------------
# View 7 — Admin views all reviews (for moderation)
# GET /api/reviews/admin/reviews/
# ------------------------------------------------------------------
class AdminReviewListView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        reviews = Review.objects.select_related(
            'customer', 'provider', 'service__category'
        ).all()

        flagged_only = request.query_params.get('flagged')
        if flagged_only == 'true':
            reviews = reviews.filter(is_flagged=True)

        serializer = ReviewSerializer(reviews, many=True)
        return Response({
            'count':   reviews.count(),
            'results': serializer.data,
        })


# ------------------------------------------------------------------
# View 8 — Admin flags or unflags a review
# PATCH /api/reviews/admin/reviews/{id}/flag/
# ------------------------------------------------------------------
class AdminReviewFlagView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def patch(self, request, pk):
        try:
            review = Review.objects.get(pk=pk)
        except Review.DoesNotExist:
            return Response(
                {'error': 'Review not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        review.is_flagged = not review.is_flagged
        review.save(update_fields=['is_flagged'])

        return Response({
            'message':    f'Review {"flagged" if review.is_flagged else "unflagged"}.',
            'is_flagged': review.is_flagged,
        })