from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from accounts.models import User

@database_sync_to_async
def get_user_from_token(token_key):
    """
    Decode JWT token and return the User.
    database_sync_to_async because Django ORM is synchronous
    but Channels consumers are async.
    """
    try:
        token=AccessToken(token_key)
        print('token ok')
        user_id=int(token['user_id'])
        print("USER_ID =", user_id, type(user_id))

        user= User.objects.get(id=user_id)
    
        print("USER_ID =", user_id, type(user_id))
        return user

    except Exception as e:
        print("AUTH ERROR =", str(e))
        return AnonymousUser()
    

class JWTAuthMiddleware:
    def __init__(self,inner):
        self.inner=inner
    
    async def __call__(self,scope,receive,send):
        print("JWT MIDDLEWARE RUNNING")
        query_string=scope.get('query_string',b'').decode()
        params=parse_qs(query_string)
        token_list=params.get('token',[])

        if token_list:
            scope['user'] = await get_user_from_token(token_list[0])
        else:
            scope['user']=AnonymousUser()

        return await self.inner(scope,receive,send)

    