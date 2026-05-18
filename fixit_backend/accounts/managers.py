from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations=True

    def create_user(self,email,password=None,**extra_fields):
        if not email:
            raise ValueError('Email address is required')
        email=self.normalize_email(email).lower()
        extra_fields.setdefault('is_active',True)
        extra_fields.setdefault('is_staff',False)

        role=extra_fields.get('role','customer')
        if role not in {'customer','provider','admin'}:
            raise ValueError('Invalid role')
        
        user=self.model(email=email,**extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user
    def create_superuser(self,email,password=None,**extra_fields):
        extra_fields.setdefault('is_staff',True)
        extra_fields.setdefault('is_superuser',True)
        extra_fields.setdefault('is_active',True)
        extra_fields.setdefault('role','admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('superuser must have is_superuser=True')
        
        return self.create_user(email, password, **extra_fields)
    

    



