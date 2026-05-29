from django.shortcuts import render
from rest_framework.permissions import AllowAny,IsAuthenticated
from .models import ServiceCategory,ProviderService,ProviderAvailability
from .serializers import ServiceCategorySerializer,ProviderServiceSerializer,ProviderServiceCreateSerializer,ProviderAvailabilitySerializer,ProviderAvailabilityCreateSerializer
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
# Create your views here.
class ServiceCategoryListView(ListAPIView):
    serializer_class=ServiceCategorySerializer
    permission_classes=[AllowAny]
    def get_queryset(self):
        qs= ServiceCategory.objects.filter(is_active=True)
        group = self.request.query_params.get('group')
        if group:
            qs = qs.filter(group=group)
        return qs


class ProviderServiceView(APIView):
    permission_classes = [IsAuthenticated]

    def _require_provider(self,request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return None
    def get(self,request):
        denied = self._require_provider(request)
        if denied:return denied
        services=request.user.provider_profile.services.select_related('category').all()
        serializer=ProviderServiceSerializer(services, many=True)
        return Response(serializer.data)
    
    def post(self,request):
        denied = self._require_provider(request)
        if denied:return denied

        serializer=ProviderServiceCreateSerializer(data=request.data,context={'request':request})
        if serializer.is_valid():
            service=serializer.save()
            return Response({
                'message': 'Service added. Upload documents to get verified.',
                'service': ProviderServiceSerializer(service).data,
            },status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class ProviderServiceDetailView(APIView):
    permission_classes=[IsAuthenticated]
    def _get_service(self, request, pk):
        try:
            return request.user.provider_profile.services.get(pk=pk)
        except ProviderService.DoesNotExist:
            return None
    def patch(self, request, pk):
        if not request.user.is_provider:
            return Response({'error': 'Only providers can access this.'}, status=status.HTTP_403_FORBIDDEN)

        service = self._get_service(request, pk)
        if not service:
            return Response({'error': 'Service not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProviderServiceCreateSerializer(
            service,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            service = serializer.save()
            return Response({
                'message': 'Service updated.',
                'service': ProviderServiceSerializer(service).data,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        if not request.user.is_provider:
            return Response({'error': 'Only providers can access this.'}, status=status.HTTP_403_FORBIDDEN)

        service = self._get_service(request, pk)
        if not service:
            return Response({'error': 'Service not found.'}, status=status.HTTP_404_NOT_FOUND)

        service.delete()
        return Response({'message': 'Service removed.'}, status=status.HTTP_204_NO_CONTENT)
    
class ProviderAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    def _require_provider(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return None

    def get(self, request):
        denied = self._require_provider(request)
        if denied: return denied

        availability = request.user.provider_profile.availability.all()
        serializer   = ProviderAvailabilitySerializer(availability, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Set or update a single day's availability."""
        denied = self._require_provider(request)
        if denied: return denied

        serializer = ProviderAvailabilityCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            availability = serializer.save()
            return Response({
                'message': 'Availability saved.',
                'availability': ProviderAvailabilitySerializer(availability).data,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




class ProviderAvailabilityDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_slot(self, request, pk):
        try:
            return request.user.provider_profile.availability.get(pk=pk)
        except ProviderAvailability.DoesNotExist:
            return None

    def patch(self, request, pk):
        if not request.user.is_provider:
            return Response({'error': 'Only providers can access this.'}, status=status.HTTP_403_FORBIDDEN)

        slot = self._get_slot(request, pk)
        if not slot:
            return Response({'error': 'Availability slot not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProviderAvailabilityCreateSerializer(
            slot, data=request.data, partial=True, context={'request': request}
        )
        if serializer.is_valid():
            slot = serializer.save()
            return Response(ProviderAvailabilitySerializer(slot).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if not request.user.is_provider:
            return Response({'error': 'Only providers can access this.'}, status=status.HTTP_403_FORBIDDEN)

        slot = self._get_slot(request, pk)
        if not slot:
            return Response({'error': 'Availability slot not found.'}, status=status.HTTP_404_NOT_FOUND)

        slot.delete()
        return Response({'message': 'Day removed from schedule.'}, status=status.HTTP_204_NO_CONTENT)



class ProviderOnlineToggleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_provider:
            return Response({'error': 'Only providers can access this.'}, status=status.HTTP_403_FORBIDDEN)

        profile = request.user.provider_profile

        if not profile.is_approved:
            return Response(
                {'error': 'Your profile must be approved before going online.'},
                status=status.HTTP_403_FORBIDDEN
            )

        profile.is_online = not profile.is_online
        profile.save(update_fields=['is_online'])

        return Response({
            'is_online': profile.is_online,
            'message':   'You are now online.' if profile.is_online else 'You are now offline.',
        })
    
