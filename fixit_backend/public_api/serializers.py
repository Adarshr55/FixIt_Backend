from rest_framework import serializers
from services.models import ProviderService, ServiceCategory
from reviews.models  import Review


class PublicCategorySerializer(serializers.ModelSerializer):
    group_label = serializers.CharField(source='get_group_display', read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model  = ServiceCategory
        fields = [
            'id', 'name', 'group', 'group_label',
            'icon', 'description', 'skill_tags',
            'slug', 'short_description',
            'image', 'image_url', 'display_order', 'is_featured',
            'seo_title', 'seo_description', 'seo_keywords',
        ]

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return obj.image_url or None


class PublicProviderCardSerializer(serializers.ModelSerializer):
    """
    Safe public version of provider card.
    No phone, email, exact coordinates, or payment details.
    """
    provider_name     = serializers.CharField(source='provider.full_name',    read_only=True)
    provider_city     = serializers.CharField(source='provider.city',         read_only=True)
    experience_years  = serializers.IntegerField(source='provider.experience_years', read_only=True)
    overall_rating    = serializers.DecimalField(
        source='provider.overall_rating',
        max_digits=4, decimal_places=2,
        read_only=True
    )

    is_online = serializers.BooleanField(source='provider.is_online',read_only=True)
    provider_photo = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name',read_only=True)
    category_icon = serializers.CharField(source='category.icon',read_only=True)
    is_verified = serializers.BooleanField(read_only=True)
    distance_km = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()
    completed_jobs = serializers.IntegerField(source='total_jobs',read_only=True)
    class Meta:
        model  = ProviderService
        fields = [
            'id',
            'provider_name',
            'provider_photo',
            'provider_city',
            'experience_years',
            'overall_rating',
            'completed_jobs',
            'category_name',
            'category_icon',
            'skills',
            'base_charge',
            'hourly_rate',
            'service_rating',
            'is_online',
            'is_verified',
            'distance_km',
            'total_reviews',
        ]

    def get_provider_photo(self, obj):
        request = self.context.get('request')
        if obj.provider.profile_photo and request:
            return request.build_absolute_uri(obj.provider.profile_photo.url)
        return None

    def get_distance_km(self, obj):
        distance_map = self.context.get('distance_map', {})
        return distance_map.get(obj.id)
    
    def get_total_reviews(self, obj):
        return obj.provider.reviews_received.filter(is_flagged=False).count()

class PublicReviewSerializer(serializers.ModelSerializer):
    """
    Safe public version of review.
    First name only for customer privacy.
    Comment truncated to 200 chars.
    """
    customer_first_name = serializers.SerializerMethodField()
    category_name       = serializers.SerializerMethodField()
    provider_city       = serializers.CharField(
        source='provider.city', read_only=True
    )
    short_comment       = serializers.SerializerMethodField()

    class Meta:
        model  = Review
        fields = [
            'id',
            'customer_first_name',
            'provider_city',
            'category_name',
            'rating',
            'short_comment',
            'created_at',
        ]

    def get_customer_first_name(self, obj):
        try:
            full_name = obj.customer.customer_profile.full_name
            return full_name.split()[0] if full_name else 'Customer'
        except Exception:
            return 'Customer'

    def get_category_name(self, obj):
        if obj.service and obj.service.category:
            return obj.service.category.name
        if obj.booking and obj.booking.category:
            return obj.booking.category.name
        return ''

    def get_short_comment(self, obj):
        if not obj.comment:
            return ''
        return obj.comment[:200] + '...' if len(obj.comment) > 200 else obj.comment


class PublicProviderDetailSerializer(serializers.ModelSerializer):
    """
    Safe public version of provider detail profile.
    Includes availability schedule slots for booking preview.
    """
    provider_name     = serializers.CharField(source='provider.full_name',    read_only=True)
    provider_photo    = serializers.SerializerMethodField()
    provider_bio      = serializers.CharField(source='provider.bio',          read_only=True)
    provider_city     = serializers.CharField(source='provider.city',         read_only=True)
    experience_years  = serializers.IntegerField(source='provider.experience_years', read_only=True)
    overall_rating    = serializers.DecimalField(
        source='provider.overall_rating',
        max_digits=4, decimal_places=2,
        read_only=True
    )
    category_name     = serializers.CharField(source='category.name', read_only=True)
    category_icon     = serializers.CharField(source='category.icon', read_only=True)
    is_verified       = serializers.BooleanField(read_only=True)
    is_online         = serializers.BooleanField(source='provider.is_online', read_only=True)
    completed_jobs    = serializers.IntegerField(source='total_jobs', read_only=True)
    total_reviews     = serializers.SerializerMethodField()
    availability      = serializers.SerializerMethodField()

    class Meta:
        model  = ProviderService
        fields = [
            'id',
            'provider_name',
            'provider_photo',
            'provider_bio',
            'provider_city',
            'experience_years',
            'overall_rating',
            'completed_jobs',
            'total_reviews',
            'category_name',
            'category_icon',
            'skills',
            'base_charge',
            'hourly_rate',
            'service_rating',
            'is_online',
            'is_verified',
            'availability',
        ]

    def get_provider_photo(self, obj):
        request = self.context.get('request')
        if obj.provider.profile_photo and request:
            return request.build_absolute_uri(obj.provider.profile_photo.url)
        return None

    def get_total_reviews(self, obj):
        return obj.provider.reviews_received.filter(is_flagged=False).count()

    def get_availability(self, obj):
        slots = obj.provider.availability.filter(is_active=True)
        return [
            {
                'day':                 slot.day,
                'day_name':            dict(slot.DAY_CHOICES).get(slot.day),
                'start_time':          str(slot.start_time),
                'end_time':            str(slot.end_time),
                'emergency_available': slot.emergency_available,
            }
            for slot in slots
        ]