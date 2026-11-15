from datetime import date, timedelta
import re


class RejectedQuestion(ValueError):
    pass


def protect(question: str):
    if re.search(
        r"\b(?:\d{8}|[XYZxyz]\d{7})[A-Za-z]\b|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b|(?<!\d)(?:\+34[\s.-]*)?[6789](?:[\s.-]*\d){8}(?!\d)",
        question,
    ):
        raise RejectedQuestion("Retira DNI, correos y teléfonos de la consulta.")
    if re.search(
        r"ignora.{0,30}(instrucciones|sistema)|ignore.{0,30}(instructions|system)|system\s*prompt|revela.{0,20}(clave|contraseña)|<\|(?:system|im_start)\|>",
        question,
        re.I,
    ):
        raise RejectedQuestion(
            "La consulta intenta cambiar las instrucciones del asistente."
        )
    return question.strip()


def deadline(
    start: str, days: int, business: bool = False, holidays: list[str] | None = None
):
    if not 0 <= days <= 3650:
        raise ValueError("El plazo debe estar entre 0 y 3650 días")
    current = date.fromisoformat(start)
    blocked = {date.fromisoformat(d) for d in holidays or []}
    remaining = days
    while remaining:
        current += timedelta(days=1)
        if not business or (current.weekday() < 5 and current not in blocked):
            remaining -= 1
    return {
        "date": current.isoformat(),
        "start_excluded": True,
        "business_days": business,
        "scope": "Cálculo de calendario; los festivos y las reglas aplicables deben indicarse expresamente.",
    }


def verify_claims(claims: list[dict], sources: list[dict]):
    known = {p["id"]: p for p in sources}
    verified, rejected = [], []
    for claim in claims[:8]:
        source = known.get(claim.get("source_id"))
        quote = claim.get("quote", "").strip()
        normalized = lambda x: re.sub(r"\s+", " ", x).strip()
        if (
            source
            and len(quote) >= 30
            and normalized(quote) in normalized(source["text"])
        ):
            verified.append(
                {
                    "text": quote,
                    "source_id": source["id"],
                    "law_name": source["law_name"],
                    "article": source["article"],
                    "url": source["url"],
                    "effective": source["effective"],
                    "fetched": source["fetched"],
                }
            )
        else:
            rejected.append(claim.get("source_id", "sin fuente"))
    return verified, rejected
