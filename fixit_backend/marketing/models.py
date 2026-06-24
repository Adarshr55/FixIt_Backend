from django.db   import models
from django.utils import timezone


class PromoBanner(models.Model):
    """
    Active promotional banners shown on landing page.
    Admin creates and manages these — no frontend hardcoding.
    """
    title            = models.CharField(max_length=150)
    subtitle         = models.TextField(blank=True)
    coupon_code      = models.CharField(max_length=20, unique=True, blank=True)
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    discount_amount  = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    cta_text         = models.CharField(max_length=50, default='Book Now')
    cta_link         = models.CharField(max_length=200, blank=True)
    background_color = models.CharField(max_length=20, default='#FF6B35')
    image            = models.ImageField(upload_to='banners/', blank=True, null=True)
    is_active        = models.BooleanField(default=True, db_index=True)
    start_date       = models.DateTimeField(null=True, blank=True)
    end_date         = models.DateTimeField(null=True, blank=True)
    display_order    = models.PositiveIntegerField(default=0)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'promo_banners'
        ordering = ['display_order', '-created_at']

    def __str__(self):
        return f'{self.title} [{self.coupon_code}]'

    @property
    def is_currently_active(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True


class CMSSection(models.Model):
    """
    Backend-driven text content for landing page sections.
    Admin edits text here — frontend reads from API.
    No more hardcoded marketing copy in JSX files.
    """
    SECTION_KEYS = [
        ('hero',              'Hero Section'),
        ('how_it_works',      'How It Works'),
        ('become_provider',   'Become a Provider'),
        ('why_fixit',         'Why FixIt'),
        ('app_download',      'App Download'),
    ]

    section_key  = models.CharField(
        max_length=50, unique=True,
        db_index=True, choices=SECTION_KEYS
    )
    title        = models.CharField(max_length=200)
    subtitle     = models.TextField(blank=True)
    body         = models.TextField(blank=True)
    cta_text     = models.CharField(max_length=50, blank=True)
    cta_link     = models.CharField(max_length=200, blank=True)
    image        = models.ImageField(upload_to='cms/', blank=True, null=True)
    image_url    = models.URLField(max_length=500, blank=True)
    is_active    = models.BooleanField(default=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cms_sections'

    def __str__(self):
        return f'CMS — {self.get_section_key_display()}'


class HowItWorksStep(models.Model):
    """
    Individual steps shown in the How It Works section.
    Ordered and admin-managed.
    """
    title       = models.CharField(max_length=100)
    description = models.TextField()
    icon        = models.CharField(max_length=50, blank=True)
    step_number = models.PositiveIntegerField()
    is_active   = models.BooleanField(default=True)

    class Meta:
        db_table = 'how_it_works_steps'
        ordering = ['step_number']

    def __str__(self):
        return f'Step {self.step_number} — {self.title}'