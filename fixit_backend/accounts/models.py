from django.db import models
from django.contrib.auth.models import AbstractBaseUser,PermissionsMixin
from .managers import UserManager
# Create your models here.

class User(AbstractBaseUser,PermissionsMixin):

    ROLE_CHOICES=[
        ('customer','Customer'),
        ('provider','Provider'),
        ('admin','Admin')
    ]

    email=models.EmailField(unique=True,db_index=True)
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)
    role=models.CharField(max_length=20,choices=ROLE_CHOICES,db_index=True)
    is_active=models.BooleanField(default=True)
    is_staff=models.BooleanField(default=False)
    # is_phone_verified = models.BooleanField(default=False)
    is_profile_complete = models.BooleanField(default=False)
    # is_email_verified=models.BooleanField(default=False)
    # is_google_auth=models.BooleanField(default=False)
    date_joined=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)



    objects=UserManager()

    USERNAME_FIELD='email'

    REQUIRED_FIELDS = ['role']

    class Meta:
        db_table='users'
        ordering  = ['-date_joined']
        verbose_name='User'
        verbose_name_plural='Users'

    def __str__(self):
        return  f"{self.email}-{self.role}"
    
    @property
    def is_customer(self):
        return self.role=='customer'
    @property
    def is_provider(self):
        return self.role=='provider'
    @property
    def is_admin_user(self):
        return self.role=='admin'
    @property
    def full_role_display(self):
        return dict(self.ROLE_CHOICES).get(self.role,self.role)


