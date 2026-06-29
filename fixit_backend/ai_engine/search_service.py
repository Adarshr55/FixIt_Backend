"""
SemanticSearchService
One search engine used by all four touchpoints.
Returns results with confidence scores and hybrid ranking.
"""

import logging
from pgvector.django import CosineDistance

logger = logging.getLogger(__name__)

# Confidence thresholds
HIGH_CONFIDENCE   = 75
MEDIUM_CONFIDENCE = 45


def search_categories(
    query: str,
    limit: int = 3,
    min_confidence: int = MEDIUM_CONFIDENCE,
) -> list:
    """
    Find the most semantically similar service categories to a query.

    Confidence is NOT raw cosine similarity * 100. The top result's
    confidence reflects how dominant it is over the runner-up (a clear
    single winner is confident even at "low" raw similarity). Every
    other result's confidence is scaled down relative to the top result,
    so the output stays correctly ordered from most to least confident.
    """
    from .models import SemanticEmbedding
    from .embedding_service import embed_text
    from services.models import ServiceCategory

    if not query or not query.strip():
        return []

    try:
        query_vector = embed_text(query.strip())

        results = list(SemanticEmbedding.objects.filter(
            content_type='category'
        ).annotate(
            distance=CosineDistance('embedding', query_vector)
        ).order_by('distance'))

        if not results:
            return []

        scored = [
            (r, max(0.0, 1.0 - float(r.distance)))
            for r in results
        ]

        top_similarity = scored[0][1]
        second_similarity = scored[1][1] if len(scored) > 1 else 0.0

        MIN_ABSOLUTE_SIMILARITY = 0.12
        if top_similarity < MIN_ABSOLUTE_SIMILARITY:
            return []

        # dominance is computed ONCE, from the top result vs its runner-up —
        # this is the actual signal that distinguishes "one clear winner"
        # (water leak -> Plumber) from "ambiguous field" (gibberish)
        dominance = top_similarity / (second_similarity + 0.05)
        top_confidence = round(min(100, (dominance * 25) + (top_similarity * 60)))

        matched_ids = [r.object_id for r, _ in scored]
        categories  = {
            c.id: c for c in ServiceCategory.objects.filter(
                pk__in=matched_ids, is_active=True
            )
        }

        output = []
        for result, similarity in scored:
            category = categories.get(result.object_id)
            if not category:
                continue

            if similarity <= 0:
                confidence = 0
            else:
                # scale every result relative to the top result's confidence,
                # proportional to how close its raw similarity is to the top.
                # This guarantees output stays sorted: confidence only ever
                # decreases as similarity decreases.
                confidence = round(top_confidence * (similarity / top_similarity))

            if confidence < min_confidence:
                continue

            output.append({
                'category_id':          category.id,
                'category_name':        category.name,
                'category_icon':        category.icon,
                'category_group':       category.group,
                'short_description':    category.short_description,
                'confidence':           confidence,
                'similarity':           round(similarity, 4),
            })

            if len(output) >= limit:
                break

        return output

    except Exception as e:
        logger.error(f'search_categories failed: {e}')
        return []


def search_with_providers(
    query: str,
    lat: float,
    lng: float,
    limit_categories: int = 3,
    limit_providers: int  = 6,
) -> dict:
    """
    Full search with nearby providers.
    Used by customer dashboard (Touchpoint 2).

    Returns:
    {
      'top_category':    { id, name, confidence },
      'providers':       [ ...hybrid scored provider cards... ],
      'alternatives':    [ ...other category suggestions... ],
      'query':           'original query string',
    }
    """
    from bookings.models import Booking
    from services.models import ProviderService
    from customer.location_backends import HaversineLocationBackend
    from django.db.models import Q
    from .embedding_service import embed_text
    from .models import SemanticEmbedding
    from pgvector.django import CosineDistance

    if not query or not query.strip():
        return {'top_category': None, 'providers': [], 'alternatives': [], 'query': query}

    try:
        # Step 1 — find matching categories
        categories = search_categories(query, limit=limit_categories)

        if not categories:
            return {
                'top_category': None,
                'providers':    [],
                'alternatives': [],
                'query':        query,
            }

        top_category    = categories[0]
        alternatives    = categories[1:]
        category_id     = top_category['category_id']
        query_vector    = embed_text(query.strip())

        # Step 2 — get nearby providers for top category
        busy_provider_ids = Booking.objects.filter(
            Q(status__in=['on_the_way', 'arrived', 'in_progress']) |
            Q(booking_type='instant', status='accepted')
        ).values_list('provider_id', flat=True)

        services = ProviderService.objects.filter(
            category_id               = category_id,
            verification_status       = 'verified',
            is_active                 = True,
            provider__approval_status = 'approved',
            provider__is_online       = True,
        ).exclude(
            provider_id__in=busy_provider_ids
        ).select_related('provider', 'category')

        # Step 3 — haversine distance filter
        backend = HaversineLocationBackend()
        ranked  = backend.find_nearby(services, lat, lng)

        if not ranked:
            return {
                'top_category': top_category,
                'providers':    [],
                'alternatives': alternatives,
                'query':        query,
            }

        # Step 4 — get semantic similarity scores for each service
        service_ids = [item['service'].id for item in ranked]
        service_embeddings = {
            se.object_id: se
            for se in SemanticEmbedding.objects.filter(
                content_type='service',
                object_id__in=service_ids,
            ).annotate(
                distance=CosineDistance('embedding', query_vector)
            )
        }

        # Step 5 — calculate hybrid score for each provider
        scored = []
        for item in ranked:
            service  = item['service']
            provider = service.provider
            dist_km  = item['distance_km']

            # semantic similarity (0.0 - 1.0)
            se = service_embeddings.get(service.id)
            if se and hasattr(se, 'distance'):
                semantic = max(0.0, 1.0 - float(se.distance))
            else:
                semantic = top_category['similarity']

            # component signals
            rating          = float(provider.overall_rating or 0) / 5.0
            distance_score  = max(0.0, 1.0 - (dist_km / 20.0))
            completion      = float(service.completion_rate or 0)
            verified_bonus  = 1.0 if service.verification_status == 'verified' else 0.0
            online_bonus    = 1.0 if provider.is_online else 0.0

            # hybrid score
            hybrid = (
                semantic       * 0.40 +
                rating         * 0.25 +
                distance_score * 0.15 +
                completion     * 0.10 +
                verified_bonus * 0.05 +
                online_bonus   * 0.05
            )

            scored.append({
                'service':          service,
                'distance_km':      dist_km,
                'semantic':         round(semantic, 4),
                'hybrid_score':     round(hybrid, 4),
                'confidence':       round(semantic * 100),
            })

        # sort by hybrid score
        scored.sort(key=lambda x: x['hybrid_score'], reverse=True)
        scored = scored[:limit_providers]

        # Step 6 — serialize for response
        from customer.serializers import ProviderCardSerializer
        distance_map = {s['service'].id: s['distance_km'] for s in scored}
        service_list = [s['service'] for s in scored]

        return {
            'top_category': top_category,
            'providers':    service_list,
            'distance_map': distance_map,
            'alternatives': alternatives,
            'query':        query,
        }

    except Exception as e:
        logger.error(f'search_with_providers failed: {e}')
        return {
            'top_category': None,
            'providers':    [],
            'alternatives': [],
            'query':        query,
        }


def detect_category_mismatch(
    issue_description: str,
    selected_category_id: int,
) -> dict:
    """
    Used by booking creation hint (Touchpoint 3).
    Checks if the issue description matches the selected category.

    Returns:
    {
      'mismatch':           True/False,
      'detected_category':  'Plumber',
      'confidence':         89,
      'message':            'This sounds like a plumbing issue...',
    }
    """
    if not issue_description:
        return {'mismatch': False}

    try:
        results = search_categories(issue_description, limit=1, min_confidence=70)

        if not results:
            return {'mismatch': False}

        top = results[0]

        if top['category_id'] == selected_category_id:
            return {'mismatch': False}

        return {
            'mismatch':          True,
            'detected_category': top['category_name'],
            'detected_id':       top['category_id'],
            'confidence':        top['confidence'],
            'message': (
                f'Your description sounds like a '
                f'{top["category_name"]} issue '
                f'({top["confidence"]}% match). '
                f'Did you select the right service?'
            ),
        }

    except Exception as e:
        logger.error(f'detect_category_mismatch failed: {e}')
        return {'mismatch': False}


def find_duplicate_services(similarity_threshold: float = 0.90) -> list:
    """
    Admin tool (Touchpoint 4).
    Finds provider services with very similar descriptions.

    Returns groups of similar services for admin review.
    """
    from .models import SemanticEmbedding
    from services.models import ProviderService
    from pgvector.django import CosineDistance

    try:
        embeddings = list(
            SemanticEmbedding.objects.filter(
                content_type='service'
            ).values('object_id', 'embedding', 'text')
        )

        if len(embeddings) < 2:
            return []

        service_ids = [e['object_id'] for e in embeddings]
        services    = {
            s.id: s for s in ProviderService.objects.filter(
                pk__in=service_ids
            ).select_related('provider', 'category')
        }

        # compare each pair
        groups    = []
        processed = set()

        for i, emb_a in enumerate(embeddings):
            if emb_a['object_id'] in processed:
                continue

            similar_group = []

            for j, emb_b in enumerate(embeddings):
                if i == j:
                    continue
                if emb_b['object_id'] in processed:
                    continue

                # calculate cosine similarity
                import numpy as np
                vec_a = np.array(emb_a['embedding'])
                vec_b = np.array(emb_b['embedding'])

                # normalize
                norm_a = np.linalg.norm(vec_a)
                norm_b = np.linalg.norm(vec_b)

                if norm_a == 0 or norm_b == 0:
                    continue

                similarity = float(np.dot(vec_a, vec_b) / (norm_a * norm_b))

                if similarity >= similarity_threshold:
                    service = services.get(emb_b['object_id'])
                    if service:
                        similar_group.append({
                            'service_id':    service.id,
                            'provider_id':   service.provider.id,
                            'provider_name': service.provider.full_name,
                            'category':      service.category.name,
                            'skills':        service.skills,
                            'similarity':    round(similarity * 100),
                        })
                        processed.add(emb_b['object_id'])

            if similar_group:
                service_a = services.get(emb_a['object_id'])
                if service_a:
                    groups.append({
                        'base_service': {
                            'service_id':    service_a.id,
                            'provider_id':   service_a.provider.id,
                            'provider_name': service_a.provider.full_name,
                            'category':      service_a.category.name,
                            'skills':        service_a.skills,
                        },
                        'similar_services': similar_group,
                        'max_similarity':   max(s['similarity'] for s in similar_group),
                    })
                    processed.add(emb_a['object_id'])

        groups.sort(key=lambda x: x['max_similarity'], reverse=True)
        return groups

    except Exception as e:
        logger.error(f'find_duplicate_services failed: {e}')
        return []