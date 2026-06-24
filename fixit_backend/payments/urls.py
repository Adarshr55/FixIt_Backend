from django.urls import path
from . import views

urlpatterns = [
    # Customer
    path('create-order/', views.CreateRazorpayOrderView.as_view(), name='create-order'),
    path('cash/',         views.CashPaymentView.as_view(),         name='cash-payment'),
    path('verify/',       views.VerifyRazorpayPaymentView.as_view(),name='verify-payment'),

    # Razorpay webhook — no auth
    path('webhook/',      views.RazorpayWebhookView.as_view(),     name='razorpay-webhook'),

    # Provider
    path('wallet/',       views.ProviderWalletView.as_view(),      name='provider-wallet'),
    path('withdraw/',     views.WithdrawalRequestView.as_view(),   name='withdrawal-request'),

    # Admin
    path('admin/withdrawals/',      views.AdminWithdrawalListView.as_view(),          name='admin-withdrawals'),
    path('admin/withdrawals/<int:pk>/', views.AdminWithdrawalActionView.as_view(),    name='admin-withdrawal-action'),
]