from django.shortcuts import render
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from .permissions import IsPlatformAdmin
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from django.conf import settings
from .models import User, EmailOTP, PasswordResetToken
from django.utils import timezone
from datetime import timedelta

from .serializers import (
    CustomerRegisterSerializer,
    ProviderRegisterSerializer,
    LoginSerializer,
    ChangePasswordSerializer,
    UserDetailSerializer,
    AdminRegisterSerializer,
    GoogleAuthSerializer,
    get_tokens_for_user,
    send_otp_to_email,
    SendOTPRequestSerializer,
    VerifyOTPRequestSerializer,
    send_password_reset_email,
    ForgotPasswordRequestSerializer,
    ForgotPasswordVerifyOTPSerializer,
    ForgotPasswordResetSerializer,
)

def _set_refresh_cookie(response, refresh_token):
    response.set_cookie(
        key='refresh_token',
        value=refresh_token,
        httponly=True,
        secure=False,  # Set to True in production HTTPS
        samesite='Lax',
        max_age=7 * 24 * 3600  # 7 days
    )

class CustomerRegisterView(APIView):
    permission_classes=[AllowAny]

    def post(self,request):
        serializer=CustomerRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user=serializer.save()
            tokens=get_tokens_for_user(user)
            response = Response({
                'message':'Customer account created successfully',
                'user':UserDetailSerializer(user).data,
                'tokens':{
                    'access': tokens['access']
                },
            },status=status.HTTP_201_CREATED)
            _set_refresh_cookie(response, tokens['refresh'])
            return response
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)

class ProviderRegisterView(APIView):
    permission_classes=[AllowAny]
    
    def post(self,request):
        serializer=ProviderRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user=serializer.save()
            tokens=get_tokens_for_user(user)
            response = Response({
                'message':'Provider account created successfully',
                'user':UserDetailSerializer(user).data,
                'tokens':{
                    'access': tokens['access']
                },
            },status=status.HTTP_201_CREATED)
            _set_refresh_cookie(response, tokens['refresh'])
            return response
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)
    
DASHBOARD_ROUTES = {
    'customer': '/dashboard/customer',
    'provider': '/dashboard/provider',
    'admin':    '/dashboard/admin',
}
class LoginView(APIView):
    permission_classes=[AllowAny]

    def post(self,request):
        serializer=LoginSerializer(data=request.data,context = {'request': request})
        if serializer.is_valid():
            user=serializer.validated_data['user']
            tokens=get_tokens_for_user(user)
            response = Response({
                'message':'Login successful',
                'user':UserDetailSerializer(user).data,
                'tokens':{
                    'access': tokens['access']
                },
                'dashboard_url': DASHBOARD_ROUTES[user.role], 
            },status=status.HTTP_200_OK)
            _set_refresh_cookie(response, tokens['refresh'])
            return response
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)

    
class LogoutView(APIView):
    permission_classes=[IsAuthenticated]

    def post(self,request):
        refresh_token=request.data.get('refresh_token') or request.COOKIES.get('refresh_token')
        if not refresh_token:
            return Response({
                'error':'refresh token is required'
            },status=status.HTTP_400_BAD_REQUEST)
        try:
            token=RefreshToken(refresh_token)
            token.blacklist()
            response = Response({
                'message':'Logged out successfully'
            },status=status.HTTP_200_OK)
            response.delete_cookie('refresh_token')
            return response
        except TokenError:
            response = Response({
                'error':'Invalid or expired token'
            },status=status.HTTP_400_BAD_REQUEST)
            response.delete_cookie('refresh_token')
            return response

class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get('refresh') or request.COOKIES.get('refresh_token')
        
        if not refresh_token:
            return Response(
                {"detail": "Refresh token not found in cookies or body."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        mutable_data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        mutable_data['refresh'] = refresh_token
        
        serializer = self.get_serializer(data=mutable_data)
        
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])
            
        res_data = serializer.validated_data
        response = Response({
            'access': res_data['access']
        }, status=status.HTTP_200_OK)
        
        new_refresh = res_data.get('refresh')
        if new_refresh:
            _set_refresh_cookie(response, new_refresh)
            
        return response
        

class MeView(APIView):
    permission_classes=[IsAuthenticated]

    def get(self,request):
        return Response(UserDetailSerializer(request.user).data,status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    permission_classes=[IsAuthenticated]

    def post(self,request):
        serializer=ChangePasswordSerializer(data=request.data,context={'request':request})
        if serializer.is_valid():
            request.user.set_password(
                serializer.validated_data['new_password']
            )
            request.user.save()
            return Response(
                {'message':'password changed successfully.please login again.plaese login again'},
                 status=status.HTTP_200_OK
                )
        return Response(
            serializer.errors,status=status.HTTP_400_BAD_REQUEST
    )



class AdminCreateView(APIView):
    """
    Only an existing app-admin can create another admin.
    Never expose this to the public register page.
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def post(self, request):
        serializer = AdminRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user   = serializer.save()
            tokens = get_tokens_for_user(user)
            return Response({
                'message': 'Admin account created successfully.',
                'user'   : UserDetailSerializer(user).data,
                'tokens' : tokens,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    



class GoogleAuthView(APIView):
    permission_classes = [AllowAny]

    def post(self,request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        token = serializer.validated_data['id_token']
        role = serializer.validated_data.get('role')

        try:
             idinfo = google_id_token.verify_oauth2_token(
                token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
            )
        except ValueError:
            return Response({'error': 'Invalid Google token'}, status=status.HTTP_400_BAD_REQUEST)
        if not idinfo.get('email_verified'):
            return Response({'error': 'Google email is not verified'}, status=status.HTTP_400_BAD_REQUEST)
        
        email = idinfo['email'].lower().strip()
        google_sub = idinfo['sub']

        try:
            user = User.objects.get(email=email)
            changed = False
            if not user.google_id:
                user.google_id = google_sub
                changed = True
            if not user.is_email_verified:
                user.is_email_verified = True
                changed = True
            if not user.is_google_auth:
                user.is_google_auth = True
                changed = True
            if changed:
                user.save()
        except User.DoesNotExist:
            if not role:
                return Response({
                    'new_user': True,
                    'message': 'No account found. Please choose a role to continue.',
                }, status=status.HTTP_200_OK)

            user = User.objects.create_user(email=email, password=None, role=role)
            user.google_id = google_sub
            user.is_email_verified = True
            user.is_google_auth = True
            user.save()

        if not user.is_active:
            return Response(
                {'error': 'This account has been deactivated. Contact support.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        tokens = get_tokens_for_user(user)
        response = Response({
            'message': 'Google authentication successful',
            'user': UserDetailSerializer(user).data,
            'tokens': {'access': tokens['access']},
            'dashboard_url': DASHBOARD_ROUTES[user.role],
        }, status=status.HTTP_200_OK)
        _set_refresh_cookie(response, tokens['refresh'])
        return response
    
class SendEmailOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SendOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        send_otp_to_email(email)
        return Response({'message': 'Verification code sent to your email.'}, status=status.HTTP_200_OK)


class VerifyEmailOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        code = serializer.validated_data['otp_code']

        otp = EmailOTP.objects.filter(
            email=email, otp_code=code, is_used=False
        ).order_by('-created_at').first()

        if not otp:
            return Response({'error': 'Invalid OTP code.'}, status=status.HTTP_400_BAD_REQUEST)
        if not otp.is_valid():
            return Response({'error': 'OTP has expired. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)

        otp.is_used = True
        otp.is_verified = True
        otp.verified_at = timezone.now()
        otp.save()

        return Response({'message': 'Email verified successfully.'}, status=status.HTTP_200_OK)


class ForgotPasswordRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        send_password_reset_email(email)
        return Response({'message': 'OTP sent to your email.'}, status=status.HTTP_200_OK)


class ForgotPasswordVerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordVerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        code = serializer.validated_data['otp_code']

        otp = EmailOTP.objects.filter(
            email=email, otp_code=code, is_used=False
        ).order_by('-created_at').first()

        if not otp:
            return Response({'error': 'Invalid OTP code.'}, status=status.HTTP_400_BAD_REQUEST)
        if not otp.is_valid():
            return Response({'error': 'OTP has expired. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)

        # Mark OTP verified and used
        otp.is_used = True
        otp.is_verified = True
        otp.verified_at = timezone.now()
        otp.save()

        # Generate long-lived UUID reset token
        user = User.objects.get(email=email)
        # Invalidate any old unused reset tokens for this user
        PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)
        
        expires = timezone.now() + timedelta(minutes=15)
        reset_token = PasswordResetToken.objects.create(user=user, expires_at=expires)

        return Response({'reset_token': str(reset_token.token)}, status=status.HTTP_200_OK)


class ForgotPasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token_val = serializer.validated_data['reset_token']
        new_password = serializer.validated_data['new_password']

        reset_token = PasswordResetToken.objects.filter(token=token_val, is_used=False).first()
        if not reset_token or not reset_token.is_valid():
            return Response({'error': 'Invalid or expired password reset token.'}, status=status.HTTP_400_BAD_REQUEST)

        # Update user password
        user = reset_token.user
        user.set_password(new_password)
        user.save()

        # Invalidate token
        reset_token.is_used = True
        reset_token.save()

        return Response({'message': 'Password reset successful.'}, status=status.HTTP_200_OK)
