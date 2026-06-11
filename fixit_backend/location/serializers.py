from rest_framework import serializers
from .models        import ProviderLocation


class ProviderLocationUpdateSerializer(serializers.Serializer):
    """Provider sends their current GPS position."""
    latitude   = serializers.DecimalField(max_digits=10, decimal_places=6)
    longitude  = serializers.DecimalField(max_digits=10, decimal_places=6)
    booking_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_latitude(self, value):
        v = float(value)
        if not (-90 <= v <= 90):
            raise serializers.ValidationError('Latitude must be between -90 and 90.')
        return value

    def validate_longitude(self, value):
        v = float(value)
        if not (-180 <= v <= 180):
            raise serializers.ValidationError('Longitude must be between -180 and 180.')
        return value


class ProviderLocationSerializer(serializers.ModelSerializer):
    """Returned to customer when polling provider position."""
    provider_name = serializers.CharField(source='provider.full_name', read_only=True)

    class Meta:
        model  = ProviderLocation
        fields = [
            'provider_name',
            'latitude',
            'longitude',
            'booking',
            'updated_at',
        ]