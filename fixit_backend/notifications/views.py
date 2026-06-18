from django.shortcuts import render
from  rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import Notification
from .serializers import NotificationSerializer
# Create your views here.

class NotificationListView(APIView):
    permission_classes=[IsAuthenticated]

    def get(self,request):
        notifications=Notification.objects.filter(user=request.user)
        unread_only=request.query_params.get('unread')
        if unread_only=='true':
            notifications=notifications.filter(is_read=False)
        return Response({
            'count':notifications.count(),
            'unread_count': Notification.objects.filter(user=request.user, is_read=False).count(),
            'results':NotificationSerializer(notifications, many=True).data,
            })
    

class NotificationMarkReadView(APIView):
    permission_classes=[IsAuthenticated]

    def patch(self,request,pk):
        try:
            notification=Notification.objects.get(pk=pk,user=request.user)
        except Notification.DoesNotExist:
            return Response(
                 {'error': 'Notification not found.'},status=status.HTTP_404_NOT_FOUND
            )
        notification.is_read=True
        notification.save(update_fields=['is_read'])

        return Response({
            'message':'Notification marked as read.'
        })


class NotificationMarkAllReadView(APIView):
    """
    POST /api/notifications/read-all/  — mark all as read
    """
    permission_classes=[IsAuthenticated]
    def post(self,request):
        updated=Notification.objects.filter(
            user=request.user,is_read=False
        ).update(is_read=True)
        return Response({'message': f'{updated} notifications marked as read.'})

class NotificationUnreadCountView(APIView):
    """
    GET /api/notifications/unread-count/
    Lightweight endpoint for navbar bell icon badge.
    """
    permission_classes=[IsAuthenticated]

    def get(self,request):
        count=Notification.objects.filter(
            user=request.user,is_read=False
        ).count()
        return Response({'unread_count':count})

    
