from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import User
from django.conf import settings



def get_tokens_for_user(user):
        refresh=RefreshToken.for_user(user)
        refresh['role']=user.role
        refresh['email']=user.email
        return {'refresh':str(refresh),'access':str(refresh.access_token)}

class BaseRegisterSerializer(serializers.Serializer): 
    email=serializers.EmailField()
    password=serializers.CharField(write_only=True, validators=[validate_password])
    password2=serializers.CharField(write_only=True)
    ROLE=None
    def validate_email(self, value):
        value=value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError( "An account with this email already exists.")
        return value
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError(
                 {"password": "Passwords do not match."}
            )
        return attrs
    
    def create(self,validated_data):
        if self.ROLE is None:
            raise NotImplementedError("Subclasses must define a ROLE attribute.")
        validated_data.pop('password2')
        return User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=self.ROLE
        )
    
class CustomerRegisterSerializer(BaseRegisterSerializer):
    ROLE='customer'

class ProviderRegisterSerializer(BaseRegisterSerializer):
    ROLE='provider'


class LoginSerializer(serializers.Serializer):
    email=serializers.EmailField()
    password=serializers.CharField(write_only= True)

    def validate(self,attrs):
        email=attrs.get('email',"").lower().strip()
        password=attrs.get('password','')

        user=authenticate(
            request=self.context.get('request'),
            username=email,
            password=password
        )

        if not user:
            raise serializers.ValidationError('Invalid email or password.')
        if not user.is_active:
            raise serializers.ValidationError('This account has been deactivated. Contact support.')
        
        attrs['user'] = user
        return attrs
    


class UserDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model=User
        fields=[
            "id",
            "email",
            "phone",
            "role",
            "is_active",
            # "is_phone_verified",
            "is_profile_complete",
            "date_joined",
        ]

        read_only_fields = fields


class ChangePasswordSerializer(serializers.Serializer):
    old_password=serializers.CharField(write_only=True)
    new_password=serializers.CharField(write_only=True,validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True)


    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(
                'Old password is incorrect.'
            )
        return value
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({
                'new_password': 'New passwords do not match.'
            })
        return attrs


