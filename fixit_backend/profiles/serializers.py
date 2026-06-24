from rest_framework import serializers
from .models import ProviderProfile,CustomerProfile,ProviderDocument,ProviderKYC,ProviderBankAccount,CustomerAddress
from django.conf import settings
from services.models import ProviderService
import re
import requests

def _safe_delete_photo(photo_field):
    """
    Safely delete a profile photo file from disk if it exists,
    guarding against external URLs or invalid filenames that raise OS errors.
    """
    if not photo_field or not photo_field.name:
        return
    if photo_field.name.startswith(('http://', 'https://')):
        return
    try:
        if photo_field.storage.exists(photo_field.name):
            photo_field.delete(save=False)
    except Exception:
        # Ignore file system exceptions during deletion
        pass

def _resolve_file_url(file_field, request=None):
    """
    Safely resolve a FileField/ImageField URL. If the filename is an
    absolute external URL, returns it directly to prevent prefixing /media/
    and causing 404 errors.
    """
    if not file_field or not file_field.name:
        return None
    if file_field.name.startswith(('http://', 'https://')):
        return file_field.name
    if request:
        return request.build_absolute_uri(file_field.url)
    return file_field.url



class CustomerAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerAddress
        fields = [
            'id', 'label', 'address', 'latitude', 'longitude', 'is_default', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        address = attrs.get('address')
        # If address is updated/created and coordinates aren't provided
        if address and (attrs.get('latitude') is None or attrs.get('longitude') is None):
            from bookings.geocoding import geocode_address
            coords = geocode_address(address)
            if not coords:
                raise serializers.ValidationError({
                    "address": "Could not resolve coordinates for this address. Please check spelling or make it more specific."
                })
            attrs['latitude'] = coords['latitude']
            attrs['longitude'] = coords['longitude']
        return attrs

class CustomerProfileSerializer(serializers.ModelSerializer):
    addresses = CustomerAddressSerializer(many=True, read_only=True)
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model=CustomerProfile
        fields=[
            'id','full_name','profile_photo','profile_photo_url','addresses','saved_addresses','created_at','updated_at'
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def get_profile_photo_url(self, obj):
        return _resolve_file_url(obj.profile_photo, self.context.get('request'))

class ProviderProfileSerializer(serializers.ModelSerializer):
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model=ProviderProfile
        fields=[
            "id",
            "user",
            "full_name",
            "profile_photo",
            "profile_photo_url",
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
            "overall_rating",
            "created_at",
            "updated_at",
        ]

    def get_profile_photo_url(self, obj):
        return _resolve_file_url(obj.profile_photo, self.context.get('request'))


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
        return _resolve_file_url(obj.file, self.context.get('request'))


    

class CustomerProfileCreateSerializer(serializers.Serializer):
    full_name=serializers.CharField(max_length=100)
    profile_photo = serializers.ImageField(required=False, allow_null=True)
    saved_addresses = serializers.JSONField(required=False)

    def to_internal_value(self, data):
        # Handle cases where photo is a string URL or is deleted
        mutable_data = data.copy() if hasattr(data, 'copy') else dict(data)
        photo = mutable_data.get('profile_photo')
        
        if isinstance(photo, str) and (photo.startswith('http://') or photo.startswith('https://') or '/media/' in photo):
            mutable_data.pop('profile_photo', None)
        elif photo == '' or photo == 'null' or photo == 'None':
            mutable_data['profile_photo'] = None

        return super().to_internal_value(mutable_data)

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
        # Create CustomerAddress rows for any saved_addresses passed
        saved_addresses = validated_data.get("saved_addresses", [])
        if isinstance(saved_addresses, list):
            for addr_data in saved_addresses:
                if isinstance(addr_data, dict) and addr_data.get('address'):
                    label = addr_data.get('label', 'Home')
                    address_text = addr_data['address']
                    if not CustomerAddress.objects.filter(customer=profile, address=address_text).exists():
                        is_default = addr_data.get('is_default', False)
                        if not CustomerAddress.objects.filter(customer=profile).exists():
                            is_default = True
                        CustomerAddress.objects.create(
                            customer=profile,
                            label=label,
                            address=address_text,
                            latitude=addr_data.get('latitude'),
                            longitude=addr_data.get('longitude'),
                            is_default=is_default
                        )
        user.is_profile_complete=True
        user.save(update_fields=['is_profile_complete'])
        return profile

    def update(self, instance, validated_data):
        instance.full_name = validated_data.get("full_name", instance.full_name)
        instance.saved_addresses = validated_data.get("saved_addresses", instance.saved_addresses)
        
        if "profile_photo" in validated_data:
            new_photo = validated_data["profile_photo"]
            if new_photo is None:
                # Clear and delete previous photo file from disk/S3
                _safe_delete_photo(instance.profile_photo)
                instance.profile_photo = None
            else:
                # Replace and delete previous photo file from disk/S3
                if instance.profile_photo and instance.profile_photo != new_photo:
                    _safe_delete_photo(instance.profile_photo)
                instance.profile_photo = new_photo
                
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

    def to_internal_value(self, data):
        # Handle cases where photo is a string URL or is deleted
        mutable_data = data.copy() if hasattr(data, 'copy') else dict(data)
        photo = mutable_data.get('profile_photo')
        
        if isinstance(photo, str) and (photo.startswith('http://') or photo.startswith('https://') or '/media/' in photo):
            mutable_data.pop('profile_photo', None)
        elif photo == '' or photo == 'null' or photo == 'None':
            mutable_data['profile_photo'] = None

        return super().to_internal_value(mutable_data)

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
        instance.full_name = validated_data.get("full_name", instance.full_name)
        instance.bio = validated_data.get("bio", instance.bio)
        instance.experience_years = validated_data.get("experience_years", instance.experience_years)
        instance.city = validated_data.get("city", instance.city)
        instance.latitude = validated_data.get("latitude", instance.latitude)
        instance.longitude = validated_data.get("longitude", instance.longitude)
        instance.service_radius_km = validated_data.get("service_radius_km", instance.service_radius_km)
        instance.hourly_rate = validated_data.get("hourly_rate", instance.hourly_rate)

        if "profile_photo" in validated_data:
            new_photo = validated_data["profile_photo"]
            if new_photo is None:
                # Clear and delete previous photo file from disk/S3
                _safe_delete_photo(instance.profile_photo)
                instance.profile_photo = None
            else:
                # Replace and delete previous photo file from disk/S3
                if instance.profile_photo and instance.profile_photo != new_photo:
                    _safe_delete_photo(instance.profile_photo)
                instance.profile_photo = new_photo
                
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

    def validate_file(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('File must be under 10MB.')
        if value.content_type not in ['image/jpeg', 'image/png', 'image/jpg', 'application/pdf']:
            raise serializers.ValidationError('Only JPG, PNG, or PDF allowed.')
        return value
    
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
    pan_document_url = serializers.SerializerMethodField()
    aadhaar_document_url = serializers.SerializerMethodField()

    class Meta:
        model  = ProviderKYC
        fields = [
            'id',
            'pan_number', 'pan_status', 'pan_reject_reason', 'pan_document_url',
            'aadhaar_last4', 'aadhaar_status', 'aadhaar_reject_reason', 'aadhaar_document_url',
            'kyc_verified',
            'submitted_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_pan_document_url(self, obj):
        return _resolve_file_url(obj.pan_document, self.context.get('request'))

    def get_aadhaar_document_url(self, obj):
        return _resolve_file_url(obj.aadhaar_document, self.context.get('request'))



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

        try:
            existing = ProviderKYC.objects.get(provider=provider)
            if 'pan_document' in validated_data and existing.pan_document and existing.pan_document != validated_data['pan_document']:
                _safe_delete_photo(existing.pan_document)
            if 'aadhaar_document' in validated_data and existing.aadhaar_document and existing.aadhaar_document != validated_data['aadhaar_document']:
                _safe_delete_photo(existing.aadhaar_document)
        except ProviderKYC.DoesNotExist:
            pass

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
        return _resolve_file_url(obj.passbook_document, self.context.get('request'))


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

        try:
            existing = ProviderBankAccount.objects.get(provider=provider)
            if 'passbook_document' in validated_data and existing.passbook_document and existing.passbook_document != validated_data['passbook_document']:
                _safe_delete_photo(existing.passbook_document)
        except ProviderBankAccount.DoesNotExist:
            pass

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


class AdminProviderKYCSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source='provider.full_name', read_only=True)
    provider_email = serializers.EmailField(source='provider.user.email', read_only=True)
    pan_document_url = serializers.SerializerMethodField()
    aadhaar_document_url = serializers.SerializerMethodField()

    class Meta:
        model = ProviderKYC
        fields = [
            'id', 'provider_name', 'provider_email', 'provider_id',
            'pan_number', 'pan_status', 'pan_reject_reason', 'pan_document_url',
            'aadhaar_last4', 'aadhaar_status', 'aadhaar_reject_reason', 'aadhaar_document_url',
            'kyc_verified', 'submitted_at', 'updated_at',
        ]

    def get_pan_document_url(self, obj):
        return _resolve_file_url(obj.pan_document, self.context.get('request'))

    def get_aadhaar_document_url(self, obj):
        return _resolve_file_url(obj.aadhaar_document, self.context.get('request'))


class AdminProviderBankAccountSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source='provider.full_name', read_only=True)
    provider_email = serializers.EmailField(source='provider.user.email', read_only=True)
    passbook_url = serializers.SerializerMethodField()

    class Meta:
        model = ProviderBankAccount
        fields = [
            'id', 'provider_name', 'provider_email', 'provider_id',
            'account_holder_name', 'account_number', 'ifsc_code',
            'bank_name', 'branch_name', 'passbook_url',
            'is_verified', 'reject_reason', 'submitted_at', 'updated_at',
        ]

    def get_passbook_url(self, obj):
        return _resolve_file_url(obj.passbook_document, self.context.get('request'))




        





