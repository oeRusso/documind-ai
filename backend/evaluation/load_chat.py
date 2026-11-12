"""Several questions at once against the running stack (stage 7, "5 preguntas simultáneas").

    uv run python -m evaluation.load_chat                     # 5 questions, through the web (:3000)
    uv run python -m evaluation.load_chat --base http://127.0.0.1:8000 --questions 8

Logs in with a seed user (app/dev/seed.py, public demo password), sends every question at once
to POST /api/v1/chat and reads the streams. For each one it prints the queue positions it saw,
the time to the first token, the total time and how it ended. It also samples the memory of the
Ollama and API containers while it runs. Needs `podman compose up` and documents loaded in Acme.
"""

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field

import httpx

from app.dev.seed import DEMO_PASSWORD
from evaluation.eval_answers import ram_sampler

QUESTIONS = [
    "¿Cuánto dura el período de prueba?",
    "¿Cuántos días de vacaciones corresponden?",
    "¿Cómo se calcula el aguinaldo?",
    "¿Qué garantía tienen los productos usados?",
    "¿Quién ganó el mundial de 1986?",
    "¿Qué es una firma digital?",
    "¿Cuál es el plazo para responder un pedido de información pública?",
    "¿Qué indemnización corresponde por despido sin causa?",
]


@dataclass
class Run:
    question: str
    positions: list[int] = field(default_factory=list)
    first_token_s: float | None = None
    total_s: float = 0.0
    ended: str = "?"
    chars: int = 0


async def ask(client: httpx.AsyncClient, headers: dict[str, str], question: str) -> Run:
    run = Run(question)
    started = time.perf_counter()
    async with client.stream(
        "POST", "/api/v1/chat", json={"question": question}, headers=headers
    ) as response:
        if response.status_code != 200:
            await response.aread()
            run.ended = f"HTTP {response.status_code}: {response.text[:120]}"
            return run
        event = ""
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "queued":
                    run.positions.append(data["position"])
                elif event == "token":
                    if run.first_token_s is None:
                        run.first_token_s = round(time.perf_counter() - started, 1)
                    run.chars += len(data["text"])
                elif event == "done":
                    run.ended = "sin evidencia" if data["no_evidence"] else "respondida"
                elif event == "error":
                    run.ended = f"error: {data['code']}"
    run.total_s = round(time.perf_counter() - started, 1)
    return run


async def main(base: str, count: int, email: str) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(900, connect=10)) as client:
        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD}
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        org = (await client.get("/api/v1/organizations", headers=auth)).json()["items"][0]["id"]
        headers = {**auth, "X-Organization-Id": org}
        questions = (QUESTIONS * (count // len(QUESTIONS) + 1))[:count]
        print(f"Enviando {count} preguntas a la vez a {base}…")
        started = time.perf_counter()
        with (
            ram_sampler("documind-ollama-1") as ollama_ram,
            ram_sampler("documind-api-1") as api_ram,
        ):
            runs = await asyncio.gather(*(ask(client, headers, q) for q in questions))
        print(f"\nTodas terminaron en {time.perf_counter() - started:.0f} s\n")
        for run in runs:
            print(
                f"- {run.question[:55]:55} cola={run.positions or '-'} "
                f"1er token={run.first_token_s}s total={run.total_s}s → {run.ended}"
            )
        if ollama_ram:
            print(f"\nRAM pico: Ollama {max(ollama_ram):.2f} GB", end="")
        if api_ram:
            print(f", API {max(api_ram):.2f} GB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default="http://127.0.0.1:3000")
    parser.add_argument("--questions", type=int, default=5)
    parser.add_argument("--email", default="ana@acme.test")
    args = parser.parse_args()
    asyncio.run(main(args.base, args.questions, args.email))
