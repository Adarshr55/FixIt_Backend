"""
EmbeddingService
Handles all embedding creation and storage.
Single responsibility: text → vector → SemanticEmbedding table.
"""

import logging
import numpy as np

logger=logging.getLogger(__name__)
_model = None

def get_model():
    """
    Lazy-load the embedding model.
    Only loads when first called — not at Django startup.
    Subsequent calls return the cached instance instantly.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info('Loading embedding model all-MiniLM-L6-v2...')
        _model=SentenceTransformer('all-MiniLM-L6-v2')
        logger.info('Embedding model ready.')
    return _model

def embed_text(text: str) -> list:
     """
    Convert a text string to a 384-dimensional vector.
    Returns a Python list suitable for pgvector storage.
    """
     if not text or not text.strip():
         return [0.0]*384
     model=get_model()
     vector=model.encode(text.strip(),normalize_embeddings=True)
     return vector.tolist()

def build_category_text(category) -> str:
    """
    Build the text representation of a ServiceCategory for embedding.
    Combines all meaningful fields into one searchable string.
    """
    parts = [category.name]
    if category.description:
        parts.append(category.description)
    if category.short_description:
        parts.append(category.short_description)
    if category.skill_tags:
        if isinstance(category.skill_tags, list):
             parts.append(' '.join(category.skill_tags))
        else:
             parts.append(str(category.skill_tags))
    return ' | '.join(parts)


def build_service_text(service) -> str:
    """
    Build the text representation of a ProviderService for embedding.
    Focuses on what the provider actually does — category + skills.
    """
    parts = []
    if service.category:
        parts.append(service.category.name)
        if service.category.description:
            parts.append(service.category.description)
    if service.skills:
        if isinstance(service.skills, list):
             parts.append(' '.join(service.skills))
        else:
             parts.append(str(service.skills))
    return ' | '.join(parts)


def build_issue_text(booking) -> str:
    """
    Build text from a booking's issue description.
    Used to learn from real customer language over time.
    """
    parts = []
    if booking.issue_description:
        parts.append(booking.issue_description)
    if booking.category:
        parts.append(booking.category.name)
    return ' | '.join(parts)

def embed_category(category_id: int) -> bool:
    """
    Embed a ServiceCategory and save to SemanticEmbedding.
    Creates or updates — safe to call multiple times.
    Returns True on success, False on failure.
    """
    from services.models import ServiceCategory
    from .models import SemanticEmbedding
    try:
        category = ServiceCategory.objects.get(pk=category_id)
        text = build_category_text(category)
        vector = embed_text(text)
        SemanticEmbedding.objects.update_or_create(
            content_type='category',
            object_id = category_id,
            defaults = {
                'text':      text,
                'embedding': vector,
            }
        )
        logger.info(f'Embedded category: {category.name} (id={category_id})')
        return True
    except ServiceCategory.DoesNotExist:
        logger.warning(f'embed_category: category {category_id} not found')
        return False
    except Exception as e:
        logger.error(f'embed_category failed for id={category_id}: {e}')
        return False
    

def embed_service(service_id: int) -> bool:
    """
    Embed a ProviderService and save to SemanticEmbedding.
    Only embeds verified services — unverified ones are skipped.
    """
    from services.models import ProviderService
    from .models import SemanticEmbedding

    try:
        service = ProviderService.objects.select_related(
            'category', 'provider'
        ).get(pk=service_id)

        if service.verification_status != 'verified':
            logger.info(
                f'Skipping unverified service id={service_id}'
            )
            return False

        text   = build_service_text(service)
        vector = embed_text(text)

        SemanticEmbedding.objects.update_or_create(
            content_type = 'service',
            object_id    = service_id,
            defaults     = {
                'text':      text,
                'embedding': vector,
            }
        )
        logger.info(f'Embedded service id={service_id}')
        return True
    
    except ProviderService.DoesNotExist:
        logger.warning(f'embed_service: service {service_id} not found')
        return False
    except Exception as e:
        logger.error(f'embed_service failed for id={service_id}: {e}')
        return False
    

def embed_issue(booking_id: int) -> bool:
     
     """
    Embed a completed booking's issue description.
    Builds the dataset of real customer language over time.
    """
     
     from bookings.models import Booking
     from .models import SemanticEmbedding
     
     try:
        booking = Booking.objects.select_related('category').get(
            pk=booking_id
        )

        if booking.status != 'completed':
            return False

        if not booking.issue_description:
            return False

        text   = build_issue_text(booking)
        vector = embed_text(text)
        SemanticEmbedding.objects.update_or_create(
            content_type = 'issue',
            object_id    = booking_id,
            defaults     = {
                'text':      text,
                'embedding': vector,
            }
        )
        logger.info(f'Embedded issue for booking id={booking_id}')
        return True
     except Booking.DoesNotExist:
        logger.warning(f'embed_issue: booking {booking_id} not found')
        return False
     except Exception as e:
        logger.error(f'embed_issue failed for id={booking_id}: {e}')
        return False



    