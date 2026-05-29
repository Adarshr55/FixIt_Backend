from django.db import models
from django.conf import settings
# Create your models here.

class CustomerProfile(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='customer_profile')
    full_name=models.CharField(max_length=100)
    # phone=models.CharField(max_length=15,blank=True)
    profile_photo=models.URLField(blank=True)
    saved_addresses=models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table='customer_profiles'

    def __str__(self):
        return f"customer:{self.user.email}"
    

class ProviderProfile(models.Model):
     APPROVAL_STATUS = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("suspended", "Suspended"),
     ]
     user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='provider_profile')
     full_name=models.CharField(max_length=100)
    #  phone=models.CharField(max_length=15)
     profile_photo=models.URLField(blank=True)
     bio = models.TextField(blank=True)
     experience_years=models.PositiveIntegerField(default=0)
     city= models.CharField(max_length=100)
     latitude=models.DecimalField(max_digits=10,decimal_places=6,blank=True,null=True)
     longitude=models.DecimalField(max_digits=10,decimal_places=6,blank=True,null=True)
     is_online=models.BooleanField(default=False)
     service_radius_km = models.PositiveIntegerField(default=10)
     approval_status=models.CharField(max_length=20,choices=APPROVAL_STATUS,default='pending',db_index=True)
     overall_rating=models.DecimalField(max_digits=10,decimal_places=2,default=0.00)
    #  total_jobs=models.PositiveIntegerField(default=0)
    #  completion_rate=models.FloatField(default=0.0)
    #  response_speed=models.FloatField(default=0.0)
     created_at=models.DateTimeField(auto_now_add=True)
     updated_at=models.DateTimeField(auto_now=True)

     class Meta:
         db_table='provider_profiles'
         ordering=['-created_at']

     def __str__(self):
         return f'provider:{self.user.email}({self.approval_status})'
     
     @property
     def is_approved(self):
         return self.approval_status=='approved'
     
class ProviderDocument(models.Model):
    DOC_TYPE_CHOICES = [

        # Universal — every provider must upload this
        ('id_proof',          'ID Proof (Aadhaar / PAN / Passport)'),

        # Home Services — one per service
        ('electrician_cert',  'Electrician ITI / Trade Certificate'),
        ('plumber_cert',      'Plumber ITI / Trade Certificate'),
        ('carpenter_cert',    'Carpenter Certificate'),
        ('painter_cert',      'Painter Certificate'),
        ('ac_cert',           'AC Technician Certificate'),
        ('appliance_cert',    'Appliance Repair Certificate'),
        ('cctv_cert',         'CCTV Installation Certificate'),
        ('pest_cert',         'Pest Control License'),

        # Automotive — per service
        ('driving_license',   'Driving License'),
        ('vehicle_rc',        'Vehicle RC Book'),
        ('mechanic_cert',     'Mechanic ITI Certificate'),
        ('towing_rc',         'Towing Vehicle RC'),

        # Optional trust boosters
        ('work_photos',       'Previous Work Photos'),
        ('police_clearance',  'Police Clearance Certificate'),
    ]

    DOC_STATUS = [
        ('pending',  'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    provider=models.ForeignKey(ProviderProfile,on_delete=models.CASCADE,related_name='documents')
    service=models.ForeignKey('services.ProviderService',on_delete=models.SET_NULL,null=True,blank=True,related_name='documents')
    doc_type=models.CharField(max_length=30,choices=DOC_TYPE_CHOICES)
    file=models.URLField()
    status=models.CharField(max_length=20,choices=DOC_STATUS,default='pending')
    reject_reason = models.TextField(blank=True)
    verified_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name='verified_documents')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    

    class Meta:
        db_table='provider_documents'
        ordering=['-uploaded_at']

    def __str__(self):
        return f"{self.provider.full_name}-{self.doc_type}-{self.status}"




    