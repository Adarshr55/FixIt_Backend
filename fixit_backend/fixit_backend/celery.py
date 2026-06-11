import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE','fixit_backend.settings')
app=Celery('fixit_backend')
app.config_from_object('django.conf:settings',namespace='CELERY')
app.autodiscover_tasks()