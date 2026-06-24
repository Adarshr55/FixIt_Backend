from django.urls import path
from . import views

urlpatterns = [
    path('categories/',views.CustomerCategoryListView.as_view(),name='customer-categories'),
    path('providers/',views.CustomerProviderListView.as_view(),   name='customer-provider-list'),
    path('providers/recommended/', views.CustomerRecommendedProvidersView.as_view(), name='customer-recommended-providers'),
    path('providers/<int:service_id>/', views.CustomerProviderDetailView.as_view(), name='customer-provider-detail'),
]