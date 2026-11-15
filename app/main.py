import asyncio
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .agents import Copilot
from .config import settings
from .corpus import LAWS, download_law, load_snapshot, save_snapshot
from .guardrails import RejectedQuestion, deadline, protect
from .retrieval import Retriever

retriever = Retriever()
semaphore = asyncio.Semaphore(settings.max_parallel)
logger = logging.getLogger("normacopilot")


async def update_corpus():
    output = []
    for law in LAWS:
        passages = await download_law(law, settings.data_dir / "raw")
        await retriever.replace_law(passages)
        output.extend(passages)
    save_snapshot(settings.data_dir, output)
    return len(output)


@asynccontextmanager
async def lifespan(app):
    await retriever.open()
    if await retriever.count() == 0:
        passages = load_snapshot(settings.data_dir)
        if passages:
            for law in LAWS:
                subset = [p for p in passages if p.law == law]
                if subset:
                    await retriever.replace_law(subset)
        else:
            await update_corpus()
    scheduler = AsyncIOScheduler(timezone="Europe/Madrid")
    if settings.weekly_updates:
        scheduler.add_job(
            update_corpus,
            "cron",
            day_of_week="sun",
            hour=4,
            minute=0,
            max_instances=1,
            misfire_grace_time=3600,
        )
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await retriever.pool.close()


app = FastAPI(title="NormaCopilot", version="1.0.0", lifespan=lifespan)
app.mount(
    "/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static"
)


class Question(BaseModel):
    question: str = Field(min_length=8, max_length=1500)
    rerank: bool = True


class Deadline(BaseModel):
    start: str
    days: int = Field(ge=0, le=3650)
    business: bool = False
    holidays: list[str] = Field(default_factory=list, max_length=100)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(Path(__file__).parent / "static/index.html")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "passages": await retriever.count(),
        "provider": settings.llm_provider,
        "model": settings.model
        if settings.llm_provider == "ollama"
        else settings.api_model,
    }


@app.get("/api/corpus")
async def corpus():
    passages = load_snapshot(settings.data_dir)
    return {
        "laws": [
            {
                "id": key,
                "name": name,
                "passages": sum(p.law == key for p in passages),
                "fetched": max(
                    (p.fetched for p in passages if p.law == key), default=None
                ),
            }
            for key, name in LAWS.items()
        ],
        "passages": await retriever.count(),
    }


@app.post("/api/ask")
async def ask(body: Question):
    try:
        protect(body.question)
    except RejectedQuestion as error:
        raise HTTPException(422, str(error)) from error

    async def generate():
        async with semaphore:
            try:
                copilot = Copilot(retriever)
                async for event in copilot.events(body.question, body.rerank):
                    yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            except (Exception, asyncio.CancelledError) as error:
                if isinstance(error, asyncio.CancelledError):
                    raise
                logger.exception("Question failed")
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "error",
                            "message": "No se ha podido consultar el modelo. Comprueba su disponibilidad y vuelve a intentarlo.",
                        }
                    )
                    + "\n\n"
                )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/tools/deadline")
async def calculate(body: Deadline):
    try:
        return deadline(body.start, body.days, body.business, body.holidays)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/tools/law/{identifier}")
async def law(identifier: str):
    if identifier not in LAWS:
        raise HTTPException(404, "Norma fuera del corpus")
    return {
        "id": identifier,
        "name": LAWS[identifier],
        "url": "https://www.boe.es/buscar/act.php?id=" + identifier,
    }
