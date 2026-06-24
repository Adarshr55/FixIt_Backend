from rest_framework import serializers
from .models import PromoBanner, CMSSection, HowItWorksStep


class PromoBannerSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model  = PromoBanner
        fields = [
            'id', 'title', 'subtitle',
            'coupon_code', 'discount_percent', 'discount_amount',
            'cta_text', 'cta_link', 'background_color',
            'image', 'is_active', 'start_date', 'end_date',
        ]

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class CMSSectionSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model  = CMSSection
        fields = [
            'section_key', 'title', 'subtitle',
            'body', 'cta_text', 'cta_link', 'image', 'image_url',
        ]

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return obj.image_url or None


class HowItWorksStepSerializer(serializers.ModelSerializer):
    class Meta:
        model  = HowItWorksStep
        fields = ['step_number', 'title', 'description', 'icon']