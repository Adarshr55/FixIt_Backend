from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations=True

    def _create_user(self, email, password, role, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        if role not in {"customer", "provider", "admin"}:
            raise ValueError(f"Invalid role: {role}")

        email = self.normalize_email(email).lower()
        user = self.model(email=email, role=role, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, role="customer", **extra_fields):
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, role, **extra_fields)
    

    def create_platform_admin(self,email,password,**extra_fields):
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email,password,"admin",**extra_fields)

        
    def create_superuser(self,email,password,**extra_fields):
        extra_fields.setdefault('is_staff',True)
        extra_fields.setdefault('is_superuser',True)
        extra_fields.setdefault('is_active',True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('superuser must have is_superuser=True')
        
        return self.create_user(email, password,"admin", **extra_fields)
    

    



