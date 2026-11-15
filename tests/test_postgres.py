from datetime import datetime, timezone
import os
from uuid import uuid4
import numpy as np
import pytest
from app.corpus import Passage
from app.retrieval import Retriever

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1", reason="Requires PostgreSQL with pgvector"
)


class FixedEmbeddings:
    async def embed(self, texts):
        vector = np.zeros(768, dtype=np.float32)
        vector[0] = 1
        return np.stack([vector for _ in texts])


@pytest.mark.asyncio
async def test_real_postgres_hybrid_search_isolates_law_and_prioritizes_terms():
    retriever = Retriever()
    retriever.embeddings = FixedEmbeddings()
    await retriever.open()
    law = "test-" + uuid4().hex

    def passage(article, text):
        return Passage(
            law + ":" + article,
            law,
            "Prueba",
            article,
            article,
            "20260101",
            datetime.now(timezone.utc).isoformat(),
            text,
            "https://www.boe.es/",
            "test",
        )

    try:
        await retriever.replace_law(
            [
                passage(
                    "vacaciones",
                    "Las vacaciones anuales comprenden treinta días naturales y son retribuidas.",
                ),
                passage(
                    "jornada",
                    "La jornada ordinaria tiene una duración máxima de cuarenta horas semanales.",
                ),
            ]
        )
        hits = await retriever.search("vacaciones anuales retribuidas", True, law)
        assert hits[0]["article"] == "vacaciones"
        assert all(h["law"] == law for h in hits)
        await retriever.replace_law(
            [
                passage(
                    "nueva",
                    "Este nuevo artículo sustituye todos los pasajes anteriores de esta norma de prueba.",
                )
            ]
        )
        hits = await retriever.search("nuevo artículo", True, law)
        assert {h["article"] for h in hits} == {"nueva"}
    finally:
        async with retriever.pool.connection() as connection:
            await connection.execute("DELETE FROM passages WHERE law=%s", (law,))
        await retriever.pool.close()
