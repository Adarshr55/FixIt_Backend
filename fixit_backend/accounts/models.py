from django.db import models
from django.contrib.auth.models import AbstractBaseUser,PermissionsMixin
from .managers import UserManager
import random
from django.utils import timezone
from datetime import timedelta
import uuid
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
    is_phone_verified = models.BooleanField(default=False)
    is_profile_complete = models.BooleanField(default=False)
    is_email_verified=models.BooleanField(default=False)
    is_google_auth=models.BooleanField(default=False)
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    date_joined=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)



    objects=UserManager()

    USERNAME_FIELD='email'

    REQUIRED_FIELDS = []

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



class EmailOTP(models.Model):
    email = models.EmailField(db_index=True)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'email_otps'

    def __str__(self):
        return f"{self.email} - {self.otp_code}"

    @staticmethod
    def generate_code():
        return str(random.randint(100000, 999999))

    @classmethod
    def create_for_email(cls, email):
        code = cls.generate_code()
        expires = timezone.now() + timedelta(minutes=10)
        return cls.objects.create(email=email.lower().strip(), otp_code=code, expires_at=expires)

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at


class PasswordResetToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = 'password_reset_tokens'

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

