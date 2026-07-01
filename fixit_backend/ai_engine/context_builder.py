"""
Context Builder — assembles database context for the LLM.
Pulls real data from FixIt's DB so the LLM answers factually.
"""

import json
import logging
from django.db.models import Avg, Min, Max

logger = logging.getLogger(__name__)


def build_category_context(category) -> dict:
    return {
        'name':category.name,
        'description': category.description or '',
        'skills':category.skill_tags or [],
        'group':category.group,
    }

def build_pricing_context(category_id: int) -> dict:

    from bookings.models import Booking

    recent_bookings = Booking.objects.filter(
        category_id  = category_id,
        status       = 'completed',
        final_amount__isnull = False,
    ).order_by('-completed_at')[:100]

    if not recent_bookings.exists():
        return {
            'available': False,
            'message':   'No pricing data yet for this category.',
        }
    
    stats = recent_bookings.aggregate(
        avg = Avg('final_amount'),
        min = Min('final_amount'),
        max = Max('final_amount'),
    )

    from services.models import ProviderService
    base_charges = list(
        ProviderService.objects.filter(
            category_id         = category_id,
            verification_status = 'verified',
            is_active           = True,
        ).values_list('base_charge', flat=True)[:20]
    )
    return {
        'available':          True,
        'avg_final_amount':   round(float(stats['avg'] or 0), 0),
        'min_final_amount':   round(float(stats['min'] or 0), 0),
        'max_final_amount':   round(float(stats['max'] or 0), 0),
        'typical_base_charge': round(
            sum(float(c) for c in base_charges) / len(base_charges), 0
        ) if base_charges else 0,
        'sample_size':        recent_bookings.count(),
        'currency':           'INR',
    }


def build_providers_context(providers_list: list, distance_map: dict) -> list:

     context = []
     for service in providers_list[:5]:
         provider = service.provider
         context.append({
            'rating':       float(provider.overall_rating or 0),
            'distance_km':  distance_map.get(service.id, 0),
            'base_charge':  float(service.base_charge or 0),
            'total_jobs':   service.total_jobs,
            'skills':       service.skills or [],
            'city':         provider.city,
            'is_online':    provider.is_online,
        })
     return context


def build_similar_issues_context(query: str, category_id: int) -> list:

     from ai_engine.models import SemanticEmbedding
     from ai_engine.embedding_service import embed_text
     from pgvector.django import CosineDistance
     from bookings.models import Booking

     try:
         query_vector = embed_text(query)

         similar = SemanticEmbedding.objects.filter(
            content_type='issue'
            ).annotate(
            distance=CosineDistance('embedding', query_vector)
            ).order_by('distance')[:5]
         
         issues = []
         for emb in similar:
            similarity = max(0.0, 1.0 - float(emb.distance))
            if similarity < 0.6:
                continue
            try:
                 booking = Booking.objects.select_related(
                    'category'
                ).get(pk=emb.object_id, status='completed')

                 issues.append({
                    'description': booking.issue_description[:100],
                    'category':    booking.category.name if booking.category else '',
                    'similarity':  round(similarity * 100),
                })
            except Booking.DoesNotExist:
                continue
         return issues
     except Exception as e:
        logger.error(f'build_similar_issues_context failed: {e}')
        return []
     

def assemble_full_context(query:str,category,providers:list,distance_map:dict,city:str = '',) -> str:
     
     context = {
        'category':         build_category_context(category),
        'pricing':          build_pricing_context(category.id),
        'providers_count':  len(providers),
        'providers':        build_providers_context(providers, distance_map),
        'similar_issues':   build_similar_issues_context(query, category.id),
        'customer_city':    city or 'India',
    }
     return json.dumps(context, indent=2, default=str)

