from __future__ import annotations

from typing import ClassVar

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField


class RecallDocument(models.Model):
    KIND_CHOICES: ClassVar = [
        ("message", "Message"),
        ("snapshot", "Snapshot"),
        ("thesis", "Thesis"),
        ("journal", "Journal"),
        ("observation", "Observation"),
        ("postmortem", "PostMortem"),
    ]
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    object_id = models.IntegerField()
    text = models.TextField()
    embedding = VectorField(dimensions=384, null=True, blank=True)
    embedding_model = models.CharField(max_length=64, blank=True, default="")
    tickers = models.JSONField(default=list)
    source_created_at = models.DateTimeField(null=True, blank=True)
    content_hash = models.CharField(max_length=64)
    search = SearchVectorField(null=True)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["kind", "object_id"], name="uniq_recall_doc")
        ]
        indexes: ClassVar = [
            HnswIndex(
                name="recall_emb_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            GinIndex(fields=["search"], name="recall_search_gin"),
            models.Index(fields=["-source_created_at"]),
        ]

    def __str__(self) -> str:
        return f"RecallDocument({self.kind}:{self.object_id})"
