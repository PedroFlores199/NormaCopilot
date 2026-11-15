from dataclasses import asdict
import json
import re
import unicodedata
from pgvector.psycopg import register_vector_async as register_vector
from psycopg_pool import AsyncConnectionPool
from rapidfuzz.fuzz import token_set_ratio
from .config import settings
from .corpus import Passage
from .models import Embeddings


def tokens(text: str) -> set[str]:
    normalized = "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )
    stop = {
        "que",
        "los",
        "las",
        "del",
        "una",
        "por",
        "para",
        "con",
        "como",
        "puede",
        "cuanto",
        "cual",
        "tiene",
        "son",
        "hay",
        "trabajadores",
        "trabajador",
        "estatuto",
        "reconoce",
        "cuantos",
        "cuantas",
        "segun",
        "ley",
        "normativa",
    }
    return {
        t for t in re.findall(r"[a-z0-9]+", normalized) if len(t) > 2 and t not in stop
    }


class Retriever:
    def __init__(self):
        self.pool = AsyncConnectionPool(
            settings.database_url, open=False, min_size=1, max_size=4
        )
        self.embeddings = Embeddings()

    async def open(self):
        await self.pool.open()
        async with self.pool.connection() as connection:
            await connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await register_vector(connection)
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS passages (id text PRIMARY KEY, law text NOT NULL, article text NOT NULL, payload jsonb NOT NULL, content text NOT NULL, embedding vector(768), terms tsvector GENERATED ALWAYS AS (to_tsvector('spanish',content)) STORED)"
            )
            await connection.execute(
                "CREATE INDEX IF NOT EXISTS passages_terms ON passages USING gin(terms)"
            )
            await connection.execute(
                "CREATE INDEX IF NOT EXISTS passages_vectors ON passages USING hnsw(embedding vector_cosine_ops)"
            )
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS query_runs (id text PRIMARY KEY, at timestamptz DEFAULT now(), question_hash text, latency_ms double precision, payload jsonb)"
            )

    async def replace_law(self, passages: list[Passage]):
        print(f"Embedding {passages[0].law}: {len(passages)} passages", flush=True)
        vectors = await self.embeddings.embed(
            [p.title + " " + p.text for p in passages]
        )
        async with self.pool.connection() as connection:
            await register_vector(connection)
            async with connection.transaction():
                await connection.execute(
                    "DELETE FROM passages WHERE law=%s", (passages[0].law,)
                )
                async with connection.cursor() as cursor:
                    await cursor.executemany(
                        "INSERT INTO passages(id,law,article,payload,content,embedding) VALUES (%s,%s,%s,%s::jsonb,%s,%s)",
                        [
                            (
                                p.id,
                                p.law,
                                p.article,
                                json.dumps(asdict(p)),
                                p.title + " " + p.text,
                                v,
                            )
                            for p, v in zip(passages, vectors)
                        ],
                    )

    async def count(self):
        async with self.pool.connection() as c:
            row = await (await c.execute("SELECT count(*) FROM passages")).fetchone()
            return row[0]

    async def search(self, question: str, rerank: bool = True, law: str | None = None):
        vector = (await self.embeddings.embed([question]))[0]
        async with self.pool.connection() as connection:
            await register_vector(connection)
            keywords = " OR ".join(sorted(tokens(question))) or question
            condition = " WHERE law=%s" if law else ""
            params = (vector, law) if law else (vector,)
            semantic = await (
                await connection.execute(
                    "SELECT payload,1-(embedding <=> %s) AS score FROM passages"
                    + condition
                    + " ORDER BY embedding <=> %s LIMIT 30",
                    params + (vector,),
                )
            ).fetchall()
            clause = " AND law=%s" if law else ""
            lexical = await (
                await connection.execute(
                    "SELECT payload,ts_rank_cd(terms,websearch_to_tsquery('spanish',%s)) AS score FROM passages WHERE terms @@ websearch_to_tsquery('spanish',%s)"
                    + clause
                    + " ORDER BY score DESC LIMIT 30",
                    (keywords, keywords) + ((law,) if law else ()),
                )
            ).fetchall()
        scores, passages = {}, {}
        for result, weight in [(semantic, 1.0), (lexical, 1.3)]:
            for rank, (p, _) in enumerate(result):
                passages[p["id"]] = p
                scores[p["id"]] = scores.get(p["id"], 0) + weight / (60 + rank + 1)
        ranked = sorted(scores, key=scores.get, reverse=True)[:24]
        if rerank:
            query_tokens = tokens(question)
            ranked.sort(
                key=lambda key: (
                    0.45 * scores[key] * 30
                    + 0.35
                    * len(query_tokens & tokens(passages[key]["text"]))
                    / max(len(query_tokens), 1)
                    + 0.2 * token_set_ratio(question, passages[key]["title"]) / 100
                ),
                reverse=True,
            )
        return [dict(passages[key], score=round(scores[key], 6)) for key in ranked[:6]]

    async def log(self, identifier, question_hash, latency, payload):
        async with self.pool.connection() as c:
            await c.execute(
                "INSERT INTO query_runs(id,question_hash,latency_ms,payload) VALUES (%s,%s,%s,%s::jsonb)",
                (identifier, question_hash, latency, json.dumps(payload)),
            )
