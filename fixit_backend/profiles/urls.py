from django.urls import path
from .import views 



urlpatterns=[
    path('customer/',views.CustomerProfileView.as_view(),name='customer-profile'),
    path('provider/',views.ProviderProfileView.as_view(),name='provider-profile'),
    path('provider/document/',views.ProviderDocumentView.as_view(),name='provider-document'),
    # Provider KYC
    path('provider/kyc/',views.ProviderKYCView.as_view(), name='provider-kyc'),
    # Provider bank account
    path('provider/bank-account/',views.ProviderBankAccountView.as_view(), name='provider-bank-account'),
     # IFSC lookup
    path('ifsc/<str:ifsc_code>/',views.IFSCLookupView.as_view(), name='ifsc-lookup'),
    # Profile status
    path('status/',views.ProfileStatusView.as_view(), name='profile-status'),
     # Admin — KYC and bank
    path('admin/kyc/<int:provider_id>/',views.AdminKYCActionView.as_view(),name='admin-kyc-action'),
    path('admin/bank-account/<int:provider_id>/',views.AdminBankAccountActionView.as_view(), name='admin-bank-action'),

]   