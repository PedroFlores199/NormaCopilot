import json
import sys
import urllib.error
import urllib.request


def run(base):
    def post(path, value, status=200):
        request = urllib.request.Request(
            base + path,
            data=json.dumps(value).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=360)
        except urllib.error.HTTPError as error:
            response = error
        assert response.status == status, (path, response.status, response.read()[:200])
        return response

    with urllib.request.urlopen(base + "/health", timeout=10) as response:
        assert json.load(response)["passages"] > 0
    post(
        "/api/ask",
        {"question": "Mi DNI es 12345678Z, necesito información laboral"},
        422,
    ).close()
    with post(
        "/api/tools/deadline",
        {
            "start": "2026-11-13",
            "days": 2,
            "business": True,
            "holidays": ["2026-11-16"],
        },
    ) as response:
        assert json.load(response)["date"] == "2026-11-18"
    events = []
    with post(
        "/api/ask",
        {
            "question": "¿Cuántos días de vacaciones reconoce el Estatuto de los Trabajadores?"
        },
    ) as response:
        for line in response:
            if line.startswith(b"data: "):
                events.append(json.loads(line[6:]))
    errors = [event for event in events if event["type"] == "error"]
    assert not errors, errors
    answer = next(event for event in events if event["type"] == "answer")
    assert answer["status"] == "grounded" and answer["claims"]
    assert any(
        claim["article"] == "a38" and "treinta" in claim["text"].lower()
        for claim in answer["claims"]
    )
    known = {source["id"]: source for source in answer["sources"]}
    assert all(
        claim["text"] in known[claim["source_id"]]["text"] for claim in answer["claims"]
    )
    assert {"planificar", "buscar", "redactar", "verificar"} <= {
        event.get("step") for event in events
    }
    print(
        json.dumps(
            {
                "result": "passed",
                "provider": base,
                "literal_citations": len(answer["claims"]),
                "correct_article": True,
                "streamed_graph": True,
                "pii_rejection": True,
                "deadline": True,
                "latency_ms": answer["latency_ms"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5101")
