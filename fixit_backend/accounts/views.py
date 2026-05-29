from django.shortcuts import render
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated,AllowAny,IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from .permissions import IsPlatformAdmin
from .serializers import( CustomerRegisterSerializer,
                         ProviderRegisterSerializer,
                         LoginSerializer,
                         ChangePasswordSerializer,
                         UserDetailSerializer,
                         AdminRegisterSerializer,
                         get_tokens_for_user
                         )
# Create your views here.

class CustomerRegisterView(APIView):
    permission_classes=[AllowAny]

    def post(self,request):
        serializer=CustomerRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user=serializer.save()
            tokens=get_tokens_for_user(user)
            return Response({
                'message':'Customer acconunt created successfully',
                'user':UserDetailSerializer(user).data,
                'tokens':tokens,

            },status=status.HTTP_201_CREATED)
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)

class ProviderRegisterView(APIView):
    permission_classes=[AllowAny]
    
    def post(self,request):
        serializer=ProviderRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user=serializer.save()
            tokens=get_tokens_for_user(user)
            return Response({
                'message':'Provider account created successfully',
                'user':UserDetailSerializer(user).data,
                'tokens':tokens,
            },status=status.HTTP_201_CREATED)
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
            return Response({
                'message':'Login successfull',
                'user':UserDetailSerializer(user).data,
                'tokens':tokens,
                'dashboard_url': DASHBOARD_ROUTES[user.role], 
            },status=status.HTTP_200_OK)
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)

    
class LogoutView(APIView):
    permission_classes=[IsAuthenticated]

    def post(self,request):
        refresh_token=request.data.get('refresh_token')
        if not refresh_token:
            return Response({
                'errors':'refresh token is required'
            },status=status.HTTP_400_BAD_REQUEST)
        try:
            token=RefreshToken(refresh_token)
            token.blacklist()
            return Response({
                'message':'Logged out sucessfull'
            },status=status.HTTP_200_OK)
        except TokenError:
            return Response({
                'error':'Invalid or expired token'
            },status=status.HTTP_400_BAD_REQUEST)
        

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



