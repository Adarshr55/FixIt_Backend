from django.db   import models
from django.conf import settings


class ProviderLocation(models.Model):
    """
    Live GPS position of a provider.
    Updated by provider while on an active booking.
    One row per provider — updated in place (not appended).
    History not needed here — BookingStatusHistory covers audit.

    Phase 5: Add PointField alongside lat/lon for PostGIS queries.
    """
    provider   = models.OneToOneField(
        'profiles.ProviderProfile',
        on_delete=models.CASCADE,
        related_name='live_location',
    )
    latitude   = models.DecimalField(max_digits=10, decimal_places=6)
    longitude  = models.DecimalField(max_digits=10, decimal_places=6)
    # which booking this location update is for
    # null = provider is online but not on a job
    booking    = models.ForeignKey(
        'bookings.Booking',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='provider_locations',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'provider_locations'

    def __str__(self):
        return f'{self.provider.full_name} @ ({self.latitude}, {self.longitude})'