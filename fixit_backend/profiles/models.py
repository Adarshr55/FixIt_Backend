from django.db import models
from django.conf import settings
# Create your models here.

class CustomerProfile(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='customer_profile')
    full_name=models.CharField(max_length=100)
    profile_photo = models.ImageField(upload_to='customer_profiles/',blank=True,null=True)
    saved_addresses=models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table='customer_profiles'

    def __str__(self):
        return f"customer:{self.user.email}"


class CustomerAddress(models.Model):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=50)  # Home, Work, Other, or custom labels
    address = models.TextField()
    latitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customer_addresses'
        ordering = ['-is_default', '-created_at']

    def save(self, *args, **kwargs):
        if self.is_default:
            # Set all other addresses for this customer to is_default=False
            CustomerAddress.objects.filter(customer=self.customer, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.customer.user.email} - {self.label}: {self.address[:30]}"
    

class ProviderProfile(models.Model):
     APPROVAL_STATUS = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("suspended", "Suspended"),
     ]
     user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='provider_profile')
     full_name=models.CharField(max_length=100)
     profile_photo = models.ImageField(upload_to='provider_profiles/',blank=True,null=True)
     bio = models.TextField(blank=True)
     experience_years=models.PositiveIntegerField(default=0)
     city= models.CharField(max_length=100)
     latitude=models.DecimalField(max_digits=10,decimal_places=6,blank=True,null=True)
     longitude=models.DecimalField(max_digits=10,decimal_places=6,blank=True,null=True)
     is_online=models.BooleanField(default=False,db_index=True)
     service_radius_km = models.PositiveIntegerField(default=10)
     approval_status=models.CharField(max_length=20,choices=APPROVAL_STATUS,default='pending',db_index=True)
     overall_rating=models.DecimalField(max_digits=4,decimal_places=2,default=0.00)
     hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, default=0)
     rejection_reason = models.TextField(blank=True)
     cached_response_speed = models.FloatField(default=0.5)
     cached_cancellation_rate = models.FloatField(default=0.0)
     cached_repeat_bonus = models.FloatField(default=0.0)
     cached_recency_score = models.FloatField(default=0.1)
     ranking_signals_updated_at = models.DateTimeField(blank=True, null=True)
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
    file = models.FileField(upload_to='provider_documents/')
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
    


class ProviderKYC(models.Model):


    DOC_STATUS = [
        ('pending',  'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    provider = models.OneToOneField(ProviderProfile,on_delete=models.CASCADE,related_name='kyc',)
    pan_number= models.CharField(max_length=10, blank=True)
    pan_document = models.FileField(upload_to='provider_kyc/pan/%Y/%m/', null=True, blank=True)
    pan_status = models.CharField(max_length=20, choices=DOC_STATUS, default='pending')
    pan_reject_reason = models.TextField(blank=True)
    aadhaar_last4= models.CharField(max_length=4, blank=True)
    aadhaar_document= models.FileField(upload_to='provider_kyc/aadhaar/%Y/%m/',null=True, blank=True)
    aadhaar_status = models.CharField(max_length=20, choices=DOC_STATUS, default='pending')
    aadhaar_reject_reason = models.TextField(blank=True)
    kyc_verified = models.BooleanField(default=False)
    verified_by= models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True, blank=True,related_name='kyc_verifications',)
    verified_at = models.DateTimeField(null=True, blank=True)
    submitted_at= models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'provider_kyc'

    def __str__(self):
        return f'KYC — {self.provider.full_name} [{self.kyc_verified}]'
    
    def check_and_set_verified(self):
        """Call after any status update — auto-sets kyc_verified."""
        if self.pan_status == 'approved' and self.aadhaar_status == 'approved':
            self.kyc_verified = True
        else:
            self.kyc_verified = False
        self.save(update_fields=['kyc_verified', 'updated_at'])


class ProviderBankAccount(models.Model):

    provider = models.OneToOneField(ProviderProfile,on_delete=models.CASCADE,related_name='bank_account',)

    account_holder_name = models.CharField(max_length=100, blank=True)
    account_number      = models.CharField(max_length=20, blank=True)
    ifsc_code           = models.CharField(max_length=11, blank=True)

    # Auto-filled from free Razorpay IFSC API
    bank_name           = models.CharField(max_length=100, blank=True)
    branch_name         = models.CharField(max_length=100, blank=True)

    passbook_document   = models.FileField(upload_to='provider_bank/%Y/%m/',null=True, blank=True)

    is_verified   = models.BooleanField(default=False)
    reject_reason = models.TextField(blank=True)

    verified_by  = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True, blank=True,related_name='bank_verifications',)
    verified_at  = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'provider_bank_accounts'

    def __str__(self):
        return f'Bank — {self.provider.full_name} [{self.ifsc_code}]'





    