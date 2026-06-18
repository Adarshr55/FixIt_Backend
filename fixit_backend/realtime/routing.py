from django.urls import re_path
from .import consumers

websocket_urlpatterns=[
    #notification route
  re_path(r'ws/notifications/$',consumers.NotificationConsumer.as_asgi()),
   #location route
  re_path(r'ws/location/(?P<booking_id>\d+)/$', consumers.LocationConsumer.as_asgi()),
  #Booking creation show 
  re_path(r'ws/provider-booking/$',consumers.ProviderBookingConsumer.as_asgi())
]