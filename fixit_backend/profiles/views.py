from django.shortcuts import render
from .models import ProviderProfile,CustomerProfile,ProviderDocument
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response  import Response
from rest_framework import status
from .serializers import(
    ProviderProfileSerializer,CustomerProfileSerializer,ProviderDocumentSerializer,
    CustomerProfileCreateSerializer,ProviderProfileCreateSerializer,ProviderDocumentCreateSerializer)
# Create your views here.

class CustomerProfileView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        if not request.user.is_customer:
            return Response(
                {'error':'Only customer can access this'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile=request.user.customer_profile
            serializer=CustomerProfileSerializer(profile)
            return Response(serializer.data,status=status.HTTP_200_OK)
        except CustomerProfile.DoesNotExist:
            return Response(
                {"error": "Customer profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
    def post(self,request):
        if not request.user.is_customer:
            return Response(
                {'error':'only Customer can access this'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer=CustomerProfileCreateSerializer(data=request.data,context={'request':request})
        if serializer.is_valid():
            profile=serializer.save()
            return Response({
                'message': 'Profile created successfully.',
                'profile': CustomerProfileSerializer(profile).data,
            },status=status.HTTP_201_CREATED)
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self,request):
        if not request.user.is_customer:
            return Response(
                {'error':'only Customer can access this'},
                status=status.HTTP_403_FORBIDDEN   
            )
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response(
                {'error': 'Profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer=CustomerProfileCreateSerializer(
            profile,
            data=request.data,
            partial=True,
            context={'request':request}
        )
        if serializer.is_valid():
            profile = serializer.save()
            return Response({
                'message':'profile updated',
                'profile':CustomerProfileSerializer(profile).data
            })
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)
    

class ProviderProfileView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile    = request.user.provider_profile
            serializer = ProviderProfileSerializer(profile)
            return Response(serializer.data)
        except ProviderProfile.DoesNotExist:
            return Response(
                {'error': 'Profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
    def post(self,request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer=ProviderProfileCreateSerializer(data=request.data,context={'request':request})
        if serializer.is_valid():
            profile=serializer.save()
            return Response({
                'message': 'Profile submitted for review.',
                'profile': ProviderProfileSerializer(profile).data,
            },status=status.HTTP_201_CREATED)
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile = request.user.provider_profile
        except ProviderProfile.DoesNotExist:
            return Response(
                {"error": "Provider profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ProviderProfileCreateSerializer(
            profile,
            data=request.data,
            partial=True,
            context={"request": request},
         )
        if serializer.is_valid():
            profile = serializer.save()
            return Response(
            ProviderProfileSerializer(profile).data,
            status=status.HTTP_200_OK,
            )
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)
    
class ProviderDocumentView(APIView):
    permission_classes=[IsAuthenticated]

    def get(self,request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            document=request.user.provider_profile.documents.all()
            serializer=ProviderDocumentSerializer(document,many=True)
            return Response (serializer.data,status=status.HTTP_200_OK)
        except ProviderProfile.DoesNotExist:
            return Response( {'error': 'Complete your profile first.'},
                status=status.HTTP_404_NOT_FOUND
            )
    def post(self, request):
        if not request.user.is_provider:              # ← add this
            return Response(
            {'error': 'Only providers can upload documents.'},
            status=status.HTTP_403_FORBIDDEN
        )
        serializer = ProviderDocumentCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        document = serializer.save()
        return Response(
            ProviderDocumentSerializer(document).data,
            status=status.HTTP_201_CREATED,
        )
class ProfileStatusView(APIView):
        permission_classes = [IsAuthenticated]
        def get(self, request):

            user = request.user
            response = {
                "role":                user.role,
                "is_profile_complete": user.is_profile_complete,
            }

            if user.is_provider:
                try:
                    profile = user.provider_profile
                    response.update({
                    "approval_status": profile.approval_status,
                    "is_approved":     profile.is_approved,
                    "is_online":       profile.is_online,
                    })
                except Exception:
                    response.update({
                    "approval_status": None,
                    "is_approved":     False,
                    "is_online":       False,
                })

            return Response(response, status=status.HTTP_200_OK)
        





