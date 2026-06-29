from django.db import migrations, models
from django.contrib.postgres.operations import CreateExtension
from pgvector.django import VectorField


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        CreateExtension('vector'),   # ← ensures pgvector exists before VectorField
        migrations.CreateModel(
            name='SemanticEmbedding',
            fields=[
                ('id',           models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content_type', models.CharField(choices=[('category', 'Service Category'), ('service', 'Provider Service'), ('issue', 'Booking Issue Description'), ('faq', 'FAQ Item')], db_index=True, max_length=20)),
                ('object_id',    models.PositiveIntegerField(db_index=True)),
                ('text',         models.TextField()),
                ('embedding',    VectorField(dimensions=384)),
                ('updated_at',   models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'semantic_embeddings'},
        ),
        migrations.AlterUniqueTogether(
            name='semanticembedding',
            unique_together={('content_type', 'object_id')},
        ),
    ]