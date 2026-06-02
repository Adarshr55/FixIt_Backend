from django.urls import path
from . import views

urlpatterns = [
    # customer
    path( '',views.CustomerBookingListCreateView.as_view(), name='customer-bookings'),
    path('provider/',views.ProviderBookingListView.as_view(),name='provider-bookings'),
    # shared detail
    path('<int:pk>/',views.BookingDetailView.as_view(),name='booking-detail'),
    path('<int:pk>/status/',views.BookingStatusUpdateView.as_view(),name='booking-status-update'),
    # admin
    path('admin/',views.AdminBookingListView.as_view(),name='admin-bookings'),
    path('admin/<int:pk>/',views.AdminBookingActionView.as_view(),name='admin-booking-action'),
]