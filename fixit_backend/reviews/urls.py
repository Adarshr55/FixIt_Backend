# reviews/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Customer actions
    path('',views.ReviewCreateView.as_view(),name='review-create'),
    path('can-review/<int:booking_id>/',views.CanReviewView.as_view(),name='can-review'),
    path('report/', views.ReportCreateView.as_view(), name='report-create'),
    # Public — anyone can see provider reviews
    path('provider/<int:service_id>/',views.ProviderReviewListView.as_view(),name='provider-reviews'),
    # Admin
    path('admin/reports/',views.AdminReportListView.as_view(),name='admin-reports'),
    path( 'admin/reports/<int:pk>/', views.AdminReportActionView.as_view(), name='admin-report-action'),
    path('admin/reviews/',views.AdminReviewListView.as_view(),name='admin-reviews'),
    path('admin/reviews/<int:pk>/flag/',views.AdminReviewFlagView.as_view(),name='admin-review-flag'),
]