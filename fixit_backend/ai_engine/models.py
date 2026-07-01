from django.db import models
from pgvector.django import VectorField
from django.conf import settings
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


import uuid

class ChatSession(models.Model):
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    user        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='chat_sessions',
    )
    messages    = models.JSONField(default=list)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_sessions'
        ordering = ['-updated_at']

    def __str__(self):
        user_label = self.user.email if self.user else 'Anonymous'
        return f'ChatSession [{user_label}] — {len(self.messages)} messages'

    def add_turn(self, entries: list):
        """
        Append one or more structured entries in a single save.
        entries is a list of dicts — see chat_service.py for the
        shapes (text / function_call / function_response).
        """
        self.messages.extend(entries)
        self.save(update_fields=['messages', 'updated_at'])

    def get_recent_history(self, limit: int = 20):
        """Return last N entries for context — keeps prompt size reasonable."""
        return self.messages[-limit:] if self.messages else []