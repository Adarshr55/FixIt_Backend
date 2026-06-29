from django.db import migrations
from pgvector.django import HnswIndex


class Migration(migrations.Migration):

    dependencies = [
        ('ai_engine', '0001_initial'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='semanticembedding',
            index=HnswIndex(
                name='semantic_embedding_hnsw_idx',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ),
    ]