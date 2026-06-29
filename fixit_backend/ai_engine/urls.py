from django.urls import path
from . import views

urlpatterns = [
    path('admin/fraud-check/<int:provider_id>/', views.AdminProviderFraudCheckView.as_view(),name='ai-fraud-check'),
    path('admin/fraud-risk/',views.AdminAllFraudRiskView.as_view(),name='ai-fraud-risk-all'),
    path('admin/score/<int:provider_id>/',views.AdminProviderScoreBreakdownView.as_view(), name='ai-score-breakdown'),
    path('admin/review-fraud-check/',views.AdminReviewFraudCheckView.as_view(),name='ai-review-fraud'),
    path('admin/duplicate-services/', views.AdminDuplicateServicesView.as_view(), name='ai-duplicate-services'),
    path('admin/customer-abuse/', views.AdminCustomerAbuseListView.as_view(), name='ai-customer-abuse'),
    path('search/',views.PublicSemanticSearchView.as_view(), name='public-semantic-search'),
]