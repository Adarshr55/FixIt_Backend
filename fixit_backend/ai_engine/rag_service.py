"""
RAG helper functions used internally by the chat agent's tools
and by the provider insights endpoint.
"""

import logging
from .llm_client import generate_with_system

logger = logging.getLogger(__name__)


def get_provider_insights(provider_profile) -> str:
    from services.models  import ProviderService
    from bookings.models  import Booking
    from reviews.models   import Review
    from django.db.models import Avg

    try:
        services = ProviderService.objects.filter(
            provider=provider_profile
        ).select_related('category')

        total_jobs = sum(s.total_jobs for s in services)
        avg_rating = float(
            Review.objects.filter(
                provider=provider_profile
            ).aggregate(avg=Avg('rating'))['avg'] or 0
        )

        recent_cancels = Booking.objects.filter(
            provider     = provider_profile,
            status       = 'cancelled',
            cancelled_by = 'provider',
        ).count()

        service_names = [s.category.name for s in services]

        context = f"""Provider stats:
- Services offered: {', '.join(service_names)}
- Total completed jobs: {total_jobs}
- Average rating: {avg_rating:.1f}/5.0
- Provider cancellations: {recent_cancels}
- Online status: {provider_profile.is_online}
- Overall rating: {float(provider_profile.overall_rating):.1f}/5.0
- City: {provider_profile.city}"""

        system = """You are FixIt's provider success assistant.
Give specific, actionable advice to help this provider get more bookings and improve their ranking.
Base your advice on their actual stats provided.
Be encouraging but honest. Maximum 4 bullet points."""

        return generate_with_system(
            system     = system,
            user       = f"My provider stats:\n{context}\n\nHow can I improve my performance on FixIt?",
            max_tokens = 400,
        )

    except Exception as e:
        logger.error(f'get_provider_insights failed: {e}')
        return "Unable to generate insights at this time. Please try again later."