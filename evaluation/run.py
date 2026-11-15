import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from app.agents import Copilot
from app.retrieval import Retriever
from app.guardrails import verify_claims


async def run():
    folder = Path(__file__).parent
    questions = json.loads((folder / "questions.json").read_text())
    retriever = Retriever()
    await retriever.open()
    copilot = Copilot(retriever)
    rows = []
    checkpoint = folder / "results.json"
    if checkpoint.exists():
        previous = json.loads(checkpoint.read_text())
        rows = previous.get("rows", [])
    done = {r["question_id"] for r in rows}
    try:
        for item in questions:
            if item["id"] in done:
                continue
            started = time.perf_counter()
            state = {"question": item["question"]}
            state.update(await copilot.plan(state))
            for rerank in [False, True]:
                variant = {**state, "rerank": rerank}
                variant.update(await copilot.retrieve(variant))
                variant.update(await copilot.write(variant))
                claims = variant["draft"].get("claims", [])
                valid, rejected = verify_claims(claims, variant["sources"])
                expected = lambda source: (
                    source.get("law", item["expected_law"]) == item["expected_law"]
                    and source.get("article") == item["expected_article"]
                )
                payload = {
                    "question_id": item["id"],
                    "configuration": "rerank" if rerank else "hybrid",
                    "retrieval_recall_at_6": int(
                        any(expected(p) for p in variant["sources"])
                    ),
                    "raw_claims": len(claims),
                    "valid_citations": len(valid),
                    "invalid_citations": len(rejected),
                    "answer_hits_reference": int(any(expected(p) for p in valid)),
                    "abstained": bool(variant["draft"].get("insufficient"))
                    or not claims,
                    "seconds": round(time.perf_counter() - started, 3),
                }
                rows.append(payload)
                if rerank:
                    rows.append(
                        {
                            **payload,
                            "configuration": "verified",
                            "raw_claims": len(valid),
                            "invalid_citations": 0,
                            "abstained": not valid
                            or bool(variant["draft"].get("insufficient")),
                        }
                    )
            output = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model": "qwen3:4b",
                "corpus": "BOE consolidated snapshot; see data manifests",
                "method": "50 authored questions with article references; deterministic exact-quote checks, not expert legal assessment or RAGAS semantic scoring",
                "rows": rows,
            }
            output["summary"] = summarize(rows)
            checkpoint.write_text(json.dumps(output, ensure_ascii=False, indent=2))
            print("Evaluated", item["id"], "/", len(questions), flush=True)
    finally:
        await retriever.pool.close()


def summarize(rows):
    output = []
    for name in ["hybrid", "rerank", "verified"]:
        group = [r for r in rows if r["configuration"] == name]
        if not group:
            continue
        claims = sum(r["raw_claims"] for r in group)
        output.append(
            {
                "configuration": name,
                "questions": len(group),
                "retrieval_recall_at_6": round(
                    sum(r["retrieval_recall_at_6"] for r in group) / len(group), 4
                ),
                "exact_citation_precision": round(
                    sum(r["valid_citations"] for r in group) / claims, 4
                )
                if claims
                else None,
                "reference_article_hit_rate": round(
                    sum(r["answer_hits_reference"] for r in group) / len(group), 4
                ),
                "abstention_rate": round(
                    sum(r["abstained"] for r in group) / len(group), 4
                ),
            }
        )
    return output


if __name__ == "__main__":
    asyncio.run(run())
