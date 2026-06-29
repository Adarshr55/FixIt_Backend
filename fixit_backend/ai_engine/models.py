from django.db import models
from pgvector.django import VectorField
# Create your models here.

class SemanticEmbedding(models.Model):
     """
    Stores vector embeddings for any model in FixIt.
    Completely separate from business models — clean architecture.

    content_type  — what kind of object this embedding belongs to
    object_id     — primary key of that object
    text          — what was embedded, stored for debugging
    embedding     — 384-dimensional vector from all-MiniLM-L6-v2
    """
     CONTENT_TYPES = [
        ('category', 'Service Category'),
        ('service',  'Provider Service'),
        ('issue',    'Booking Issue Description'),
        ('faq',      'FAQ Item'),
    ]
     content_type = models.CharField(max_length=20,choices=CONTENT_TYPES,db_index=True,)
     object_id  = models.PositiveIntegerField(db_index=True)
     embedding=VectorField(dimensions=384,)
     text = models.TextField()  
     updated_at = models.DateTimeField(auto_now=True)

     class Meta:
          db_table = 'semantic_embeddings'
          unique_together = [('content_type', 'object_id')]
          indexes = [
            models.Index(fields=['content_type', 'object_id']),
            ]
     def __str__(self):
        return f'Embedding [{self.content_type}:{self.object_id}]'
