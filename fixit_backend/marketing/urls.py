from django.urls import path
from . import views

urlpatterns = [
    # Public
    path('banners/',views.PublicPromoBannerView.as_view(),name='public-banners'),
    path('sections/',views.PublicCMSSectionView.as_view(),name='public-sections'),
    path('how-it-works/',views.PublicHowItWorksView.as_view(),name='how-it-works'),

    # Admin
    path('admin/banners/',views.AdminPromoBannerView.as_view(),name='admin-banners'),
    path('admin/banners/<int:pk>/',views.AdminPromoBannerDetailView.as_view(), name='admin-banner-detail'),
    path('admin/sections/',views.AdminCMSSectionView.as_view(),name='admin-sections'),
    path('admin/sections/<str:key>/',views.AdminCMSSectionDetailView.as_view(), name='admin-section-detail'),
]