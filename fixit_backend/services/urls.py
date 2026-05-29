from django.urls import path
from .import views
urlpatterns=[
    path('categories/',views.ServiceCategoryListView.as_view(),name='service-categories'),
    path('provider/services/',views.ProviderServiceView.as_view(),name='provider-services'),
    path('provider/services/<int:pk>/',views.ProviderServiceDetailView.as_view(),name='provider-service-detail'),
    path('provider/availability/',views.ProviderAvailabilityView.as_view(),name='provider-availability'),
    path('provider/availability/<int:pk>/',  views.ProviderAvailabilityDetailView.as_view(),name='provider-availability-detail'),
    path('provider/toggle-online/', views.ProviderOnlineToggleView.as_view(), name='provider-toggle-online'),
]
