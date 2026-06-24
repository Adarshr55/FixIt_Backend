from django.shortcuts import render
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from accounts.permissions import IsPlatformAdmin
from .models import PromoBanner, CMSSection, HowItWorksStep
from .serializers import (
    PromoBannerSerializer,
    CMSSectionSerializer,
    HowItWorksStepSerializer,
)


# ── Public Views ──────────────────────────────────────────────────

class PublicPromoBannerView(APIView):
    """
    GET /api/marketing/banners/
    Returns currently active promo banners for landing page.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        now     = timezone.now()

        # manual filter since complex OR with null needs Q
        from django.db.models import Q
        banners = PromoBanner.objects.filter(
            is_active=True
        ).filter(
            Q(start_date__isnull=True) | Q(start_date__lte=now)
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=now)
        ).order_by('display_order')

        return Response(PromoBannerSerializer(banners, many=True).data)


class PublicCMSSectionView(APIView):
    """
    GET /api/marketing/sections/
    GET /api/marketing/sections/?key=hero

    Returns CMS content for landing page sections.
    Frontend reads headline, subtitle, CTA text from here.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        key      = request.query_params.get('key')
        sections = CMSSection.objects.filter(is_active=True)

        if key:
            sections = sections.filter(section_key=key)

        return Response(CMSSectionSerializer(sections, many=True).data)


class PublicHowItWorksView(APIView):
    """
    GET /api/marketing/how-it-works/
    Returns ordered steps for the How It Works section.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        steps = HowItWorksStep.objects.filter(is_active=True)
        return Response(HowItWorksStepSerializer(steps, many=True).data)


# ── Admin Views ───────────────────────────────────────────────────

class AdminPromoBannerView(APIView):
    """
    GET  /api/marketing/admin/banners/     — list all
    POST /api/marketing/admin/banners/     — create new banner
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        banners = PromoBanner.objects.all()
        return Response(PromoBannerSerializer(banners, many=True).data)

    def post(self, request):
        serializer = PromoBannerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminPromoBannerDetailView(APIView):
    """
    PATCH  /api/marketing/admin/banners/{pk}/
    DELETE /api/marketing/admin/banners/{pk}/
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def _get(self, pk):
        try:
            return PromoBanner.objects.get(pk=pk)
        except PromoBanner.DoesNotExist:
            return None

    def patch(self, request, pk):
        banner = self._get(pk)
        if not banner:
            return Response({'error': 'Banner not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PromoBannerSerializer(banner, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        banner = self._get(pk)
        if not banner:
            return Response({'error': 'Banner not found.'}, status=status.HTTP_404_NOT_FOUND)
        banner.delete()
        return Response({'message': 'Banner deleted.'}, status=status.HTTP_204_NO_CONTENT)


class AdminCMSSectionView(APIView):
    """
    GET  /api/marketing/admin/sections/
    POST /api/marketing/admin/sections/
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        sections = CMSSection.objects.all()
        return Response(CMSSectionSerializer(sections, many=True).data)

    def post(self, request):
        serializer = CMSSectionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminCMSSectionDetailView(APIView):
    """
    PATCH /api/marketing/admin/sections/{key}/
    Admin updates hero text, CTA text etc by section_key.
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def patch(self, request, key):
        try:
            section = CMSSection.objects.get(section_key=key)
        except CMSSection.DoesNotExist:
            return Response({'error': 'Section not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = CMSSectionSerializer(section, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)