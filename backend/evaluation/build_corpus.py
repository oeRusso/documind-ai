"""Build the evaluation corpus: Argentine national laws from Infoleg, as PDFs with stable pages.

    uv run python -m evaluation.build_corpus            # rebuild PDFs from the cached HTML
    uv run python -m evaluation.build_corpus --download  # fetch the HTML again first

Legal and polite:
- The texts are official national laws, published by the Ministerio de Justicia on Infoleg
  (servicios.infoleg.gob.ar) for free public access. Infoleg has no robots.txt restrictions.
- One request at a time, with a pause between them and a User-Agent that says who we are.
- Only the text is kept. The PDFs are generated here (so their pages never change) and each one
  records its source URL, the download date and the SHA-256 of what was downloaded
  (`corpus/manifest.json`).
"""

import argparse
import hashlib
import html
import json
import re
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf as _pymupdf

pymupdf: Any = _pymupdf

HERE = Path(__file__).parent
CORPUS = HERE / "corpus"
CACHE = HERE / ".cache" / "infoleg"  # raw HTML, not committed (see .gitignore)
BASE_URL = "http://servicios.infoleg.gob.ar/infolegInternet/anexos/"
USER_AGENT = "DocuMind-AI-dataset/0.1 (proyecto educativo, sin fines de lucro)"
PAUSE_SECONDS = 3

# slug -> (path on Infoleg, title). The title is checked against the downloaded page.
LAWS: dict[str, tuple[str, str]] = {
    "ley-20744-contrato-de-trabajo": ("25000-29999/25552/texact.htm", "20.744"),
    "ley-24240-defensa-del-consumidor": ("0-4999/638/texact.htm", "24.240"),
    "ley-25326-datos-personales": ("60000-64999/64790/texact.htm", "25.326"),
    "ley-25506-firma-digital": ("70000-74999/70749/texact.htm", "25.506"),
    "ley-24557-riesgos-del-trabajo": ("25000-29999/27971/texact.htm", "24557"),
    "ley-19549-procedimientos-administrativos": ("20000-24999/22363/texact.htm", "19.549"),
    "ley-27275-acceso-a-la-informacion": ("265000-269999/265949/norma.htm", "27275"),
    "ley-27555-teletrabajo": ("340000-344999/341093/norma.htm", "27555"),
    "ley-25675-ambiente": ("75000-79999/79980/norma.htm", "25.675"),
    "ley-26657-salud-mental": ("175000-179999/175977/norma.htm", "26.657"),
    "ley-11723-propiedad-intelectual": ("40000-44999/42755/texact.htm", "11.723"),
    "ley-26061-ninas-ninos-adolescentes": ("110000-114999/110778/norma.htm", "26.061"),
}


@dataclass(frozen=True)
class CorpusEntry:
    slug: str
    file: str
    source_url: str
    retrieved_at: str
    source_sha256: str
    pages: int


def download(slug: str, path: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f"{slug}.html"
    # A fixed official http URL (BASE_URL), never user input: S310 does not apply.
    request = urllib.request.Request(BASE_URL + path, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        target.write_bytes(response.read())
    time.sleep(PAUSE_SECONDS)
    return target


def html_to_text(raw: bytes) -> str:
    page = raw.decode("cp1252", errors="replace")
    page = re.sub(r"(?is)<(script|style).*?</\1>", "", page)
    page = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>|</li>", "\n", page)
    text = html.unescape(re.sub(r"<[^>]+>", "", page))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    # Drop Infoleg's site title at the top.
    return re.sub(r"^InfoLEG - Ministerio de Justicia[^\n]*\n+", "", text)


def write_pdf(text: str, target: Path) -> int:
    """A4 pages, 10 pt text: the same input always gives the same pages."""
    story = pymupdf.Story(html="".join(f"<p>{html.escape(p)}</p>" for p in text.split("\n\n")))
    story.user_css = "p { font-family: sans-serif; font-size: 10pt; margin-bottom: 5pt; }"
    writer = pymupdf.DocumentWriter(str(target))
    page_box = pymupdf.paper_rect("a4")
    margin = 60  # points (about 2 cm)
    content = pymupdf.Rect(
        page_box.x0 + margin, page_box.y0 + margin, page_box.x1 - margin, page_box.y1 - margin
    )
    pages = 0
    more = True
    while more:
        device = writer.begin_page(page_box)
        more, _ = story.place(content)
        story.draw(device)
        writer.end_page()
        pages += 1
    writer.close()
    return pages


def build(*, fetch: bool) -> list[CorpusEntry]:
    CORPUS.mkdir(parents=True, exist_ok=True)
    previous = {}
    manifest_path = CORPUS / "manifest.json"
    if manifest_path.exists():
        previous = {e["slug"]: e for e in json.loads(manifest_path.read_text())["documents"]}
    entries = []
    for slug, (path, number) in LAWS.items():
        cached = CACHE / f"{slug}.html"
        if fetch or not cached.exists():
            print(f"descargando {slug}…")
            cached = download(slug, path)
            retrieved = datetime.now(UTC).date().isoformat()
        else:
            retrieved = previous.get(slug, {}).get("retrieved_at", "desconocida")
        raw = cached.read_bytes()
        text = html_to_text(raw)
        if number not in text[:600]:
            raise SystemExit(f"{slug}: the page does not look like law {number}")
        pdf = CORPUS / f"{slug}.pdf"
        pages = write_pdf(text, pdf)
        entries.append(
            CorpusEntry(
                slug=slug,
                file=pdf.name,
                source_url=BASE_URL + path,
                retrieved_at=retrieved,
                source_sha256=hashlib.sha256(raw).hexdigest(),
                pages=pages,
            )
        )
        print(f"{slug}: {pages} páginas")
    manifest_path.write_text(
        json.dumps(
            {
                "source": (
                    "Infoleg (Ministerio de Justicia de la Nación), "
                    "textos oficiales de acceso libre"
                ),
                "documents": [asdict(e) for e in entries],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="fetch the laws again")
    build(fetch=parser.parse_args().download)


if __name__ == "__main__":
    main()
