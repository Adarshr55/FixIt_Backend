from django.db import models
from  django.conf import settings
# Create your models here.

class ServiceCategory(models.Model):
    GROUP_CHOICES=[
        ('home', 'Home Services'),
         ('automotive', 'Automotive Services'),
    ]
    name=models.CharField(max_length=100,unique=True)
    group=models.CharField(max_length=20,choices=GROUP_CHOICES,db_index=True)
    icon=models.CharField(max_length=50,blank=True)
    description=models.TextField(blank=True)
    is_active=models.BooleanField(default=True)
    skill_tags=models.JSONField(default=list)
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table='service_categories'
        verbose_name='Service Category'
        verbose_name_plural='Service Categories'
        ordering=['group', 'name']

    def __str__(self):
        return f"{self.name}-({self.get_group_display()})"
    

class ProviderService(models.Model):
     VERIFICATION_STATUS = [
        ('unverified', 'Unverified'),
        ('pending',    'Pending Review'),
        ('verified',   'Verified'),
        ('rejected',   'Rejected'),
    ]
     provider=models.ForeignKey('profiles.ProviderProfile',on_delete=models.CASCADE,related_name='services')
     category=models.ForeignKey(ServiceCategory,on_delete=models.PROTECT,related_name='provider_services')
     skills=models.JSONField(default=list)
     base_charge=models.DecimalField(max_digits=10,decimal_places=2)
     hourly_rate=models.DecimalField(max_digits=8,decimal_places=2)
     extra_info  = models.JSONField(default=dict)
     verification_status=models.CharField(max_length=20,choices=VERIFICATION_STATUS,default='unverified')
     service_rating=models.DecimalField(max_digits=4,decimal_places=2,default=0.00)
     total_jobs=models.PositiveIntegerField(default=0)
     completion_rate= models.FloatField(default=0.0)   
     is_active=models.BooleanField(default=True)
     created_at=models.DateTimeField(auto_now_add=True)
     updated_at=models.DateTimeField(auto_now=True)


     class Meta:
         db_table='provider_services'
         unique_together=['provider','category']
         ordering=['-created_at']

     def __str__(self):
         return f'{self.provider.full_name}-{self.category.name}'
     @property
     def is_verified(self):
        return self.verification_status == 'verified'


class ProviderAvailability(models.Model):
     DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
     ]
     provider=models.ForeignKey('profiles.ProviderProfile',on_delete=models.CASCADE,related_name='availability')
     day=models.IntegerField(choices=DAY_CHOICES)
     start_time=models.TimeField()  
     end_time=models.TimeField()
     is_active=models.BooleanField(default=True)
     emergency_available = models.BooleanField(default=False)
     updated_at=models.DateTimeField(auto_now=True)
     class Meta:
         db_table='provider_availability'
         unique_together=['provider','day']
         ordering=['day']

     def __str__(self):
         day_name = dict(self.DAY_CHOICES).get(self.day, self.day)
         return f'{self.provider.full_name}-{day_name}'
     

     def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError('start_time must be before end_time.')