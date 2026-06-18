"""
WebSocket Consumers for FixIt.

A consumer is like a Django view but for WebSocket connections.
Each connected client gets its own consumer instance.

Flow:
  Browser opens WebSocket → connect() called
  Browser sends message  → receive() called
  Server sends message   → self.send() or group_send()
  Browser disconnects    → disconnect() called

Groups:
  We use Channel Groups to broadcast to multiple consumers.
  Example: when booking status changes, we send to group
  "user_5_notifications" which all consumers for user 5 are in.
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db                import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


# ── Notification Consumer ─────────────────────────────────────────

class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Personal notification stream for each user.

    Each user connects to: ws://localhost:8000/ws/notify/?token=xxx

    Group name: user_{user_id}_notifications
    When any part of the backend calls:
        channel_layer.group_send('user_5_notifications', {...})
    This consumer receives it and forwards to the browser.
    """

    async def connect(self):
        user = self.scope['user']

        # reject anonymous connections
        if isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4001)   # 4001 = unauthorized
            return

        # group name is unique per user
        self.group_name = f'user_{user.id}_notifications'

        # join the group
        # now when anyone sends to this group, this consumer receives it
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name   # unique name for this specific connection
        )

        await self.accept()

        logger.info(f'NotificationConsumer connected: user={user.id}')

        # send unread count immediately on connect
        # so the frontend bell badge shows the right number right away
        unread_count = await self.get_unread_count(user.id)
        await self.send(text_data=json.dumps({
            'type':         'connected',
            'unread_count': unread_count,
            'message':      'Connected to notification stream',
        }))



    async def disconnect(self, close_code):
        # leave the group so no messages are wasted on dead connections
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        logger.info(f'NotificationConsumer disconnected: code={close_code}')

    async def receive(self, text_data):
        """
        Handle messages FROM the browser.
        Currently supports:
          { "type": "mark_read", "notification_id": 5 }
          { "type": "ping" }
        """
        try:
            data = json.loads(text_data)
            msg_type = data.get('type')

            if msg_type == 'mark_read':
                notification_id = data.get('notification_id')
                if notification_id:
                    await self.mark_notification_read(
                        notification_id, self.scope['user'].id
                    )
                    await self.send(text_data=json.dumps({
                        'type':            'marked_read',
                        'notification_id': notification_id,
                    }))

            elif msg_type == 'ping':
                # keep-alive ping from frontend
                await self.send(text_data=json.dumps({'type': 'pong'}))

        except json.JSONDecodeError:
            pass

    # ── Handler for group messages ────────────────────────────────
    # Method name format: async def {type_with_dots_as_underscores}
    # When group_send sends type='notification.new', this method is called

    async def notification_new(self, event):
        """
        Called when a new notification is pushed to this user's group.
        Forwards the notification data to the browser.
        """
        await self.send(text_data=json.dumps({
            'type':              'new_notification',
            'id':                event['id'],
            'notification_type': event['notification_type'],
            'title':             event['title'],
            'message':           event['message'],
            'booking_id':        event.get('booking_id'),
            'created_at':        event['created_at'],
            'unread_count':      event['unread_count'],
        }))

    # ── Database helpers (sync→async wrappers) ────────────────────

    @database_sync_to_async
    def get_unread_count(self, user_id):
        from notifications.models import Notification
        return Notification.objects.filter(
            user_id=user_id, is_read=False
        ).count()

    @database_sync_to_async
    def mark_notification_read(self, notification_id, user_id):
        from notifications.models import Notification
        Notification.objects.filter(
            id=notification_id, user_id=user_id
        ).update(is_read=True)





#location section consumers

class LocationConsumer(AsyncWebsocketConsumer):
     

     """
    Live GPS tracking for a specific booking.

    Both provider and customer connect to:
    ws://localhost:8000/ws/location/{booking_id}/?token=xxx

    Group name: booking_{booking_id}_location

    Provider sends GPS → group_send → customer receives instantly.
    Customer also sends their location → provider receives it once.
    """
      
     async def connect(self):
        user       = self.scope['user']
        booking_id = self.scope['url_route']['kwargs']['booking_id']

        if isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close()
            return
        
        booking = await self.get_booking(booking_id, user)
        if not booking:
            await self.close()   # 4004 = not found / not authorized
            return
        

        self.booking_id = booking_id
        self.group_name = f'booking_{booking_id}_location'
        self.user       = user
        self.booking    = booking


        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

        logger.info(
            f'LocationConsumer connected: user={user.id} booking={booking_id}'
        )

        self.role = await self.get_user_role(user, booking)
        await self.send(text_data=json.dumps({
            'type':'connected',
            'role': self.role,
            'booking_id': int(booking_id),
            'message':    f'Connected to location stream for booking {booking_id}',
        }))

     async def disconnect(self, close_code):
            if hasattr(self, 'group_name'):
                await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
                
     async def receive(self, text_data):
        """
        Handle GPS data sent from provider or customer browser.

        Provider sends every 5 seconds:
        { "type": "location_update", "latitude": 9.93, "longitude": 76.26 }

        Customer sends once when booking starts:
        { "type": "customer_location", "latitude": 9.95, "longitude": 76.28 }
        """
        try:
            data     = json.loads(text_data)
            msg_type = data.get('type')

            if msg_type == 'location_update':
                if self.role !='provider':
                    return
                booking_status = await self.get_booking_status()
                if booking_status not in ['accepted', 'on_the_way', 'arrived', 'in_progress']:
                    return
                # provider is sending their live GPS
                lat = data.get('latitude')
                lng = data.get('longitude')

                if lat is None or lng is None:
                    return

                # save to DB for REST polling fallback
                await self.save_provider_location(lat, lng)

                # broadcast to everyone in this booking's group
                # customer will receive this instantly
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type':       'location.update',   # maps to location_update method
                        'latitude':   lat,
                        'longitude':  lng,
                        'sender':     'provider',
                        'booking_id': int(self.booking_id),
                    }
                )

            elif msg_type == 'customer_location':
                # customer is sharing their static pickup location
                lat = data.get('latitude')
                lng = data.get('longitude')

                if lat is None or lng is None:
                    return

                # broadcast to provider so they see the destination pin
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type':       'location.update',
                        'latitude':   lat,
                        'longitude':  lng,
                        'sender':     'customer',
                        'booking_id': int(self.booking_id),
                    }
                )

            elif msg_type == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))

        except json.JSONDecodeError:
            pass

    # ── Group message handler ─────────────────────────────────────

     async def location_update(self, event):
        """
        Called when anyone in the group sends a location update.
        Forwards the GPS data to this consumer's browser.
        """
        await self.send(text_data=json.dumps({
            'type':       'location_update',
            'latitude':   event['latitude'],
            'longitude':  event['longitude'],
            'sender':     event['sender'],
            'booking_id': event['booking_id'],
        }))
     @database_sync_to_async
     def get_booking(self, booking_id, user):
        """
        Verify booking exists and user is part of it.
        Returns booking or None.
        """
        from bookings.models import Booking
        try:
            booking = Booking.objects.select_related(
                'customer', 'provider__user'
            ).get(id=booking_id)

            # check user is customer or provider of this booking
            is_customer = booking.customer == user
            is_provider = (
                hasattr(user, 'provider_profile') and
                booking.provider == user.provider_profile
            )
            logger.info(f'get_booking: booking={booking_id} status={booking.status} is_customer={is_customer} is_provider={is_provider}')   
            if is_customer or is_provider:
                return booking
            return None
        except Booking.DoesNotExist:
            logger.info(f'get_booking: booking {booking_id} does not exist')
            return None
     
     @database_sync_to_async
     def get_user_role(self, user, booking):
        """Returns 'provider' or 'customer' for this booking."""
        if hasattr(user, 'provider_profile'):
            try:
                if booking.provider == user.provider_profile:
                    return 'provider'
            except Exception:
                pass
        return 'customer'

     @database_sync_to_async
     def save_provider_location(self, lat, lng): 
        from location.models import ProviderLocation
        from bookings.models import Booking
        try:
            booking = Booking.objects.select_related('provider').get(
            id=self.booking_id
             )
            ProviderLocation.objects.update_or_create(
            provider=self.booking.provider,
            defaults={
                'latitude':  lat,
                'longitude': lng,
                'booking':  booking,
            }
        )
        except Exception as e:
            logger.error(f'save_provider_location failed: {e}')

     @database_sync_to_async
     def get_booking_status(self):
        self.booking.refresh_from_db(fields=['status'])
        return self.booking.status
     
#Booking creation consumer 

class ProviderBookingConsumer(AsyncWebsocketConsumer):
     
     """
    Live booking stream for a provider's dashboard.

    Provider connects to: ws://localhost:8000/ws/provider-bookings/?token=xxx

    Group name: provider_{provider_id}_bookings

    Whenever a booking is created/cancelled/disputed for this provider,
    the backend pushes the full booking payload directly — no polling,
    no implicit refetch via notifications.
    """
     async def connect(self):
         user=self.scope['user']

         if isinstance(user,AnonymousUser) or not user.is_authenticated:
             await self.close(code=4001)
             return
         provider_profile = await self.get_provider_profile(user)
         if not provider_profile:
             await self.close(code=4003)
             return
         
         self.group_name = f'provider_{provider_profile.id}_bookings'
         await self.channel_layer.group_add(self.group_name, self.channel_name)
         await self.accept()

         logger.info(f'ProviderBookingConsumer connected: provider={provider_profile.id}')

         await self.send(text_data=json.dumps({
            'type': 'connected',
            'message': 'Connected to provider booking stream',
        }))
         
     async def disconnect(self,close_code):
         if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

     async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except json.JSONDecodeError:
            pass
     async def booking_event(self, event):
         """
        event = {
            'type': 'booking.event',
            'event_type': 'created' | 'cancelled' | 'disputed' | 'status_changed',
            'booking': {...serialized booking data...},
        }
        """
         await self.send(text_data=json.dumps({
            'type':       'booking_event',
            'event_type': event['event_type'],
            'booking':    event['booking'],
        }))
         
     @database_sync_to_async
     def get_provider_profile(self, user):
        if hasattr(user, 'provider_profile'):
            return user.provider_profile
        return None
     

         
         
        






