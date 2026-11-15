import json
import httpx
import numpy as np
from .config import settings
from .observability import observation


class LanguageModel:
    async def json(
        self, system: str, user: str, schema: dict | None = None
    ) -> tuple[dict, dict]:
        with observation(
            "structured-generation",
            "generation",
            model=settings.model
            if settings.llm_provider == "ollama"
            else settings.api_model,
            metadata={"input_chars": len(user)},
        ) as span:
            data, usage = await self._json(system, user, schema)
            if span:
                span.update(
                    usage_details={
                        "input": usage.get(
                            "input_tokens", usage.get("prompt_tokens", 0)
                        ),
                        "output": usage.get(
                            "output_tokens", usage.get("completion_tokens", 0)
                        ),
                    },
                    cost_details={"total": 0}
                    if settings.llm_provider == "ollama"
                    else None,
                )
            return data, usage

    async def _json(
        self, system: str, user: str, schema: dict | None = None
    ) -> tuple[dict, dict]:
        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
            if settings.llm_provider == "api":
                if not settings.api_key or not settings.api_model:
                    raise RuntimeError("Falta configurar el proveedor API")
                response = await client.post(
                    settings.api_base.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + settings.api_key},
                    json={
                        "model": settings.api_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "structured_response",
                                "schema": schema,
                            },
                        }
                        if schema
                        else {"type": "json_object"},
                        "temperature": 0,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return json.loads(data["choices"][0]["message"]["content"]), data.get(
                    "usage", {}
                )
            response = await client.post(
                settings.ollama_url + "/api/chat",
                json={
                    "model": settings.model,
                    "stream": False,
                    "think": False,
                    "format": schema or "json",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 650},
                },
            )
            response.raise_for_status()
            data = response.json()
            return json.loads(data["message"]["content"]), {
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
                "cost": 0,
                "currency": "EUR",
                "billing": "local; no incluye electricidad",
            }


class Embeddings:
    async def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 768))
        output = []
        async with httpx.AsyncClient(timeout=120) as client:
            for start in range(0, len(texts), 24):
                response = await client.post(
                    settings.ollama_url + "/api/embed",
                    json={
                        "model": settings.embedding_model,
                        "input": [t[:6000] for t in texts[start : start + 24]],
                    },
                )
                response.raise_for_status()
                output.extend(response.json()["embeddings"])
        matrix = np.array(output, dtype=np.float32)
        if matrix.shape[1] != 768:
            raise ValueError("El corpus requiere embeddings de 768 dimensiones")
        return matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)
