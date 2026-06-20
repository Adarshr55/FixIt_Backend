from rest_framework import serializers
from .models import ProviderProfile,CustomerProfile,ProviderDocument,ProviderKYC,ProviderBankAccount
from django.conf import settings
from services.models import ProviderService
import re
import requests

class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model=CustomerProfile
        fields=[
            'id','full_name','profile_photo','saved_addresses','created_at','updated_at'
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
            'hourly_rate',   
            "created_at",
            "updated_at",

        ]
        read_only_fields = [
            "id",
            "user",
            "approval_status",
            "upi_verified",
            "upi_name",
            "overall_rating",
            "created_at",
            "updated_at",
        ]


class ProviderDocumentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    class Meta:
        model=ProviderDocument
        fields=["id",
            "provider",
            "doc_type",
            "file",
            'file_url',
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
    
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


    

class CustomerProfileCreateSerializer(serializers.Serializer):
    full_name=serializers.CharField(max_length=100)
    profile_photo = serializers.ImageField(required=False, allow_null=True)
    saved_addresses = serializers.JSONField(required=False)



    def create(self, validated_data):
        user=self.context['request'].user
        profile,created=CustomerProfile.objects.update_or_create(
            user=user,
            defaults={
                 "full_name": validated_data["full_name"],
                "profile_photo": validated_data.get("profile_photo",None),
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
    profile_photo = serializers.ImageField(required=False, allow_null=True)
    bio = serializers.CharField(required=False, allow_blank=True)
    experience_years = serializers.IntegerField(required=False, min_value=0, default=0)
    city = serializers.CharField(max_length=100)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=6, required=False, allow_null=True)
    service_radius_km = serializers.IntegerField(required=False, min_value=1, default=10)
    hourly_rate= serializers.DecimalField(max_digits=8, decimal_places=2, required=False, default=0)

    def create(self, validated_data):
        user=self.context['request'].user
        profile,created=ProviderProfile.objects.update_or_create(
            user=user,
            defaults={
                "full_name": validated_data["full_name"],
                "profile_photo": validated_data.get("profile_photo", None),
                "bio": validated_data.get("bio", ""),
                "experience_years": validated_data.get("experience_years", 0),
                "city": validated_data["city"],
                "latitude": validated_data.get("latitude"),
                "longitude": validated_data.get("longitude"),
                "service_radius_km": validated_data.get("service_radius_km", 10),
                "hourly_rate":       validated_data.get("hourly_rate", 0),
            }
        )
        user.is_profile_complete=True
        user.save(update_fields=['is_profile_complete'])
        return profile
    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance
    

class ProviderDocumentCreateSerializer(serializers.Serializer):
    doc_type=serializers.ChoiceField(choices=ProviderDocument.DOC_TYPE_CHOICES)
    file = serializers.FileField()
    service = serializers.PrimaryKeyRelatedField(
    queryset=ProviderService.objects.all(),
    required=False,
    allow_null=True
)
    
    def validate(self, attrs):
        service  = attrs.get('service')
        doc_type = attrs.get('doc_type')
        user     = self.context['request'].user
        
        if service:
            if service.provider != user.provider_profile:
                raise serializers.ValidationError(
                    {'service': 'This service does not belong to your profile.'}
                )
        try:
            provider_profile = user.provider_profile
            existing = ProviderDocument.objects.filter(
                provider=provider_profile,
                doc_type=doc_type
        ).exclude(status='rejected')
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
    

class ProviderKYCSerializer(serializers.ModelSerializer):
    """Read serializer — returned to provider."""

    class Meta:
        model  = ProviderKYC
        fields = [
            'id',
            'pan_number', 'pan_status', 'pan_reject_reason',
            'aadhaar_last4', 'aadhaar_status', 'aadhaar_reject_reason',
            'kyc_verified',
            'submitted_at', 'updated_at',
        ]
        read_only_fields = fields



class ProviderKYCSubmitSerializer(serializers.Serializer):
    """Provider submits KYC documents."""
    pan_number       = serializers.CharField(max_length=10)
    pan_document     = serializers.FileField()
    aadhaar_last4    = serializers.CharField(min_length=4, max_length=4)
    aadhaar_document = serializers.FileField()

    def validate_pan_number(self, value):
        value = value.strip().upper()
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', value):
            raise serializers.ValidationError(
                'Invalid PAN format. Expected format: AAABBB1234C'
            )
        return value

    def validate_aadhaar_last4(self, value):
        if not value.isdigit():
            raise serializers.ValidationError(
                'Last 4 digits of Aadhaar must be numeric.'
            )
        return value
    
    def validate_pan_document(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('File must be under 10MB.')
        if value.content_type not in ['image/jpeg', 'image/png', 'image/jpg', 'application/pdf']:
            raise serializers.ValidationError('Only JPG, PNG, or PDF allowed.')
        return value
    
    def validate_aadhaar_document(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('File must be under 10MB.')
        if value.content_type not in ['image/jpeg', 'image/png', 'image/jpg', 'application/pdf']:
            raise serializers.ValidationError('Only JPG, PNG, or PDF allowed.')
        return value
    
    def create(self, validated_data):
        provider = self.context['request'].user.provider_profile

        kyc, created = ProviderKYC.objects.update_or_create(
            provider=provider,
            defaults={
                'pan_number':        validated_data['pan_number'],
                'pan_document':      validated_data['pan_document'],
                'pan_status':        'pending',
                'aadhaar_last4':     validated_data['aadhaar_last4'],
                'aadhaar_document':  validated_data['aadhaar_document'],
                'aadhaar_status':    'pending',
                'kyc_verified':      False,
            }
        )
        return kyc
    

class AdminKYCActionSerializer(serializers.Serializer):
    """Admin approves or rejects a single KYC document."""
    document_type = serializers.ChoiceField(choices=['pan', 'aadhaar'])
    action        = serializers.ChoiceField(choices=['approve', 'reject'])
    reject_reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['action'] == 'reject' and not attrs.get('reject_reason', '').strip():
            raise serializers.ValidationError(
                {'reject_reason': 'reject_reason is required when rejecting.'}
            )
        return attrs
    


# ── Bank account serializers ──────────────────────────────────────

class ProviderBankAccountSerializer(serializers.ModelSerializer):
    """Read serializer — returned to provider."""
    passbook_url = serializers.SerializerMethodField()

    class Meta:
        model  = ProviderBankAccount
        fields = [
            'id',
            'account_holder_name',
            'account_number',
            'ifsc_code',
            'bank_name',
            'branch_name',
            'passbook_url',
            'is_verified',
            'reject_reason',
            'submitted_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_passbook_url(self, obj):
        request = self.context.get('request')
        if obj.passbook_document and request:
            return request.build_absolute_uri(obj.passbook_document.url)
        return None


class ProviderBankAccountSubmitSerializer(serializers.Serializer):
    """Provider submits bank account details."""
    account_holder_name = serializers.CharField(max_length=100)
    account_number      = serializers.CharField(max_length=20)
    ifsc_code           = serializers.CharField(max_length=11)
    passbook_document   = serializers.FileField()

    def validate_account_number(self, value):
        value = value.strip()
        if not value.isdigit() or len(value) < 9 or len(value) > 18:
            raise serializers.ValidationError(
                'Account number must be 9-18 digits.'
            )
        return value

    def validate_ifsc_code(self, value):
        value = value.strip().upper()
        if not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', value):
            raise serializers.ValidationError(
                'Invalid IFSC format. Expected: SBIN0001234'
            )
        return value

    def validate_passbook_document(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('File must be under 10MB.')
        if value.content_type not in ['image/jpeg', 'image/png', 'image/jpg', 'application/pdf']:
            raise serializers.ValidationError('Only JPG, PNG, or PDF allowed.')
        return value

    def validate(self, attrs):
        # validate IFSC via free Razorpay API
        ifsc = attrs.get('ifsc_code', '')
        try:
            response = requests.get(
                f'https://ifsc.razorpay.com/{ifsc}',
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                attrs['bank_name']   = data.get('BANK', '')
                attrs['branch_name'] = data.get('BRANCH', '')
            elif response.status_code == 404:
                raise serializers.ValidationError(
                    {'ifsc_code': 'IFSC code not found. Please check and try again.'}
                )
        except requests.Timeout:
            # don't block submission if IFSC API is slow
            attrs['bank_name']   = ''
            attrs['branch_name'] = ''
        except serializers.ValidationError:
            raise
        except Exception:
            attrs['bank_name']   = ''
            attrs['branch_name'] = ''

        return attrs

    def create(self, validated_data):
        provider = self.context['request'].user.provider_profile

        bank, created = ProviderBankAccount.objects.update_or_create(
            provider=provider,
            defaults={
                'account_holder_name': validated_data['account_holder_name'],
                'account_number':      validated_data['account_number'],
                'ifsc_code':           validated_data['ifsc_code'],
                'bank_name':           validated_data.get('bank_name', ''),
                'branch_name':         validated_data.get('branch_name', ''),
                'passbook_document':   validated_data['passbook_document'],
                'is_verified':         False,
                'reject_reason':       '',
            }
        )
        return bank
    

class AdminBankAccountActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    reject_reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['action'] == 'reject' and not attrs.get('reject_reason', '').strip():
            raise serializers.ValidationError(
                {'reject_reason': 'reject_reason is required when rejecting.'}
            )
        return attrs




        





