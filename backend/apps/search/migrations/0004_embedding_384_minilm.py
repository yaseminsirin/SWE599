# Migrate JobEmbedding vectors from 768 (Gemini) to 384 (all-MiniLM-L6-v2).

import pgvector.django
from django.db import migrations

VECTOR_DIMENSIONS = 384


def clear_all_embeddings(apps, schema_editor):
    JobEmbedding = apps.get_model("search", "JobEmbedding")
    JobEmbedding.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("search", "0003_embedding_768_gemini"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="jobembedding",
            name="search_jobemb_embed_hnsw_idx",
        ),
        migrations.RunPython(clear_all_embeddings, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="jobembedding",
            name="embedding",
            field=pgvector.django.VectorField(dimensions=VECTOR_DIMENSIONS),
        ),
        migrations.AddIndex(
            model_name="jobembedding",
            index=pgvector.django.HnswIndex(
                name="search_jobemb_embed_hnsw_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]
