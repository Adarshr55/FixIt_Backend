from rest_framework  import serializers
from services.models import ServiceCategory, ProviderService


class CategoryCardSerializer(serializers.ModelSerializer):
    """Home screen category grid cards."""
    image = serializers.SerializerMethodField()

    class Meta:
        model  = ServiceCategory
        fields = [
            'id', 'name', 'group', 'icon', 'description', 
            'image', 'image_url', 'display_order', 'is_featured', 
            'short_description'
        ]

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return obj.image_url or None


class ProviderCardSerializer(serializers.ModelSerializer):
    """
    Provider list card — shown after customer selects a category.
    distance_km injected via context distance_map.
    """
    provider_name    = serializers.CharField(source='provider.full_name',    read_only=True)
    provider_photo = serializers.SerializerMethodField()
    provider_city    = serializers.CharField(source='provider.city',         read_only=True)
    experience_years = serializers.IntegerField(source='provider.experience_years', read_only=True)
    overall_rating   = serializers.DecimalField(
        source='provider.overall_rating',
        max_digits=4, decimal_places=2,
        read_only=True
    )
    category_name    = serializers.CharField(source='category.name', read_only=True)
    category_icon    = serializers.CharField(source='category.icon', read_only=True)
    is_verified      = serializers.BooleanField(read_only=True)
    distance_km      = serializers.SerializerMethodField()

    def get_provider_photo(self, obj):
        request = self.context.get('request')
        if obj.provider.profile_photo and request:
            return request.build_absolute_uri(obj.provider.profile_photo.url)
        return None

    class Meta:
        model  = ProviderService
        fields = [
            'id',
            'provider_name',
            'provider_photo',
            'provider_city',
            'experience_years',
            'overall_rating',
            'category_name',
            'category_icon',
            'skills',
            'base_charge',
            'hourly_rate',
            'service_rating',
            'total_jobs',
            'completion_rate',
            'is_verified',
            'distance_km',
        ]

    def get_distance_km(self, obj):
        distance_map = self.context.get('distance_map', {})
        return distance_map.get(obj.id)


class ProviderDetailSerializer(serializers.ModelSerializer):
    """
    Full provider detail — shown when customer taps a card.
    Includes availability schedule so customer can schedule a booking.
    """
    provider_name    = serializers.CharField(source='provider.full_name',    read_only=True)
    provider_photo = serializers.SerializerMethodField()
    provider_bio     = serializers.CharField(source='provider.bio',          read_only=True)
    provider_city    = serializers.CharField(source='provider.city',         read_only=True)
    experience_years = serializers.IntegerField(source='provider.experience_years', read_only=True)
    overall_rating   = serializers.DecimalField(
        source='provider.overall_rating',
        max_digits=4, decimal_places=2,
        read_only=True
    )
    service_radius_km = serializers.IntegerField(source='provider.service_radius_km', read_only=True)
    category_name    = serializers.CharField(source='category.name', read_only=True)
    category_icon    = serializers.CharField(source='category.icon', read_only=True)
    is_verified      = serializers.BooleanField(read_only=True)
    availability     = serializers.SerializerMethodField()

    def get_provider_photo(self, obj):
        request = self.context.get('request')
        if obj.provider.profile_photo and request:
            return request.build_absolute_uri(obj.provider.profile_photo.url)
        return None 

    class Meta:
        model  = ProviderService
        fields = [
            'id',
            'provider_name',
            'provider_photo',
            'provider_bio',
            'provider_city',
            'experience_years',
            'service_radius_km',
            'overall_rating',
            'category_name',
            'category_icon',
            'skills',
            'base_charge',
            'hourly_rate',
            'service_rating',
            'total_jobs',
            'completion_rate',
            'is_verified',
            'availability',
        ]

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