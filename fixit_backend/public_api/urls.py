from django.urls import path
from . import views
urlpatterns = [
    # Geocoding
    path('geocode/',         views.PublicGeocodeView.as_view(),        name='public-geocode'),
    path('reverse-geocode/', views.PublicReverseGeocodeView.as_view(), name='public-reverse-geocode'),
    path('location-suggest/',views.PublicLocationSuggestView.as_view(),name='public-location-suggest'),

    # Discovery
    path('providers/',       views.PublicProviderSearchView.as_view(), name='public-providers'),
    path('providers/<int:service_id>/', views.PublicProviderDetailView.as_view(), name='public-provider-detail'),
    path('categories/',      views.PublicCategoryListView.as_view(),   name='public-categories'),

    # Trust signals
    path('stats/',           views.PublicStatsView.as_view(),          name='public-stats'),
    path('reviews/',         views.PublicReviewListView.as_view(),     name='public-reviews'),
]