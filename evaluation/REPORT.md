# Evaluación reproducible

50 preguntas redactadas con artículo de referencia del Estatuto de los Trabajadores. Modelo local `qwen3:4b`, recuperación híbrida PostgreSQL/pgvector y corpus del BOE.

| Configuración | Recuperación del artículo @6 | Citas literales válidas | Respuesta con artículo de referencia | Abstención |
| --- | ---: | ---: | ---: | ---: |
| Híbrida | 90.0 % | 97.4 % | 84.0 % | 0.0 % |
| Con re-ranking | 94.0 % | 98.8 % | 92.0 % | 0.0 % |
| Con re-ranking y verificador | 94.0 % | 100.0 % | 92.0 % | 2.0 % |

Las comprobaciones de citas exigen coincidencia literal con el pasaje y una fuente conocida. No equivalen a una evaluación semántica de fidelidad jurídica por expertos. La recuperación mide si aparece el artículo esperado entre seis pasajes; una respuesta alternativa puede citar otro artículo relevante y no puntuar. La configuración sin verificador se evalúa solo fuera de la interfaz; el servicio siempre verifica.

El verificador descarta evidencia que no puede contrastar. Una cita válida no demuestra que el artículo resuelva todas las circunstancias del caso. No se ha usado un LLM externo como juez ni se han presentado estas medidas como RAGAS.

Repetir: `PYTHONPATH=. python evaluation/run.py`. El fichero `results.json` permite reanudar; para una medición nueva, guarda el resultado anterior fuera de esa ruta.
