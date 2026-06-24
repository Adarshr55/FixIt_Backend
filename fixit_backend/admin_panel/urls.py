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

    # CMS & Category Management
    path('categories/', views.AdminCategoryListView.as_view(), name='admin-category-list'),
    path('categories/<int:pk>/', views.AdminCategoryDetailView.as_view(), name='admin-category-detail'),
    path('cms-sections/', views.AdminCMSSectionListView.as_view(), name='admin-cms-section-list'),
    path('cms-sections/<str:pk_or_key>/', views.AdminCMSSectionDetailView.as_view(), name='admin-cms-section-detail'),
    path('promo-banners/', views.AdminPromoBannerListView.as_view(), name='admin-promo-banner-list'),
    path('promo-banners/<int:pk>/', views.AdminPromoBannerDetailView.as_view(), name='admin-promo-banner-detail'),
    path('how-it-works-steps/', views.AdminHowItWorksStepListView.as_view(), name='admin-how-it-works-step-list'),
    path('how-it-works-steps/<int:pk>/', views.AdminHowItWorksStepDetailView.as_view(), name='admin-how-it-works-step-detail'),
]