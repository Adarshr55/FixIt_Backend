from django.shortcuts import render
from .models import ProviderProfile,CustomerProfile,ProviderDocument,ProviderBankAccount,ProviderKYC,CustomerAddress
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response  import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from accounts.permissions import IsPlatformAdmin
from django.utils import timezone
from .serializers import(
    ProviderProfileSerializer,CustomerProfileSerializer,ProviderDocumentSerializer,
    CustomerProfileCreateSerializer,ProviderProfileCreateSerializer,ProviderDocumentCreateSerializer,ProviderKYCSerializer,
    ProviderKYCSubmitSerializer,AdminKYCActionSerializer,ProviderBankAccountSerializer,ProviderBankAccountSubmitSerializer,
    AdminBankAccountActionSerializer, AdminProviderKYCSerializer, AdminProviderBankAccountSerializer,
    CustomerAddressSerializer
    )
# Create your views here.

class CustomerProfileView(APIView):
    permission_classes=[IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    def get(self,request):
        if not request.user.is_customer:
            return Response(
                {'error':'Only customer can access this'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile=request.user.customer_profile
            serializer=CustomerProfileSerializer(profile, context={'request': request})
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
                'profile': CustomerProfileSerializer(profile, context={'request': request}).data,
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
                'profile':CustomerProfileSerializer(profile, context={'request': request}).data
            })
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)
    

class ProviderProfileView(APIView):
    permission_classes=[IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    def get(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile    = request.user.provider_profile
            serializer = ProviderProfileSerializer(profile, context={'request': request})
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
                'profile': ProviderProfileSerializer(profile, context={'request': request}).data,
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
                ProviderProfileSerializer(profile, context={'request': request}).data,
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)
    
class ProviderDocumentView(APIView):
    permission_classes=[IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self,request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            document=request.user.provider_profile.documents.all()
            serializer=ProviderDocumentSerializer(document,many=True,context={'request': request})
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
            ProviderDocumentSerializer(document, context={'request': request}).data,
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
                    "is_approved":profile.is_approved,
                    "is_online":profile.is_online,
                    'kyc_verified': getattr(profile.kyc, 'kyc_verified', False) if hasattr(profile, 'kyc') else False,
                    'bank_verified':getattr(profile.bank_account, 'is_verified', False) if hasattr(profile, 'bank_account') else False,
                     })  
                except Exception:
                    response.update({
                    "approval_status": None,
                    "is_approved":     False,
                    "is_online":       False,
                })

            return Response(response, status=status.HTTP_200_OK)
        
class ProviderKYCView(APIView):
    """
    GET  /api/profiles/provider/kyc/ — provider checks their KYC status
    POST /api/profiles/provider/kyc/ — provider submits KYC documents
    Must use multipart/form-data for file upload.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            kyc = request.user.provider_profile.kyc
            return Response(ProviderKYCSerializer(kyc, context={'request': request}).data)
        except ProviderKYC.DoesNotExist:
            return Response({
                'kyc_verified': False,
                'message': 'No KYC submitted yet.',
            })

    def post(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can submit KYC.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile = request.user.provider_profile
        except ProviderProfile.DoesNotExist:
            return Response(
                {'error': 'Complete your provider profile first.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # block resubmission if already verified
        try:
            existing = profile.kyc
            if existing.kyc_verified:
                return Response(
                    {'error': 'KYC is already verified. No changes allowed.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except ProviderKYC.DoesNotExist:
            pass

        serializer = ProviderKYCSubmitSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            kyc = serializer.save()
            # notify admins
            from notifications.services import notify_kyc_submitted
            notify_kyc_submitted(kyc)
            return Response({
                'message': 'KYC submitted successfully. Admin will verify within 24-48 hours.',
                'kyc': ProviderKYCSerializer(kyc, context={'request': request}).data,
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminKYCActionView(APIView):
    """
    PATCH /api/profiles/admin/kyc/{provider_id}/
    Admin approves or rejects PAN or Aadhaar individually.
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def patch(self, request, provider_id):
        try:
            kyc = ProviderKYC.objects.select_related(
                'provider__user'
            ).get(provider_id=provider_id)
        except ProviderKYC.DoesNotExist:
            return Response(
                {'error': 'KYC not found for this provider.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = AdminKYCActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        doc_type      = serializer.validated_data['document_type']
        action        = serializer.validated_data['action']
        reject_reason = serializer.validated_data.get('reject_reason', '')

        from notifications.services import (
            notify_kyc_pan_approved, notify_kyc_pan_rejected,
            notify_kyc_aadhaar_approved, notify_kyc_aadhaar_rejected,
            notify_kyc_fully_verified,
        )

        if doc_type == 'pan':
            if action == 'approve':
                kyc.pan_status        = 'approved'
                kyc.pan_reject_reason = ''
                kyc.save(update_fields=['pan_status', 'pan_reject_reason', 'updated_at'])
                notify_kyc_pan_approved(kyc.provider)
            else:
                kyc.pan_status        = 'rejected'
                kyc.pan_reject_reason = reject_reason
                kyc.save(update_fields=['pan_status', 'pan_reject_reason', 'updated_at'])
                notify_kyc_pan_rejected(kyc.provider, reject_reason)

        elif doc_type == 'aadhaar':
            if action == 'approve':
                kyc.aadhaar_status        = 'approved'
                kyc.aadhaar_reject_reason = ''
                kyc.save(update_fields=['aadhaar_status', 'aadhaar_reject_reason', 'updated_at'])
                notify_kyc_aadhaar_approved(kyc.provider)
            else:
                kyc.aadhaar_status        = 'rejected'
                kyc.aadhaar_reject_reason = reject_reason
                kyc.save(update_fields=['aadhaar_status', 'aadhaar_reject_reason', 'updated_at'])
                notify_kyc_aadhaar_rejected(kyc.provider, reject_reason)

        # check if both approved now
        kyc.verified_by = request.user
        kyc.verified_at = timezone.now()
        kyc.save(update_fields=['verified_by', 'verified_at'])
        kyc.check_and_set_verified()

        if kyc.kyc_verified:
            notify_kyc_fully_verified(kyc.provider)

        return Response({
            'message': f'{doc_type.upper()} {action}d successfully.',
            'kyc': ProviderKYCSerializer(kyc).data,
        })
    

# ── Bank Account Views ────────────────────────────────────────────

class ProviderBankAccountView(APIView):
    """
    GET  /api/profiles/provider/bank-account/ — provider checks bank status
    POST /api/profiles/provider/bank-account/ — provider submits bank details
    Must use multipart/form-data.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            bank = request.user.provider_profile.bank_account
            return Response(
                ProviderBankAccountSerializer(bank, context={'request': request}).data
            )
        except ProviderBankAccount.DoesNotExist:
            return Response({
                'is_verified': False,
                'message': 'No bank account submitted yet.',
            })

    def post(self, request):
        if not request.user.is_provider:
            return Response(
                {'error': 'Only providers can submit bank details.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile = request.user.provider_profile
        except ProviderProfile.DoesNotExist:
            return Response(
                {'error': 'Complete your provider profile first.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            kyc = profile.kyc
            if not kyc.kyc_verified:
                return Response(
                {'error': 'Complete identity verification (KYC) before adding bank details.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ProviderKYC.DoesNotExist:
            return Response(
            {'error': 'Submit your KYC documents before adding bank details.'},
            status=status.HTTP_400_BAD_REQUEST
        )

        # block changes if already verified
        try:
            existing = profile.bank_account
            if existing.is_verified:
                return Response(
                    {'error': 'Bank account is already verified. Contact support to update.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except ProviderBankAccount.DoesNotExist:
            pass

        serializer = ProviderBankAccountSubmitSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            bank = serializer.save()
            from notifications.services import notify_bank_account_submitted
            notify_bank_account_submitted(bank)
            return Response({
                'message': 'Bank account submitted. Admin will verify within 24-48 hours.',
                'bank_account': ProviderBankAccountSerializer(
                    bank, context={'request': request}
                ).data,
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    


class AdminBankAccountActionView(APIView):
    """
    PATCH /api/profiles/admin/bank-account/{provider_id}/
    Admin approves or rejects a provider's bank account.
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def patch(self, request, provider_id):
        try:
            bank = ProviderBankAccount.objects.select_related(
                'provider__user'
            ).get(provider_id=provider_id)
        except ProviderBankAccount.DoesNotExist:
            return Response(
                {'error': 'Bank account not found for this provider.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = AdminBankAccountActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action        = serializer.validated_data['action']
        reject_reason = serializer.validated_data.get('reject_reason', '')

        from notifications.services import (
            notify_bank_account_approved,
            notify_bank_account_rejected,
        )

        if action == 'approve':
            bank.is_verified   = True
            bank.reject_reason = ''
            bank.verified_by   = request.user
            bank.verified_at   = timezone.now()
            bank.save(update_fields=[
                'is_verified', 'reject_reason',
                'verified_by', 'verified_at', 'updated_at'
            ])
            notify_bank_account_approved(bank)
            message = 'Bank account approved.'
        else:
            bank.is_verified   = False
            bank.reject_reason = reject_reason
            bank.verified_by   = request.user
            bank.verified_at   = timezone.now()
            bank.save(update_fields=[
                'is_verified', 'reject_reason',
                'verified_by', 'verified_at', 'updated_at'
            ])
            notify_bank_account_rejected(bank, reject_reason)
            message = 'Bank account rejected.'

        return Response({
            'message': message,
            'bank_account': ProviderBankAccountSerializer(
                bank, context={'request': request}
            ).data,
        })


class IFSCLookupView(APIView):
    """
    GET /api/profiles/ifsc/{ifsc_code}/
    Frontend can call this to show bank name before form submission.
    Free Razorpay public API — no auth needed.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, ifsc_code):
        import requests as req
        ifsc_code = ifsc_code.strip().upper()

        import re
        if not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', ifsc_code):
            return Response(
                {'error': 'Invalid IFSC format.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            response = req.get(
                f'https://ifsc.razorpay.com/{ifsc_code}',
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                return Response({
                    'ifsc':    ifsc_code,
                    'bank':    data.get('BANK', ''),
                    'branch':  data.get('BRANCH', ''),
                    'city':    data.get('CITY', ''),
                    'state':   data.get('STATE', ''),
                })
            return Response(
                {'error': 'IFSC not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception:
            return Response(
                {'error': 'IFSC lookup service unavailable.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class AdminKYCListView(APIView):
    """
    GET /api/profiles/admin/kyc/
    List all provider KYC submissions.
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        status_filter = request.query_params.get('status')
        kycs = ProviderKYC.objects.select_related('provider__user').all().order_by('-submitted_at')
        
        if status_filter == 'pending':
            kycs = kycs.filter(kyc_verified=False)
        elif status_filter == 'verified':
            kycs = kycs.filter(kyc_verified=True)
            
        serializer = AdminProviderKYCSerializer(kycs, many=True, context={'request': request})
        return Response({
            'count': kycs.count(),
            'results': serializer.data
        })


class AdminBankAccountListView(APIView):
    """
    GET /api/profiles/admin/bank-account/
    List all provider Bank account details.
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        status_filter = request.query_params.get('status')
        banks = ProviderBankAccount.objects.select_related('provider__user').all().order_by('-submitted_at')
        
        if status_filter == 'pending':
            banks = banks.filter(is_verified=False)
        elif status_filter == 'verified':
            banks = banks.filter(is_verified=True)
            
        serializer = AdminProviderBankAccountSerializer(banks, many=True, context={'request': request})
        return Response({
            'count': banks.count(),
            'results': serializer.data
        })


class CustomerAddressListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile = request.user.customer_profile
            addresses = CustomerAddress.objects.filter(customer=profile)
            serializer = CustomerAddressSerializer(addresses, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CustomerProfile.DoesNotExist:
            return Response(
                {"error": "Customer profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

    def post(self, request):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response(
                {"error": "Customer profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = CustomerAddressSerializer(data=request.data)
        if serializer.is_valid():
            is_default = serializer.validated_data.get('is_default', False)
            if not CustomerAddress.objects.filter(customer=profile).exists():
                is_default = True
            
            address = serializer.save(customer=profile, is_default=is_default)
            return Response(CustomerAddressSerializer(address).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomerAddressDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, profile):
        try:
            return CustomerAddress.objects.get(pk=pk, customer=profile)
        except CustomerAddress.DoesNotExist:
            return None

    def get(self, request, pk):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response(
                {"error": "Customer profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        address = self.get_object(pk, profile)
        if not address:
            return Response(
                {"error": "Address not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = CustomerAddressSerializer(address)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response(
                {"error": "Customer profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        address = self.get_object(pk, profile)
        if not address:
            return Response(
                {"error": "Address not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = CustomerAddressSerializer(address, data=request.data, partial=True)
        if serializer.is_valid():
            saved_address = serializer.save()
            
            if not saved_address.is_default:
                if not CustomerAddress.objects.filter(customer=profile, is_default=True).exists():
                    other = CustomerAddress.objects.filter(customer=profile).order_by('-updated_at').first()
                    if other:
                        other.is_default = True
                        other.save()
            return Response(CustomerAddressSerializer(saved_address).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if not request.user.is_customer:
            return Response(
                {'error': 'Only customers can access this.'},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response(
                {"error": "Customer profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        address = self.get_object(pk, profile)
        if not address:
            return Response(
                {"error": "Address not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        was_default = address.is_default
        address.delete()
        
        if was_default:
            other = CustomerAddress.objects.filter(customer=profile).order_by('-created_at').first()
            if other:
                other.is_default = True
                other.save()
                
        return Response(status=status.HTTP_204_NO_CONTENT)

        
