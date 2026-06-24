from rest_framework  import serializers
from profiles.models import ProviderProfile, ProviderDocument, CustomerProfile
from services.models import ProviderService
from accounts.models import User


# ── Document serializer ───────────────────────────────────────────

class AdminDocumentSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(
        source='service.category.name',
        read_only=True,
        default=None,
    )
    file_url = serializers.SerializerMethodField()

    class Meta:
        model  = ProviderDocument
        fields = [
            'id', 'doc_type', 'file', 'file_url', 'status',
            'reject_reason', 'service_name',
            'uploaded_at', 'verified_at',
        ]

    def get_file_url(self, obj):
        from profiles.serializers import _resolve_file_url
        return _resolve_file_url(obj.file, self.context.get('request'))


# ── Service serializer ────────────────────────────────────────────

class AdminProviderServiceSerializer(serializers.ModelSerializer):
    category_name  = serializers.CharField(source='category.name',  read_only=True)
    category_group = serializers.CharField(source='category.group', read_only=True)

    class Meta:
        model  = ProviderService
        fields = [
            'id', 'category_name', 'category_group',
            'skills', 'base_charge', 'hourly_rate',
            'verification_status', 'service_rating',
            'total_jobs', 'is_active',
        ]


# ── Provider list — lightweight ───────────────────────────────────

class AdminProviderListSerializer(serializers.ModelSerializer):
    email          = serializers.EmailField(source='user.email',     read_only=True)
    phone          = serializers.CharField(source='user.phone',      read_only=True)
    is_active      = serializers.BooleanField(source='user.is_active', read_only=True)
    document_count = serializers.SerializerMethodField()
    service_count  = serializers.SerializerMethodField()

    class Meta:
        model  = ProviderProfile
        fields = [
            'id', 'email', 'phone', 'full_name', 'city',
            'approval_status', 'overall_rating', 'is_online',
            'is_active', 'document_count', 'service_count', 'created_at',
        ]

    def get_document_count(self, obj):
        return obj.documents.count()

    def get_service_count(self, obj):
        return obj.services.count()


# ── Provider detail — full ────────────────────────────────────────

class AdminProviderDetailSerializer(serializers.ModelSerializer):
    email      = serializers.EmailField(source='user.email',     read_only=True)
    phone      = serializers.CharField(source='user.phone',      read_only=True)
    is_active  = serializers.BooleanField(source='user.is_active', read_only=True)
    documents  = AdminDocumentSerializer(many=True, read_only=True)
    services   = AdminProviderServiceSerializer(many=True, read_only=True)

    class Meta:
        model  = ProviderProfile
        fields = [
            'id', 'email', 'phone', 'full_name', 'profile_photo',
            'bio', 'experience_years', 'city', 'latitude', 'longitude',
            'service_radius_km', 'approval_status', 'rejection_reason',
            'overall_rating', 'is_online', 'is_active',
            'documents', 'services', 'created_at', 'updated_at',
        ]


# ── Provider approval action ──────────────────────────────────────

class ProviderApprovalSerializer(serializers.Serializer):
    ACTION_CHOICES = ['approve', 'reject', 'suspend', 'reactivate']
    action         = serializers.ChoiceField(choices=ACTION_CHOICES)
    reason         = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['action'] in ['reject', 'suspend'] and not attrs.get('reason', '').strip():
            raise serializers.ValidationError({
                'reason': f'A reason is required when {attrs["action"]}ing a provider.'
            })
        return attrs


# ── Document verification action ──────────────────────────────────

class DocumentVerificationSerializer(serializers.Serializer):
    ACTION_CHOICES = ['approve', 'reject']
    action         = serializers.ChoiceField(choices=ACTION_CHOICES)
    reject_reason  = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['action'] == 'reject' and not attrs.get('reject_reason', '').strip():
            raise serializers.ValidationError({
                'reject_reason': 'reject_reason is required when rejecting a document.'
            })
        return attrs


# ── Service verification action ───────────────────────────────────

class ServiceVerificationSerializer(serializers.Serializer):
    ACTION_CHOICES = ['verify', 'reject']
    action         = serializers.ChoiceField(choices=ACTION_CHOICES)
    reject_reason  = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['action'] == 'reject' and not attrs.get('reject_reason', '').strip():
            raise serializers.ValidationError({
                'reject_reason': 'reject_reason is required when rejecting a service.'
            })
        return attrs


# ── Customer list ─────────────────────────────────────────────────

class AdminCustomerListSerializer(serializers.ModelSerializer):
    email     = serializers.EmailField(source='user.email',       read_only=True)
    phone     = serializers.CharField(source='user.phone',        read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)

    class Meta:
        model  = CustomerProfile
        fields = [
            'id', 'email', 'phone', 'full_name',
            'profile_photo', 'is_active', 'created_at',
        ]


# ── User account action ───────────────────────────────────────────

class UserAccountActionSerializer(serializers.Serializer):
    ACTION_CHOICES = ['suspend', 'reactivate']
    action         = serializers.ChoiceField(choices=ACTION_CHOICES)


# ── Platform stats ────────────────────────────────────────────────

class PlatformStatsSerializer(serializers.Serializer):
    users     = serializers.DictField()
    providers = serializers.DictField()
    documents = serializers.DictField()
    services  = serializers.DictField()


# ── Admin CMS & Category Serializers ──────────────────────────────────
from services.models import ServiceCategory
from marketing.models import CMSSection, PromoBanner, HowItWorksStep

class AdminCategorySerializer(serializers.ModelSerializer):
    group_label = serializers.CharField(source='get_group_display', read_only=True)
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = ServiceCategory
        fields = [
            'id', 'name', 'group', 'group_label', 'icon', 'description', 'skill_tags',
            'slug', 'short_description', 'image', 'image_url', 'display_order', 'is_featured',
            'is_active', 'created_at', 'seo_title', 'seo_description', 'seo_keywords'
        ]
        read_only_fields = ['id', 'slug', 'created_at']


class AdminCMSSectionSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = CMSSection
        fields = [
            'id', 'section_key', 'title', 'subtitle', 'body', 'cta_text', 'cta_link',
            'image', 'image_url', 'is_active', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at']


class AdminPromoBannerSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = PromoBanner
        fields = [
            'id', 'title', 'subtitle', 'coupon_code', 'discount_percent', 'discount_amount',
            'cta_text', 'cta_link', 'background_color', 'image', 'is_active', 'start_date',
            'end_date', 'display_order', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AdminHowItWorksStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = HowItWorksStep
        fields = ['id', 'step_number', 'title', 'description', 'icon', 'is_active']
        read_only_fields = ['id']