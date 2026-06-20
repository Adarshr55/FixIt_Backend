from rest_framework import serializers
from django.utils   import timezone
from .models        import Booking, BookingStatusHistory
from services.models import ProviderService
from .geocoding import geocode_address
import logging
from decimal import Decimal
from datetime import timedelta

logger = logging.getLogger(__name__)

def mask_scheduled_booking_details(data, instance, request_user=None):
    if instance.booking_type != 'scheduled':
        return data
    if instance.status not in ['requested', 'accepted']:
        return data
    if not instance.scheduled_at:
        return data
    
    if instance.scheduled_at <= timezone.now() + timedelta(hours=1):
        return data
        
    if request_user:
        if request_user == instance.customer:
            return data
        if getattr(request_user, 'role', '') == 'admin' or getattr(request_user, 'is_staff', False):
            return data
            
    data['customer_address'] = "Masked until 1 hour before service"
    if 'customer_latitude' in data:
        data['customer_latitude'] = None
    if 'customer_longitude' in data:
        data['customer_longitude'] = None
    return data
# ── Status history ────────────────────────────────────────────────

class BookingStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_email = serializers.EmailField(
        source='changed_by.email',
        read_only=True,
        default=None,
    )

    class Meta:
        model  = BookingStatusHistory
        fields = ['id', 'status', 'changed_by_email', 'note', 'timestamp']


# ── List serializer — lightweight, no nested history ──────────────

class BookingListSerializer(serializers.ModelSerializer):
    customer_email = serializers.EmailField(source='customer.email',      read_only=True)
    provider_name  = serializers.CharField(source='provider.full_name', read_only=True)
    category_name  = serializers.CharField(source='category.name',      read_only=True)
    category_icon  = serializers.CharField(source='category.icon',      read_only=True)
    is_active      = serializers.BooleanField(read_only=True)
    is_cancellable = serializers.BooleanField(read_only=True)
    prep_window_start_time = serializers.SerializerMethodField()
    is_prep_window_active = serializers.SerializerMethodField()
    is_service_start_reached = serializers.SerializerMethodField()

    class Meta:
        model  = Booking
        fields = [
            'id', 'provider_name', 'category_name', 'category_icon',
            'booking_type', 'status', 'issue_description',
            'customer_address', 'scheduled_at',
            'agreed_base_charge', 'agreed_hourly_rate',
            'is_active', 'is_cancellable', 'created_at','customer_email',
            'prep_window_start_time', 'is_prep_window_active', 'is_service_start_reached',
        ]

    def get_prep_window_start_time(self, obj):
        if obj.booking_type != 'scheduled' or not obj.scheduled_at:
            dt = obj.created_at
        else:
            dt = obj.scheduled_at - timedelta(hours=1)
        return dt.isoformat() if dt else None

    def get_is_prep_window_active(self, obj):
        if obj.booking_type != 'scheduled':
            return True
        if not obj.scheduled_at:
            return True
        return timezone.now() >= (obj.scheduled_at - timedelta(hours=1))

    def get_is_service_start_reached(self, obj):
        if obj.booking_type != 'scheduled':
            return True
        if not obj.scheduled_at:
            return True
        return timezone.now() >= obj.scheduled_at

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        request_user = request.user if request else None
        return mask_scheduled_booking_details(data, instance, request_user)


# ── Detail serializer — full, includes history ────────────────────

class BookingSerializer(serializers.ModelSerializer):
    customer_email = serializers.EmailField(source='customer.email',      read_only=True)
    provider_name  = serializers.CharField(source='provider.full_name',   read_only=True)
    category_name  = serializers.CharField(source='category.name',        read_only=True)
    category_icon  = serializers.CharField(source='category.icon',        read_only=True)
    status_history = BookingStatusHistorySerializer(many=True, read_only=True)
    is_active      = serializers.BooleanField(read_only=True)
    is_cancellable = serializers.BooleanField(read_only=True)
    prep_window_start_time = serializers.SerializerMethodField()
    is_prep_window_active = serializers.SerializerMethodField()
    is_service_start_reached = serializers.SerializerMethodField()

    class Meta:
        model  = Booking
        fields = [
            'id', 'customer_email', 'provider_name',
            'category_name', 'category_icon',
            'booking_type', 'status',
            'issue_description', 'issue_photo',
            'customer_address', 'customer_latitude', 'customer_longitude',
            'scheduled_at',
            'agreed_base_charge', 'agreed_hourly_rate', 'final_amount',
            'cancelled_by', 'cancel_reason',
            'reject_reason', 'dispute_reason',
            'accepted_at', 'started_at', 'completed_at',
            'is_active', 'is_cancellable',
            'status_history', 'created_at',
            'prep_window_start_time', 'is_prep_window_active', 'is_service_start_reached',
        ]
        read_only_fields = fields

    def get_prep_window_start_time(self, obj):
        if obj.booking_type != 'scheduled' or not obj.scheduled_at:
            dt = obj.created_at
        else:
            dt = obj.scheduled_at - timedelta(hours=1)
        return dt.isoformat() if dt else None

    def get_is_prep_window_active(self, obj):
        if obj.booking_type != 'scheduled':
            return True
        if not obj.scheduled_at:
            return True
        return timezone.now() >= (obj.scheduled_at - timedelta(hours=1))

    def get_is_service_start_reached(self, obj):
        if obj.booking_type != 'scheduled':
            return True
        if not obj.scheduled_at:
            return True
        return timezone.now() >= obj.scheduled_at

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        request_user = request.user if request else None
        return mask_scheduled_booking_details(data, instance, request_user)


# ── Customer creates booking ──────────────────────────────────────

class BookingCreateSerializer(serializers.Serializer):
    service_id         = serializers.IntegerField()
    booking_type       = serializers.ChoiceField(choices=['instant', 'scheduled'], default='instant')
    issue_description  = serializers.CharField(min_length=10)
    issue_photo        = serializers.URLField(required=False, allow_blank=True)
    customer_address   = serializers.CharField(required=False)
    scheduled_at       = serializers.DateTimeField(required=False, allow_null=True)


    def validate_customer_address(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError('A service address is required.')
        return value.strip()

    def validate_service_id(self, value):
        try:
            service = ProviderService.objects.select_related(
                'provider', 'category'
            ).get(id=value)
        except ProviderService.DoesNotExist:
            raise serializers.ValidationError('Service not found.')

        if not service.is_active:
            raise serializers.ValidationError('This service is currently paused.')

        if service.verification_status != 'verified':
            raise serializers.ValidationError('This provider is not yet verified for this service.')

        if not service.provider.is_approved:
            raise serializers.ValidationError('This provider is not approved.')

        return value

    def validate(self, attrs):
        booking_type = attrs.get('booking_type', 'instant')
        scheduled_at = attrs.get('scheduled_at')
        service_id = attrs.get('service_id')

        try:
            service = ProviderService.objects.select_related('provider', 'category').get(id=service_id)
        except ProviderService.DoesNotExist:
            raise serializers.ValidationError({'service_id': 'Service not found.'})

        if booking_type == 'scheduled':
            if not scheduled_at:
                raise serializers.ValidationError(
                    {'scheduled_at': 'scheduled_at is required for scheduled bookings.'}
                )
            if scheduled_at <= timezone.now():
                raise serializers.ValidationError(
                    {'scheduled_at': 'Scheduled time must be in the future.'}
                )

            # Prevent customer scheduling slot overlap in same category
            customer = self.context['request'].user
            start_range = scheduled_at - timezone.timedelta(hours=2)
            end_range = scheduled_at + timezone.timedelta(hours=2)
            
            overlapping_customer = Booking.objects.filter(
                customer=customer,
                category=service.category,
                booking_type='scheduled',
                status__in=['requested', 'accepted', 'on_the_way', 'arrived', 'in_progress'],
                scheduled_at__range=(start_range, end_range)
            ).exists()
            
            if overlapping_customer:
                raise serializers.ValidationError(
                    {'scheduled_at': f'You already have a scheduled booking for {service.category.name} within this 2-hour slot.'}
                )

            # Prevent scheduling slot overlap for provider
            overlapping_provider = Booking.objects.filter(
                provider=service.provider,
                booking_type='scheduled',
                status__in=['accepted', 'on_the_way', 'arrived', 'in_progress'],
                scheduled_at__range=(start_range, end_range)
            ).exists()
            
            if overlapping_provider:
                raise serializers.ValidationError(
                    {'scheduled_at': 'This provider is already booked for another job during this time slot.'}
                )

        if booking_type == 'instant':
            if scheduled_at:
                attrs['scheduled_at'] = None

            # Provider must be online for instant booking
            if not service.provider.is_online:
                raise serializers.ValidationError(
                    {'service_id': 'This provider is currently offline and cannot receive instant bookings.'}
                )

            # Provider must not be busy with an active job
            from django.db.models import Q
            is_busy = Booking.objects.filter(
                provider=service.provider,
            ).filter(
                Q(status__in=['on_the_way', 'arrived', 'in_progress']) |
                Q(booking_type='instant', status='accepted')
            ).exists()

            if is_busy:
                raise serializers.ValidationError(
                    {'service_id': 'This provider is currently busy with another active job.'}
                )

            # block customer from having multiple active instant bookings
            customer = self.context['request'].user
            active_instant = Booking.objects.filter(
                customer=customer,
                booking_type='instant',
                status__in=['requested', 'accepted', 'on_the_way', 'arrived', 'in_progress']
            ).exists()
            
            active_in_progress = Booking.objects.filter(
                customer=customer,
                status__in=['on_the_way', 'arrived', 'in_progress']
            ).exists()

            if active_instant or active_in_progress:
                raise serializers.ValidationError(
                    'You already have an active job in progress or a pending instant request. Complete or cancel it first.'
                )

        return attrs

    def create(self, validated_data):
        customer = self.context['request'].user
        service  = ProviderService.objects.select_related(
            'provider', 'category'
        ).get(id=validated_data['service_id'])

        address = validated_data.get('customer_address', '')
        coords  = geocode_address(address)

        logger.error(f'DEBUG coords type: {type(coords)}, value: {coords!r}')

        booking = Booking.objects.create(
            customer           = customer,
            provider           = service.provider,
            service            = service,
            category           = service.category,
            booking_type       = validated_data.get('booking_type', 'instant'),
            status             = 'requested',
            issue_description  = validated_data['issue_description'],
            issue_photo        = validated_data.get('issue_photo', ''),
            customer_address   = validated_data.get('customer_address', ''),
            customer_latitude    = Decimal(str(coords['latitude']))  if coords else None,
            customer_longitude   = Decimal(str(coords['longitude'])) if coords else None,
            scheduled_at       = validated_data.get('scheduled_at'),
            agreed_base_charge = service.base_charge,
            agreed_hourly_rate = service.hourly_rate,
        )

        BookingStatusHistory.objects.create(
            booking    = booking,
            status     = 'requested',
            changed_by = customer,
            note       = 'Booking created by customer.',
        )

        return booking


# ── Provider updates status ───────────────────────────────────────

# what each role is allowed to do from each state
VALID_TRANSITIONS = {
    #  current_status  : { role : [allowed next statuses] }
    'requested':   {'provider': ['accepted', 'rejected'], 'customer': ['cancelled']},
    'accepted':    {'provider': ['on_the_way', 'cancelled'], 'customer': ['cancelled']},
    'on_the_way':  {'provider': ['arrived', 'cancelled'],   'customer': ['cancelled']},
    'arrived':     {'provider': ['in_progress'],            'customer': ['cancelled']},
    'in_progress': {'provider': ['completed']},
    'completed':   {'customer': ['disputed']},
}

class BookingStatusUpdateSerializer(serializers.Serializer):
    new_status     = serializers.ChoiceField(choices=Booking.STATUS_CHOICES)
    note           = serializers.CharField(required=False, allow_blank=True)
    cancel_reason  = serializers.CharField(required=False, allow_blank=True)
    reject_reason  = serializers.CharField(required=False, allow_blank=True)
    dispute_reason = serializers.CharField(required=False, allow_blank=True)
    final_amount   = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)

    def validate(self, attrs):
        booking    = self.context['booking']
        user       = self.context['request'].user
        new_status = attrs['new_status']

        # determine role
        if user == booking.customer:
            role = 'customer'
        elif hasattr(user, 'provider_profile') and user.provider_profile == booking.provider:
            role = 'provider'
        else:
            raise serializers.ValidationError('You are not part of this booking.')

        # check transition is allowed
        allowed = VALID_TRANSITIONS.get(booking.status, {}).get(role, [])
        if new_status not in allowed:
            raise serializers.ValidationError({
                'new_status': f'Cannot move from "{booking.status}" to "{new_status}" as {role}. Allowed: {allowed}'
            })

        # Acceptance and Time-based status gating checks
        if new_status == 'accepted':
            if booking.booking_type == 'scheduled' and booking.scheduled_at:
                start_range = booking.scheduled_at - timedelta(hours=2)
                end_range = booking.scheduled_at + timedelta(hours=2)
                overlapping = Booking.objects.filter(
                    provider=booking.provider,
                    booking_type='scheduled',
                    status__in=['accepted', 'on_the_way', 'arrived', 'in_progress'],
                    scheduled_at__range=(start_range, end_range)
                ).exclude(id=booking.id).exists()
                if overlapping:
                    raise serializers.ValidationError(
                        'You cannot accept this booking because it overlaps with an already accepted scheduled booking.'
                    )
            elif booking.booking_type == 'instant':
                from django.db.models import Q
                is_busy = Booking.objects.filter(
                    provider=booking.provider,
                ).filter(
                    Q(status__in=['on_the_way', 'arrived', 'in_progress']) |
                    Q(booking_type='instant', status='accepted')
                ).exclude(id=booking.id).exists()
                if is_busy:
                    raise serializers.ValidationError(
                        'You are currently busy with another active job.'
                    )

        if booking.booking_type == 'scheduled' and booking.scheduled_at:
            if new_status in ['on_the_way', 'arrived', 'in_progress']:
                if timezone.now() < booking.scheduled_at - timedelta(hours=1):
                    raise serializers.ValidationError({
                        'new_status': 'Cannot perform this action yet. The scheduled service window is not open.'
                    })
            elif new_status == 'completed':
                if timezone.now() < booking.scheduled_at:
                    raise serializers.ValidationError({
                        'new_status': 'Cannot mark the job as completed before the scheduled service start time.'
                    })

        # field requirements per status
        if new_status == 'cancelled' and not attrs.get('cancel_reason', '').strip():
            raise serializers.ValidationError({'cancel_reason': 'Cancel reason is required.'})

        if new_status == 'rejected' and not attrs.get('reject_reason', '').strip():
            raise serializers.ValidationError({'reject_reason': 'Reject reason is required.'})

        if new_status == 'disputed' and not attrs.get('dispute_reason', '').strip():
            raise serializers.ValidationError({'dispute_reason': 'Dispute reason is required.'})

        if new_status == 'completed' and not attrs.get('final_amount'):
            raise serializers.ValidationError({'final_amount': 'Final amount is required when completing.'})

        attrs['role'] = role
        return attrs