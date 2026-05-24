# Generated manually for pgvector migration

from django.db import migrations, models
import pgvector.django

VECTOR_DIMENSIONS = 128


def copy_json_embeddings_to_vector(apps, schema_editor):
    JobEmbedding = apps.get_model("search", "JobEmbedding")
    for row in JobEmbedding.objects.all().iterator():
        legacy = row.embedding
        if legacy is None:
            row.embedding_vector = None
        elif isinstance(legacy, list) and len(legacy) == VECTOR_DIMENSIONS:
            row.embedding_vector = legacy
        else:
            row.embedding_vector = None
        row.save(update_fields=["embedding_vector"])


def clear_vector_embeddings(apps, schema_editor):
    JobEmbedding = apps.get_model("search", "JobEmbedding")
    JobEmbedding.objects.update(embedding_vector=None)


def delete_null_vector_embeddings(apps, schema_editor):
    JobEmbedding = apps.get_model("search", "JobEmbedding")
    JobEmbedding.objects.filter(embedding__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("search", "0001_initial"),
    ]

    operations = [
        pgvector.django.VectorExtension(),
        migrations.AddField(
            model_name="jobembedding",
            name="embedding_vector",
            field=pgvector.django.VectorField(dimensions=VECTOR_DIMENSIONS, null=True),
        ),
        migrations.RunPython(copy_json_embeddings_to_vector, clear_vector_embeddings),
        migrations.RemoveField(
            model_name="jobembedding",
            name="embedding",
        ),
        migrations.RenameField(
            model_name="jobembedding",
            old_name="embedding_vector",
            new_name="embedding",
        ),
        migrations.RunPython(delete_null_vector_embeddings, migrations.RunPython.noop),
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
