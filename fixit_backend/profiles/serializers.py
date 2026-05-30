from rest_framework import serializers
from .models import ProviderProfile,CustomerProfile,ProviderDocument
from django.conf import settings
from services.models import ProviderService

class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model=CustomerProfile
        fields=[
            'id','user','full_name','profile_photo','saved_addresses','created_at','updated_at'
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

class ProviderProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model=ProviderProfile
        fields=[
            "id",
            "user",
            "full_name",
            "profile_photo",
            "bio",
            "experience_years",
            "city",
            "latitude",
            "longitude",
            "is_online",
            "service_radius_km",
            "approval_status",
            "overall_rating",
            "created_at",
            "updated_at",

        ]
        read_only_fields = [
            "id",
            "user",
            "approval_status",
            "overall_rating",
            "created_at",
            "updated_at",
        ]


class ProviderDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model=ProviderDocument
        fields=["id",
            "provider",
            "doc_type",
            "file",
            "status",
            "uploaded_at",
            "reject_reason",
            "verified_at",
            "service"
        ]
        read_only_fields = [
            "id", "provider", "status", "uploaded_at",
            "reject_reason", "verified_at" 
        ]

class CustomerProfileCreateSerializer(serializers.Serializer):
    full_name=serializers.CharField(max_length=100)
    profile_photo=serializers.URLField(required=False, allow_blank=True)
    saved_addresses = serializers.JSONField(required=False)



    def create(self, validated_data):
        user=self.context['request'].user
        profile,created=CustomerProfile.objects.update_or_create(
            user=user,
            defaults={
                 "full_name": validated_data["full_name"],
                "profile_photo": validated_data.get("profile_photo", ""),
                "saved_addresses": validated_data.get("saved_addresses", []),

            }
        )
        user.is_profile_complete=True
        user.save(update_fields=['is_profile_complete'])
        return profile
    def update(self, instance, validated_data):
        instance.full_name = validated_data.get("full_name", instance.full_name)
        instance.profile_photo = validated_data.get("profile_photo", instance.profile_photo)
        instance.saved_addresses = validated_data.get("saved_addresses", instance.saved_addresses)
        instance.save()
        return instance
    
class ProviderProfileCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=100)
    profile_photo = serializers.URLField(required=False, allow_blank=True)
    bio = serializers.CharField(required=False, allow_blank=True)
    experience_years = serializers.IntegerField(required=False, min_value=0, default=0)
    city = serializers.CharField(max_length=100)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=6, required=False, allow_null=True)
    service_radius_km = serializers.IntegerField(required=False, min_value=1, default=10)

    def create(self, validated_data):
        user=self.context['request'].user
        profile,created=ProviderProfile.objects.update_or_create(
            user=user,
            defaults={
                "full_name": validated_data["full_name"],
                "profile_photo": validated_data.get("profile_photo", ""),
                "bio": validated_data.get("bio", ""),
                "experience_years": validated_data.get("experience_years", 0),
                "city": validated_data["city"],
                "latitude": validated_data.get("latitude"),
                "longitude": validated_data.get("longitude"),
                "service_radius_km": validated_data.get("service_radius_km", 10),
            }
        )
        return profile
    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance
    

class ProviderDocumentCreateSerializer(serializers.Serializer):
    doc_type=serializers.ChoiceField(choices=ProviderDocument.DOC_TYPE_CHOICES)
    file=serializers.URLField()
    service = serializers.PrimaryKeyRelatedField(
    queryset=ProviderService.objects.all(),
    required=False,
    allow_null=True
)
    
    def validate(self, attrs):
        service  = attrs.get('service')
        doc_type = attrs.get('doc_type')
        user     = self.context['request'].user

        if service.provider != user.provider_profile:
            raise serializers.ValidationError(
                {'service': 'This service does not belong to your profile.'}
            )
        try:
            provider_profile = user.provider_profile
            existing = ProviderDocument.objects.filter(
                provider=provider_profile,
                doc_type=doc_type
        )
            if existing.exists():
                raise serializers.ValidationError(
                {'doc_type': f'A {doc_type} document is already uploaded or under review.'}
            )
        except ProviderProfile.DoesNotExist:
            pass
        return attrs

    def create(self, validated_data):
        user=self.context['request'].user
        try:
            provider_profile = user.provider_profile
        except ProviderProfile.DoesNotExist:
            raise serializers.ValidationError(
            'Complete your provider profile before uploading documents.'
        )
        return ProviderDocument.objects.create(
        provider=provider_profile,
        doc_type=validated_data['doc_type'],
        file=validated_data['file'],
        status='pending',
        service=validated_data.get('service'),
        )
    




