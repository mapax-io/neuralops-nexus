"""
pgvector vector store implementation.

Alternative to ChromaStore (chroma_store.py, kept installed and still the
default -- see VectorStoreFactory) for setups that would rather not run a
separate ChromaDB service at all, e.g. the FAT single-container image,
which already bundles Postgres. Selected via VECTOR_STORE=pgvector.

Uses asyncpg directly (nexus-ai is fully async/FastAPI, unlike nucleus's
sync Django ORM) with the pgvector extension for similarity search, over
the SAME Postgres instance nucleus's own data lives in -- one database,
not a second one to run/back up.

Table shape: one shared table across every collection_id, not one
physical collection per collection_id the way Chroma's client-side model
works -- collection_id is just another indexed column here. Simpler to
manage in a single relational database, and lets filter-by-metadata and
similarity-search happen in the same SQL query instead of two separate
API calls.
"""
from __future__ import annotations

import json

import asyncpg
from pgvector.asyncpg import register_vector

from apps.core.config import settings
from apps.interfaces.vectorstore import Chunk, VectorStore


class PgVectorStore(VectorStore):
    # Shared across instances -- VectorStoreFactory.get() may be called
    # more than once per process; one pool per process is what we want,
    # not one per call.
    _pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if PgVectorStore._pool is None:
            PgVectorStore._pool = await asyncpg.create_pool(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                database=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                init=register_vector,  # teaches asyncpg the VECTOR wire codec
            )
            await self._ensure_schema(PgVectorStore._pool)
        return PgVectorStore._pool

    async def _ensure_schema(self, pool: asyncpg.Pool) -> None:
        """
        Idempotent -- IF NOT EXISTS everywhere, safe to run on every
        process start. EMBEDDING_DIM is baked into the column type at
        creation time; changing EMBEDDING_MODEL to a different output
        size later requires a migration, not just a config change.
        """
        async with pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS vector_documents (
                    id TEXT NOT NULL,
                    collection_id TEXT NOT NULL,
                    document TEXT NOT NULL,
                    embedding VECTOR({settings.EMBEDDING_DIM}) NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (collection_id, id)
                );
            """)
            # cosine ops: fastembed's nomic-embed-text output is
            # normalized, so cosine and L2 ranking are equivalent for
            # these vectors -- cosine is just the more conventional
            # choice for embedding similarity.
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS vector_documents_embedding_idx
                    ON vector_documents USING hnsw (embedding vector_cosine_ops);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS vector_documents_metadata_idx
                    ON vector_documents USING gin (metadata);
            """)

    async def store(
        self,
        texts: list[str],
        vectors: list[list[float]],
        metadatas: list[dict],
        collection_id: str,
        ids: list[str] | None = None,
    ) -> None:
        """Upsert -- ON CONFLICT keeps re-embedding the same doc ID idempotent,
        same guarantee ChromaStore.store() documents for its own upsert()."""
        doc_ids = ids if ids else [f"{collection_id}_{i}" for i in range(len(texts))]
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO vector_documents (id, collection_id, document, embedding, metadata)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (collection_id, id) DO UPDATE SET
                    document = EXCLUDED.document,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata
                """,
                [
                    (doc_ids[i], collection_id, texts[i], vectors[i], json.dumps(metadatas[i]))
                    for i in range(len(texts))
                ],
            )

    async def search(
        self,
        query_vector: list[float],
        collection_id: str,
        top_k: int = 5,
        filter: dict | None = None,
    ) -> list[Chunk]:
        """
        filter is a flat {key: value} dict, same shape ChromaStore accepts
        as its `where` kwarg -- translated here into JSONB containment
        checks (metadata @> '{"key": "value"}') rather than Chroma's own
        filter syntax.
        """
        pool = await self._get_pool()

        where_clauses = ["collection_id = $1"]
        params: list = [collection_id]
        if filter:
            for key, value in filter.items():
                params.append(json.dumps({key: value}))
                where_clauses.append(f"metadata @> ${len(params)}::jsonb")
        where_sql = " AND ".join(where_clauses)

        params.append(query_vector)
        vector_param = len(params)
        params.append(top_k)
        limit_param = len(params)

        query = f"""
            SELECT document, metadata, embedding <=> ${vector_param} AS distance
            FROM vector_documents
            WHERE {where_sql}
            ORDER BY embedding <=> ${vector_param}
            LIMIT ${limit_param}
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [
            Chunk(
                text=row["document"],
                # cosine distance -> similarity score, same 1-distance
                # convention ChromaStore.search() uses.
                score=1 - row["distance"],
                metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else dict(row["metadata"]),
            )
            for row in rows
        ]

    async def delete_collection(self, collection_id: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM vector_documents WHERE collection_id = $1", collection_id)

    async def delete_by_ids(self, collection_id: str, ids: list[str]) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM vector_documents WHERE collection_id = $1 AND id = ANY($2::text[])",
                collection_id, ids,
            )
