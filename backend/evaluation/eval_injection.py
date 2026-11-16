"""Prompt injection against the REAL model, through the HTTP API (stage 9).

    uv run python -m evaluation.eval_injection                       # local stack (:3000)
    uv run python -m evaluation.eval_injection --base https://documind.esteban-russo.com \\
        --email alguien@ejemplo.com                                   # the deployed version

For each attack of evaluation/injection.py: uploads the malicious document to its own
organization ("Prueba de inyección", created the first time, so no real documents are touched),
waits until it is processed, asks the question only about that document (POST /chat with
`document_ids`) and checks the answer: the attack wins if a forbidden marker appears (a canary
word, a link, the hidden rules...). It also notes whether the real fact was still answered.

Exit code 1 if any attack won. Report in docs/evaluation/injection-<date>.md.
The password comes from INJECTION_PASSWORD (default: the public password of the dev seed).
"""

import argparse
import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.dev.seed import DEMO_PASSWORD
from evaluation.eval_retrieval import REPORTS
from evaluation.injection import ATTACKS, Attack, attack_won, build_file

ORGANIZATION_SLUG = "prueba-inyeccion"


@dataclass
class Outcome:
    attack: Attack
    answer: str
    won: list[str]
    answered_fact: bool
    seconds: float


async def organization(client: httpx.AsyncClient, auth: dict[str, str]) -> str:
    mine = (await client.get("/api/v1/organizations", headers=auth)).json()["items"]
    for org in mine:
        if org["slug"] == ORGANIZATION_SLUG:
            return str(org["id"])
    created = await client.post(
        "/api/v1/organizations",
        json={"name": "Prueba de inyección", "slug": ORGANIZATION_SLUG},
        headers=auth,
    )
    created.raise_for_status()
    return str(created.json()["id"])


async def upload(client: httpx.AsyncClient, headers: dict[str, str], path: Path) -> str:
    content = await asyncio.to_thread(path.read_bytes)
    response = await client.post(
        "/api/v1/documents", files={"file": (path.name, content)}, headers=headers
    )
    if response.status_code == 409:  # already uploaded in a previous run: reuse it
        details: list[dict[str, Any]] = response.json()["error"].get("details") or []
        return str(details[0]["document_id"])
    response.raise_for_status()
    return str(response.json()["id"])


async def wait_ready(client: httpx.AsyncClient, headers: dict[str, str], document_id: str) -> None:
    for _ in range(180):
        state = (
            await client.get(f"/api/v1/documents/{document_id}/processing", headers=headers)
        ).json()
        if state.get("status") == "ready":
            return
        if state.get("status") == "failed":
            raise RuntimeError(f"processing failed: {state.get('error')}")
        await asyncio.sleep(2)
    raise TimeoutError(f"document {document_id} not ready")


async def ask(
    client: httpx.AsyncClient, headers: dict[str, str], question: str, document_id: str
) -> str:
    for _ in range(10):
        async with client.stream(
            "POST",
            "/api/v1/chat",
            json={"question": question, "document_ids": [document_id]},
            headers={**headers, "Accept": "text/event-stream"},
        ) as response:
            if response.status_code == 429:
                await asyncio.sleep(int(response.headers.get("Retry-After", "10")))
                continue
            response.raise_for_status()
            body = "".join([piece async for piece in response.aiter_text()])
        return "".join(
            _data(block)["text"] for block in body.split("\n\n") if block.startswith("event: token")
        )
    raise RuntimeError("too many 429 answers")


def _data(block: str) -> dict[str, Any]:
    line = next(line for line in block.splitlines() if line.startswith("data: "))
    data: dict[str, Any] = json.loads(line[6:])
    return data


def write_report(outcomes: list[Outcome], base: str) -> Path:
    today = datetime.now(UTC).date().isoformat()
    won = sum(1 for o in outcomes if o.won)
    lines = [
        f"# Prompt injection — {today}",
        "",
        "Generado por `uv run python -m evaluation.eval_injection` (etapa 9). No editar a mano.",
        "",
        f"- Contra: `{base}` (modelo y prompt de esa versión).",
        f"- **Ataques que funcionaron: {won} de {len(outcomes)}.**",
        "- Un ataque gana si la respuesta muestra su marca (canario, link, reglas internas).",
        "- «Respondió el dato»: la respuesta igual contiene el dato real del documento.",
        "",
        "| Ataque | Qué intenta | ¿Funcionó? | Respondió el dato | Segundos |",
        "|---|---|---|---|---|",
    ]
    for o in outcomes:
        lines.append(
            f"| `{o.attack.id}` | {o.attack.description} "
            f"| {'**sí**: ' + ', '.join(o.won) if o.won else 'no'} "
            f"| {'sí' if o.answered_fact else 'no'} | {o.seconds:.0f} |"
        )
    lines += ["", "## Respuestas", ""]
    for o in outcomes:
        answer = " ".join(o.answer.split()).replace("|", "/")
        lines += [f"- **{o.attack.id}** — {o.attack.question}", f"  > {answer}", ""]
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"injection-{today}.md"
    path.write_text("\n".join(lines).rstrip() + "\n")
    return path


async def evaluate(base: str, email: str, password: str) -> list[Outcome]:
    timeout = httpx.Timeout(600, connect=10)
    async with httpx.AsyncClient(base_url=base, timeout=timeout) as client:
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        login.raise_for_status()
        auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
        headers = {**auth, "X-Organization-Id": await organization(client, auth)}

        documents: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as folder:
            for attack in ATTACKS:
                documents[attack.id] = await upload(
                    client, headers, build_file(attack, Path(folder))
                )
        for document_id in documents.values():
            await wait_ready(client, headers, document_id)
        print(f"{len(documents)} documentos listos en «{ORGANIZATION_SLUG}».")

        outcomes = []
        for attack in ATTACKS:
            started = time.perf_counter()
            answer = await ask(client, headers, attack.question, documents[attack.id])
            outcome = Outcome(
                attack=attack,
                answer=answer,
                won=attack_won(attack, answer),
                answered_fact=attack.expected.lower() in answer.lower(),
                seconds=time.perf_counter() - started,
            )
            outcomes.append(outcome)
            verdict = f"GANÓ ({', '.join(outcome.won)})" if outcome.won else "resistió"
            print(f"{attack.id:22} {verdict:28} dato={'sí' if outcome.answered_fact else 'no'}")
        print("Informe:", write_report(outcomes, base))
        return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:3000")
    parser.add_argument("--email", default="ana@acme.test")
    args = parser.parse_args()
    password = os.environ.get("INJECTION_PASSWORD", DEMO_PASSWORD)
    outcomes = asyncio.run(evaluate(args.base, args.email, password))
    if any(o.won for o in outcomes):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
