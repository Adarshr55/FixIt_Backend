from django.urls import path
from . import views

urlpatterns = [
    # provider sends GPS update
    path('update/',views.ProviderLocationUpdateView.as_view(),  name='location-update'),
    # customer polls provider position
    path('booking/<int:booking_id>/',views.CustomerTrackProviderView.as_view(),   name='location-track'),
    # provider checks own last location
    path('me/',views.ProviderCurrentLocationView.as_view(), name='location-me'),
]