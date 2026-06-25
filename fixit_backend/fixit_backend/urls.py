"""
URL configuration for fixit_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/',include('accounts.urls')),
    path("api/services/", include("services.urls")),
    path('api/profiles/',include('profiles.urls')),
    path('api/bookings/',include('bookings.urls')),
    path('api/admin_panel/',include('admin_panel.urls')),
    path('api/customer/',include('customer.urls')),
    path('api/location/', include('location.urls')),
    path('api/notifications/',include('notifications.urls')),
    path('api/reviews/',include('reviews.urls')),
    path('api/payments/',include('payments.urls')),
    path('api/public/',include('public_api.urls')),
    path('api/marketing/',include('marketing.urls')),
    path('api/ai_engine/', include('ai_engine.urls'))
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
