from rest_framework import serializers
from.models import ServiceCategory,ProviderService,ProviderAvailability

class ServiceCategorySerializer(serializers.ModelSerializer):
    group_label = serializers.CharField(source='get_group_display', read_only=True)
    class Meta:
        model=ServiceCategory
        fields=['id','name','group','group_label','icon','description','skill_tags']

class ProviderServiceSerializer(serializers.ModelSerializer):
     category_name  = serializers.CharField(source='category.name',  read_only=True)
     category_icon  = serializers.CharField(source='category.icon',  read_only=True)
     category_group = serializers.CharField(source='category.group', read_only=True)
     provider_name = serializers.CharField(source="provider.full_name", read_only=True)
     class Meta:
         model=ProviderService
         fields = [
            'id',"provider_name", 'category', 'category_name', 'category_icon', 'category_group',
            'skills', 'base_charge', 'hourly_rate',
            'verification_status', 'service_rating', 'total_jobs',
            'completion_rate', 'is_active', 'created_at',
        ]
         read_only_fields = [
             'id', 'verification_status', 'service_rating',
            'total_jobs', 'completion_rate', 'created_at',
        ]
class ProviderServiceCreateSerializer(serializers.Serializer):
     category    = serializers.PrimaryKeyRelatedField(queryset=ServiceCategory.objects.filter(is_active=True))
     skills      = serializers.ListField(child=serializers.CharField(), required=False, default=list)
     base_charge = serializers.DecimalField(max_digits=10, decimal_places=2)
     hourly_rate = serializers.DecimalField(max_digits=8,  decimal_places=2)

     def validate_skills(self, value):
        # skills must be from the category's skill_tags
        category = self.initial_data.get('category')
        if category:
            try:
                cat = ServiceCategory.objects.get(pk=category)
                invalid = [s for s in value if s not in cat.skill_tags]
                if invalid:
                    raise serializers.ValidationError(
                        f"Invalid skills for this category: {invalid}"
                    )
            except ServiceCategory.DoesNotExist:
                pass
        return value
     def validate(self, attrs):
        request  = self.context['request']
        provider = request.user.provider_profile
        category = attrs.get('category')

        # on create — block duplicate service
        if not self.instance:
            if ProviderService.objects.filter(provider=provider, category=category).exists():
                raise serializers.ValidationError(
                    f"You already offer {category.name}. Edit the existing service instead."
                )
        return attrs
     def create(self, validated_data):
        provider = self.context['request'].user.provider_profile
        return ProviderService.objects.create(
            provider    = provider,
            category    = validated_data['category'],
            skills      = validated_data.get('skills', []),
            base_charge = validated_data['base_charge'],
            hourly_rate = validated_data['hourly_rate'],
        )
     def update(self, instance, validated_data):
        instance.skills      = validated_data.get('skills',      instance.skills)
        instance.base_charge = validated_data.get('base_charge', instance.base_charge)
        instance.hourly_rate = validated_data.get('hourly_rate', instance.hourly_rate)
        instance.is_active   = validated_data.get('is_active',   instance.is_active)
        instance.save()
        return instance
     
class ProviderAvailabilitySerializer(serializers.ModelSerializer):
    day_name = serializers.CharField(source='get_day_display', read_only=True)

    class Meta:
        model  = ProviderAvailability
        fields = ['id', 'day', 'day_name', 'start_time', 'end_time',
                  'is_active', 'emergency_available']
        read_only_fields = ['id']


class ProviderAvailabilityCreateSerializer(serializers.Serializer):
    day                 = serializers.IntegerField(min_value=0, max_value=6)
    start_time          = serializers.TimeField()
    end_time            = serializers.TimeField()
    is_active           = serializers.BooleanField(default=True)
    emergency_available = serializers.BooleanField(default=False)

    def validate(self, attrs):
        start_time = attrs.get('start_time')
        end_time = attrs.get('end_time')

        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError('start_time must be before end_time.')
        return attrs

    def create(self, validated_data):
        provider = self.context['request'].user.provider_profile
        # upsert — provider can re-set a day's schedule
        availability, _ = ProviderAvailability.objects.update_or_create(
            provider = provider,
            day      = validated_data['day'],
            defaults = {
                'start_time':          validated_data['start_time'],
                'end_time':            validated_data['end_time'],
                'is_active':           validated_data['is_active'],
                'emergency_available': validated_data['emergency_available'],
            }
        )
        return availability

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance