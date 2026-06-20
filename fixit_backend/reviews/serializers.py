# reviews/serializers.py

from rest_framework import serializers
from django.utils   import timezone
from .models        import Review, Report
from bookings.models import Booking


# ------------------------------------------------------------------
# Review serializers
# ------------------------------------------------------------------

class ReviewSerializer(serializers.ModelSerializer):
    """Read serializer — returned in GET responses."""
    customer_name = serializers.SerializerMethodField()
    provider_name = serializers.CharField(
        source='provider.full_name', read_only=True
    )
    category_name = serializers.SerializerMethodField()

    class Meta:
        model  = Review
        fields = [
            'id',
            'booking',
            'customer_name',
            'provider_name',
            'category_name',
            'rating',
            'comment',
            'created_at',
        ]

    def get_customer_name(self, obj):
        # Show first name only for privacy
        try:
            return obj.customer.customer_profile.full_name.split()[0]
        except Exception:
            return 'Customer'

    def get_category_name(self, obj):
        if obj.service and obj.service.category:
            return obj.service.category.name
        if obj.booking and obj.booking.category:
            return obj.booking.category.name
        return ''


class ReviewCreateSerializer(serializers.Serializer):
    """
    Customer submits a review after completed booking.

    Request body:
    {
        "booking_id": 5,
        "rating":     4,
        "comment":    "Great work, very professional."
    }
    """
    booking_id = serializers.IntegerField()
    rating     = serializers.IntegerField(min_value=1, max_value=5)
    comment    = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
    )

    def validate_booking_id(self, value):
        user = self.context['request'].user

        # Booking must exist and belong to this customer
        try:
            booking = Booking.objects.select_related(
                'provider', 'service', 'category'
            ).get(id=value, customer=user)
        except Booking.DoesNotExist:
            raise serializers.ValidationError(
                'Booking not found.'
            )

        # Must be completed
        if booking.status != 'completed':
            raise serializers.ValidationError(
                'You can only review a completed booking.'
            )

        # Cannot review twice
        if Review.objects.filter(booking=booking).exists():
            raise serializers.ValidationError(
                'You have already reviewed this booking.'
            )

        # Store booking on serializer for create()
        self._booking = booking
        return value

    def create(self, validated_data):
        from .utils import update_service_rating, update_provider_overall_rating
        from notifications.services import notify_review_submitted

        booking  = self._booking
        customer = self.context['request'].user

        review = Review.objects.create(
            booking  = booking,
            customer = customer,
            provider = booking.provider,
            service  = booking.service,
            rating   = validated_data['rating'],
            comment  = validated_data.get('comment', ''),
        )

        # Update service rating
        if review.service:
            update_service_rating(review.service)

        # Update provider overall rating
        if review.provider:
            update_provider_overall_rating(review.provider)

        # Notify provider
        notify_review_submitted(review)

        return review


# ------------------------------------------------------------------
# Report serializers
# ------------------------------------------------------------------

class ReportSerializer(serializers.ModelSerializer):
    """Read serializer — for admin panel."""
    customer_email = serializers.EmailField(
        source='customer.email', read_only=True
    )
    provider_name  = serializers.CharField(
        source='provider.full_name', read_only=True
    )

    class Meta:
        model  = Report
        fields = [
            'id',
            'booking',
            'customer_email',
            'provider_name',
            'reason',
            'description',
            'status',
            'admin_note',
            'created_at',
        ]


class ReportCreateSerializer(serializers.Serializer):
    """
    Customer reports a provider.

    Request body:
    {
        "booking_id":   5,
        "reason":       "fraud",
        "description":  "Provider charged double the agreed amount."
    }
    """
    booking_id  = serializers.IntegerField()
    reason      = serializers.ChoiceField(
        choices=[r[0] for r in Report.REASON_CHOICES]
    )
    description = serializers.CharField(min_length=20)

    def validate_booking_id(self, value):
        user = self.context['request'].user

        try:
            booking = Booking.objects.select_related(
                'provider'
            ).get(id=value, customer=user)
        except Booking.DoesNotExist:
            raise serializers.ValidationError('Booking not found.')

        # Can only report after booking is no longer in progress
        if booking.status in ['requested', 'accepted', 'on_the_way',
                               'arrived', 'in_progress']:
            raise serializers.ValidationError(
                'You can only report after the booking is completed, '
                'cancelled, or rejected.'
            )

        self._booking = booking
        return value

    def create(self, validated_data):
        from .utils import check_and_flag_provider

        booking  = self._booking
        customer = self.context['request'].user

        report = Report.objects.create(
            booking     = booking,
            customer    = customer,
            provider    = booking.provider,
            reason      = validated_data['reason'],
            description = validated_data['description'],
        )

        # Check if provider should be auto-flagged
        check_and_flag_provider(booking.provider)

        return report


class ReportAdminUpdateSerializer(serializers.Serializer):
    """Admin resolves or dismisses a report."""

    ACTION_CHOICES = ['reviewed', 'resolved', 'dismissed']
    action     = serializers.ChoiceField(choices=ACTION_CHOICES)
    admin_note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['action'] in ['resolved', 'dismissed']:
            if not attrs.get('admin_note', '').strip():
                raise serializers.ValidationError({
                    'admin_note': 'admin_note is required when resolving or dismissing.'
                })
        return attrs