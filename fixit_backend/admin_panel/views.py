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
        return Response(AdminProviderDetailSerializer(provider).data)

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

        elif action == 'reject':
            provider.approval_status  = 'rejected'
            provider.rejection_reason = reason
            provider.is_online        = False
            message = f'{provider.full_name} has been rejected.'

        elif action == 'suspend':
            provider.approval_status  = 'suspended'
            provider.rejection_reason = reason
            provider.is_online        = False
            provider.user.is_active   = False
            provider.user.save(update_fields=['is_active'])
            message = f'{provider.full_name} has been suspended.'

        elif action == 'reactivate':
            provider.approval_status  = 'approved'
            provider.rejection_reason = ''
            provider.user.is_active   = True
            provider.user.save(update_fields=['is_active'])
            message = f'{provider.full_name} has been reactivated.'

        provider.save()

        return Response({
            'message':  message,
            'provider': AdminProviderDetailSerializer(provider).data,
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

        serializer = AdminDocumentSerializer(documents, many=True)
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
            return Response({
                'message':             f'{service.category.name} verified for {service.provider.full_name}.',
                'verification_status': service.verification_status,
                'service':             AdminProviderServiceSerializer(service).data,
            })

        else:
            service.verification_status = 'rejected'
            service.save(update_fields=['verification_status', 'updated_at'])
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