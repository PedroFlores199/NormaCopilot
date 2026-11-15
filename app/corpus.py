from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import httpx
from defusedxml import ElementTree

LAWS = {
    "BOE-A-2015-11430": "Estatuto de los Trabajadores",
    "BOE-A-1995-24292": "Prevención de Riesgos Laborales",
    "BOE-A-2015-11724": "Ley General de la Seguridad Social",
}


@dataclass(frozen=True)
class Passage:
    id: str
    law: str
    law_name: str
    article: str
    title: str
    effective: str
    fetched: str
    text: str
    url: str
    digest: str


def parse_law(raw: bytes, law: str, as_of: date, fetched: str) -> list[Passage]:
    tree = ElementTree.fromstring(raw)
    if tree.findtext("./status/code") != "200":
        raise ValueError("El BOE no devolvió un documento válido")
    output = []
    for block in tree.findall(".//bloque"):
        article = block.get("id", "")
        if not re.fullmatch(r"a\d+[a-z]*", article):
            continue
        candidates = []
        for version in block.findall("version"):
            when = version.get("fecha_vigencia") or version.get("fecha_publicacion")
            if when and when[:8] <= as_of.strftime("%Y%m%d"):
                candidates.append((when, version.get("fecha_publicacion", ""), version))
        if not candidates:
            continue
        effective, _, selected = max(candidates, key=lambda x: (x[0], x[1]))
        paragraphs = [
            re.sub(r"\s+", " ", " ".join(p.itertext())).strip()
            for p in selected.findall("p")
        ]
        paragraphs = [p for p in paragraphs if len(p) > 25]
        title = paragraphs[0] if paragraphs else block.get("titulo", article)
        for index, paragraph in enumerate(paragraphs):
            for offset in range(0, len(paragraph), 2400):
                text = paragraph[offset : offset + 2600]
                if len(text) < 30:
                    continue
                key = f"{law}:{article}:{index}:{offset}"
                output.append(
                    Passage(
                        key,
                        law,
                        LAWS.get(law, law),
                        article,
                        title,
                        effective,
                        fetched,
                        text,
                        f"https://www.boe.es/buscar/act.php?id={law}#{article}",
                        sha256(text.encode()).hexdigest(),
                    )
                )
    if not output:
        raise ValueError("La norma no contiene artículos vigentes reconocibles")
    return output


async def download_law(law: str, folder: Path) -> list[Passage]:
    if law not in LAWS:
        raise ValueError("Norma no autorizada para la ingesta")
    folder.mkdir(parents=True, exist_ok=True)
    url = f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{law}/texto"
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "application/xml",
                "User-Agent": "NormaCopilot/1.0 (portfolio educativo)",
            },
        )
        response.raise_for_status()
    raw = response.content
    if len(raw) > 12_000_000:
        raise ValueError("La respuesta supera el tamaño admitido")
    now = datetime.now(timezone.utc).isoformat()
    passages = parse_law(raw, law, date.today(), now)
    (folder / (law + ".xml")).write_bytes(raw)
    (folder / (law + ".manifest.json")).write_text(
        json.dumps(
            {
                "source": url,
                "fetched": now,
                "sha256": sha256(raw).hexdigest(),
                "passages": len(passages),
            },
            indent=2,
        )
    )
    return passages


def load_snapshot(folder: Path) -> list[Passage]:
    path = folder / "corpus.json"
    return [Passage(**v) for v in json.loads(path.read_text())] if path.exists() else []


def save_snapshot(folder: Path, passages: list[Passage]):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "corpus.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps([asdict(p) for p in passages], ensure_ascii=False))
    temporary.replace(path)
