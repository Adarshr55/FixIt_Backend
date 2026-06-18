from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
        
        booking_id = serializers.IntegerField(
        source='booking.id',
        read_only=True,
        default=None,
     )
        class Meta:
            model=Notification
            fields =[
            'id','notification_type','title','message','is_read','booking_id','created_at',
            ]
            read_only_fields=fields