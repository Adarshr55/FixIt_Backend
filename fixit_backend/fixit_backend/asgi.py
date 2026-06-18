"""
ASGI config for fixit_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
import django
from django.core.asgi import get_asgi_application


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fixit_backend.settings')
django.setup()

from channels.routing import ProtocolTypeRouter,URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from  realtime.middleware import JWTAuthMiddleware
from realtime.routing import websocket_urlpatterns
application = ProtocolTypeRouter({
    'http':get_asgi_application(),
    'websocket':JWTAuthMiddleware(
            URLRouter(websocket_urlpatterns)

    )

})
