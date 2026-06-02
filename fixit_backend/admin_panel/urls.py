from django.urls import path
from . import views

urlpatterns = [
    # stats
    path('stats/',views.AdminStatsView.as_view(),          name='admin-stats'),

    # provider management
    path('providers/',views.AdminProviderListView.as_view(),   name='admin-provider-list'),
    path('providers/<int:pk>/',views.AdminProviderDetailView.as_view(), name='admin-provider-detail'),

    # document verification
    path('documents/',views.AdminDocumentListView.as_view(),   name='admin-document-list'),
    path('documents/<int:pk>/',views.AdminDocumentVerifyView.as_view(), name='admin-document-verify'),

    # service verification
    path('services/<int:pk>/verify/',views.AdminServiceVerifyView.as_view(),  name='admin-service-verify'),

    # customer management
    path('customers/',views.AdminCustomerListView.as_view(),   name='admin-customer-list'),

    # user account actions
    path('users/<int:user_id>/action/',views.AdminUserActionView.as_view(),     name='admin-user-action'),
]