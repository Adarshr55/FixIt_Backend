from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .import views

urlpatterns=[
    path('customer/register/',views.CustomerRegisterView.as_view()),
    path('provider/register/',views.ProviderRegisterView.as_view()),
    path('login/',views.LoginView.as_view()),
    path('logout/',views.LogoutView.as_view()),
    path('me/',views.MeView.as_view()),
    path('change-password/',views.ChangePasswordView.as_view()),
    path('admin/create/',views.AdminCreateView.as_view()),
    path('token/refresh/',views.CustomTokenRefreshView.as_view())
]