from django.urls import path
from .import views 



urlpatterns=[
    path('customer/',views.CustomerProfileView.as_view(),name='customer-profile'),
    path('provider/',views.ProviderProfileView.as_view(),name='provider-profile'),
    path('provider/document/',views.ProviderDocumentView.as_view(),name='provider-document'),
    path('status/',views.ProfileStatusView.as_view(),name='profile-status')

]   