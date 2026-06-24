from django.utils  import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from accounts.permissions import IsPlatformAdmin
from accounts.models import User
from profiles.models import ProviderProfile, ProviderDocument, CustomerProfile
from services.models import ProviderService

from .serializers import (
    AdminProviderListSerializer,
    AdminProviderDetailSerializer,
    AdminDocumentSerializer,
    AdminProviderServiceSerializer,
    ProviderApprovalSerializer,
    DocumentVerificationSerializer,
    ServiceVerificationSerializer,
    AdminCustomerListSerializer,
    UserAccountActionSerializer,
    PlatformStatsSerializer,
)
from notifications.services import (
    notify_provider_approved,
    notify_provider_rejected,
    notify_document_approved,
    notify_document_rejected,
    notify_provider_suspended,
    notify_provider_reactivated,
    notify_service_verified,
    notify_service_rejected,
)



# ── Shared mixin ──────────────────────────────────────────────────

class AdminMixin:
    permission_classes = [IsAuthenticated, IsPlatformAdmin]


# ── Stats ─────────────────────────────────────────────────────────

class AdminStatsView(AdminMixin, APIView):
    """
    GET /api/admin/stats/
    Platform overview for admin dashboard.
    """

    def get(self, request):
        stats = {
            'users': {
                'total':     User.objects.count(),
                'customers': User.objects.filter(role='customer').count(),
                'providers': User.objects.filter(role='provider').count(),
                'admins':    User.objects.filter(role='admin').count(),
            },
            'providers': {
                'total':     ProviderProfile.objects.count(),
                'pending':   ProviderProfile.objects.filter(approval_status='pending').count(),
                'approved':  ProviderProfile.objects.filter(approval_status='approved').count(),
                'rejected':  ProviderProfile.objects.filter(approval_status='rejected').count(),
                'suspended': ProviderProfile.objects.filter(approval_status='suspended').count(),
            },
            'documents': {
                'total':    ProviderDocument.objects.count(),
                'pending':  ProviderDocument.objects.filter(status='pending').count(),
                'approved': ProviderDocument.objects.filter(status='approved').count(),
                'rejected': ProviderDocument.objects.filter(status='rejected').count(),
            },
            'services': {
                'total':      ProviderService.objects.count(),
                'unverified': ProviderService.objects.filter(verification_status='unverified').count(),
                'pending':    ProviderService.objects.filter(verification_status='pending').count(),
                'verified':   ProviderService.objects.filter(verification_status='verified').count(),
                'rejected':   ProviderService.objects.filter(verification_status='rejected').count(),
            },
        }
        return Response(PlatformStatsSerializer(stats).data)


# ── Provider management ───────────────────────────────────────────

class AdminProviderListView(AdminMixin, APIView):
    """
    GET /api/admin/providers/
    GET /api/admin/providers/?status=pending
    GET /api/admin/providers/?search=rajan
    """

    def get(self, request):
        providers = ProviderProfile.objects.select_related(
            'user'
        ).prefetch_related(
            'documents', 'services'
        ).order_by('-created_at')

        approval_status = request.query_params.get('status')
        if approval_status:
            if approval_status not in ['pending', 'approved', 'rejected', 'suspended']:
                return Response(
                    {'error': 'status must be pending, approved, rejected, or suspended.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            providers = providers.filter(approval_status=approval_status)

        search = request.query_params.get('search')
        if search:
            providers = providers.filter(
                full_name__icontains=search
            ) | providers.filter(
                user__email__icontains=search
            )

        serializer = AdminProviderListSerializer(providers, many=True)
        return Response({
            'count':   providers.count(),
            'results': serializer.data,
        })


class AdminProviderDetailView(AdminMixin, APIView):
    """
    GET   /api/admin/providers/{pk}/   — full provider detail
    PATCH /api/admin/providers/{pk}/   — approve / reject / suspend / reactivate
    """

    def _get_provider(self, pk):
        try:
            return ProviderProfile.objects.select_related(
                'user'
            ).prefetch_related(
                'documents__service__category',
                'services__category',
            ).get(pk=pk)
        except ProviderProfile.DoesNotExist:
            return None

    def get(self, request, pk):
        provider = self._get_provider(pk)
        if not provider:
            return Response({'error': 'Provider not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(AdminProviderDetailSerializer(provider, context={'request': request}).data)

    def patch(self, request, pk):
        provider = self._get_provider(pk)
        if not provider:
            return Response({'error': 'Provider not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProviderApprovalSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action = serializer.validated_data['action']
        reason = serializer.validated_data.get('reason', '')

        if action == 'approve':
            provider.approval_status  = 'approved'
            provider.rejection_reason = ''
            provider.user.is_active   = True
            provider.user.save(update_fields=['is_active'])
            message = f'{provider.full_name} has been approved.'
            provider.save()
            notify_provider_approved(provider) 

        elif action == 'reject':
            provider.approval_status  = 'rejected'
            provider.rejection_reason = reason
            provider.is_online        = False
            message = f'{provider.full_name} has been rejected.'
            provider.save()
            notify_provider_rejected(provider)

        elif action == 'suspend':
            provider.approval_status  = 'suspended'
            provider.rejection_reason = reason
            provider.is_online        = False
            provider.user.is_active   = False
            provider.user.save(update_fields=['is_active'])
            message = f'{provider.full_name} has been suspended.'
            provider.save()
            notify_provider_suspended(provider)


        elif action == 'reactivate':
            provider.approval_status  = 'approved'
            provider.rejection_reason = ''
            provider.user.is_active   = True
            provider.user.save(update_fields=['is_active'])
            message = f'{provider.full_name} has been reactivated.'
            provider.save()
            notify_provider_reactivated(provider)



        return Response({
            'message':  message,
            'provider': AdminProviderDetailSerializer(provider, context={'request': request}).data,
        })


# ── Document verification ─────────────────────────────────────────

class AdminDocumentListView(AdminMixin, APIView):
    """
    GET /api/admin/documents/
    GET /api/admin/documents/?status=pending
    """

    def get(self, request):
        documents = ProviderDocument.objects.select_related(
            'provider', 'service__category'
        ).order_by('-uploaded_at')

        doc_status = request.query_params.get('status')
        if doc_status:
            documents = documents.filter(status=doc_status)

        serializer = AdminDocumentSerializer(documents, many=True, context={'request': request})
        return Response({
            'count':   documents.count(),
            'results': serializer.data,
        })


class AdminDocumentVerifyView(AdminMixin, APIView):
    """
    PATCH /api/admin/documents/{pk}/
    Approve or reject a document.
    When approved and document is linked to a ProviderService,
    that service's verification_status is flipped to 'verified'.
    When rejected and service was verified, it flips back to 'pending'.
    """

    def patch(self, request, pk):
        try:
            document = ProviderDocument.objects.select_related(
                'provider', 'service'
            ).get(pk=pk)
        except ProviderDocument.DoesNotExist:
            return Response({'error': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = DocumentVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action = serializer.validated_data['action']

        if action == 'approve':
            document.status        = 'approved'
            document.verified_by   = request.user
            document.verified_at   = timezone.now()
            document.reject_reason = ''
            document.save()
            notify_document_approved(document)

            if document.service:
                document.service.verification_status = 'verified'
                document.service.save(update_fields=['verification_status', 'updated_at'])

            message = 'Document approved.'

        else:
            document.status        = 'rejected'
            document.reject_reason = serializer.validated_data['reject_reason']
            document.verified_by   = request.user
            document.verified_at   = timezone.now()
            document.save()
            notify_document_rejected(document)

            if document.service and document.service.verification_status == 'verified':
                document.service.verification_status = 'pending'
                document.service.save(update_fields=['verification_status', 'updated_at'])

            message = 'Document rejected.'

        return Response({
            'message':  message,
            'document': AdminDocumentSerializer(document).data,
        })


# ── Service verification ──────────────────────────────────────────

class AdminServiceVerifyView(AdminMixin, APIView):
    """
    PATCH /api/admin/services/{pk}/verify/
    Manual service verification — used when documents
    are not linked directly to a ProviderService.
    """

    def patch(self, request, pk):
        try:
            service = ProviderService.objects.select_related(
                'provider', 'category'
            ).get(pk=pk)
        except ProviderService.DoesNotExist:
            return Response({'error': 'Service not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ServiceVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action = serializer.validated_data['action']

        if action == 'verify':
            service.verification_status = 'verified'
            service.save(update_fields=['verification_status', 'updated_at'])
            notify_service_verified(service)
            return Response({
                'message':             f'{service.category.name} verified for {service.provider.full_name}.',
                'verification_status': service.verification_status,
                'service':             AdminProviderServiceSerializer(service).data,
            })

        else:
            service.verification_status = 'rejected'
            service.save(update_fields=['verification_status', 'updated_at'])
            notify_service_rejected(service)
            return Response({
                'message':             f'{service.category.name} rejected for {service.provider.full_name}.',
                'verification_status': service.verification_status,
                'reject_reason':       serializer.validated_data['reject_reason'],
                'service':             AdminProviderServiceSerializer(service).data,
            })


# ── Customer management ───────────────────────────────────────────

class AdminCustomerListView(AdminMixin, APIView):
    """
    GET /api/admin/customers/
    GET /api/admin/customers/?search=john
    """

    def get(self, request):
        customers = CustomerProfile.objects.select_related(
            'user'
        ).order_by('-created_at')

        search = request.query_params.get('search')
        if search:
            customers = customers.filter(
                full_name__icontains=search
            ) | customers.filter(
                user__email__icontains=search
            )

        serializer = AdminCustomerListSerializer(customers, many=True)
        return Response({
            'count':   customers.count(),
            'results': serializer.data,
        })


# ── User account actions ──────────────────────────────────────────

class AdminUserActionView(AdminMixin, APIView):
    """
    PATCH /api/admin/users/{user_id}/action/
    Suspend or reactivate any customer or provider account.
    Admins cannot be suspended through this endpoint.
    """

    def patch(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        if user.is_admin_user:
            return Response(
                {'error': 'Cannot suspend an admin account.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = UserAccountActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action = serializer.validated_data['action']

        if action == 'suspend':
            user.is_active = False
            user.save(update_fields=['is_active'])
            if user.is_provider:
                try:
                    user.provider_profile.is_online = False
                    user.provider_profile.save(update_fields=['is_online'])
                except Exception:
                    pass
            message = f'{user.email} has been suspended.'

        else:
            user.is_active = True
            user.save(update_fields=['is_active'])
            message = f'{user.email} has been reactivated.'

        return Response({'message': message})


# ── Admin CMS & Category Management Views ──────────────────────────────
from services.models import ServiceCategory
from marketing.models import CMSSection, PromoBanner, HowItWorksStep
from .serializers import (
    AdminCategorySerializer,
    AdminCMSSectionSerializer,
    AdminPromoBannerSerializer,
    AdminHowItWorksStepSerializer,
)

class AdminCategoryListView(AdminMixin, APIView):
    """
    GET  /api/admin_panel/categories/      — list all categories (active & inactive)
    POST /api/admin_panel/categories/      — create new category (supports multipart image upload)
    """
    def get(self, request):
        categories = ServiceCategory.objects.all().order_by('display_order', 'name')
        serializer = AdminCategorySerializer(categories, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = AdminCategorySerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminCategoryDetailView(AdminMixin, APIView):
    """
    GET    /api/admin_panel/categories/{pk}/  — get category detail
    PATCH  /api/admin_panel/categories/{pk}/  — edit category (supports multipart image upload)
    DELETE /api/admin_panel/categories/{pk}/  — delete category
    """
    def _get_category(self, pk):
        try:
            return ServiceCategory.objects.get(pk=pk)
        except ServiceCategory.DoesNotExist:
            return None

    def get(self, request, pk):
        category = self._get_category(pk)
        if not category:
            return Response({'error': 'Category not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminCategorySerializer(category, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk):
        category = self._get_category(pk)
        if not category:
            return Response({'error': 'Category not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminCategorySerializer(category, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        category = self._get_category(pk)
        if not category:
            return Response({'error': 'Category not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            category.delete()
            return Response({'message': 'Category deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({'error': f'Cannot delete category because it is referenced elsewhere: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


class AdminCMSSectionListView(AdminMixin, APIView):
    """
    GET  /api/admin_panel/cms-sections/    — list all sections
    POST /api/admin_panel/cms-sections/    — create a section
    """
    def get(self, request):
        sections = CMSSection.objects.all().order_by('section_key')
        serializer = AdminCMSSectionSerializer(sections, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = AdminCMSSectionSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminCMSSectionDetailView(AdminMixin, APIView):
    """
    GET    /api/admin_panel/cms-sections/{pk_or_key}/ — get section
    PATCH  /api/admin_panel/cms-sections/{pk_or_key}/ — update section (supports image upload)
    DELETE /api/admin_panel/cms-sections/{pk_or_key}/ — delete section
    """
    def _get_section(self, pk_or_key):
        try:
            if pk_or_key.isdigit():
                return CMSSection.objects.get(pk=int(pk_or_key))
            else:
                return CMSSection.objects.get(section_key=pk_or_key)
        except CMSSection.DoesNotExist:
            return None

    def get(self, request, pk_or_key):
        section = self._get_section(pk_or_key)
        if not section:
            return Response({'error': 'CMS Section not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminCMSSectionSerializer(section, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk_or_key):
        section = self._get_section(pk_or_key)
        if not section:
            return Response({'error': 'CMS Section not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminCMSSectionSerializer(section, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk_or_key):
        section = self._get_section(pk_or_key)
        if not section:
            return Response({'error': 'CMS Section not found.'}, status=status.HTTP_404_NOT_FOUND)
        section.delete()
        return Response({'message': 'CMS Section deleted.'}, status=status.HTTP_204_NO_CONTENT)


class AdminPromoBannerListView(AdminMixin, APIView):
    """
    GET  /api/admin_panel/promo-banners/   — list all promo banners
    POST /api/admin_panel/promo-banners/   — create promo banner (supports image upload)
    """
    def get(self, request):
        banners = PromoBanner.objects.all().order_by('display_order', '-created_at')
        serializer = AdminPromoBannerSerializer(banners, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = AdminPromoBannerSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminPromoBannerDetailView(AdminMixin, APIView):
    """
    GET    /api/admin_panel/promo-banners/{pk}/
    PATCH  /api/admin_panel/promo-banners/{pk}/
    DELETE /api/admin_panel/promo-banners/{pk}/
    """
    def _get_banner(self, pk):
        try:
            return PromoBanner.objects.get(pk=pk)
        except PromoBanner.DoesNotExist:
            return None

    def get(self, request, pk):
        banner = self._get_banner(pk)
        if not banner:
            return Response({'error': 'Promo banner not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminPromoBannerSerializer(banner, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk):
        banner = self._get_banner(pk)
        if not banner:
            return Response({'error': 'Promo banner not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminPromoBannerSerializer(banner, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        banner = self._get_banner(pk)
        if not banner:
            return Response({'error': 'Promo banner not found.'}, status=status.HTTP_404_NOT_FOUND)
        banner.delete()
        return Response({'message': 'Promo banner deleted.'}, status=status.HTTP_204_NO_CONTENT)


class AdminHowItWorksStepListView(AdminMixin, APIView):
    """
    GET  /api/admin_panel/how-it-works-steps/
    POST /api/admin_panel/how-it-works-steps/
    """
    def get(self, request):
        steps = HowItWorksStep.objects.all().order_by('step_number')
        serializer = AdminHowItWorksStepSerializer(steps, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = AdminHowItWorksStepSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminHowItWorksStepDetailView(AdminMixin, APIView):
    """
    GET    /api/admin_panel/how-it-works-steps/{pk}/
    PATCH  /api/admin_panel/how-it-works-steps/{pk}/
    DELETE /api/admin_panel/how-it-works-steps/{pk}/
    """
    def _get_step(self, pk):
        try:
            return HowItWorksStep.objects.get(pk=pk)
        except HowItWorksStep.DoesNotExist:
            return None

    def get(self, request, pk):
        step = self._get_step(pk)
        if not step:
            return Response({'error': 'How it works step not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminHowItWorksStepSerializer(step)
        return Response(serializer.data)

    def patch(self, request, pk):
        step = self._get_step(pk)
        if not step:
            return Response({'error': 'How it works step not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminHowItWorksStepSerializer(step, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        step = self._get_step(pk)
        if not step:
            return Response({'error': 'How it works step not found.'}, status=status.HTTP_404_NOT_FOUND)
        step.delete()
        return Response({'message': 'How it works step deleted.'}, status=status.HTTP_204_NO_CONTENT)