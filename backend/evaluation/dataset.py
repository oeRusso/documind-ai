"""The evaluation dataset: corpus PDFs + questions with the page where the answer is.

    uv run python -m evaluation.dataset          # check every question against the PDFs
    uv run python -m evaluation.dataset --fix    # (re)write expected_page in questions.json

The page is never typed by hand: each question carries an `anchor`, an exact phrase of the
article that answers it, and the page is the one where that phrase appears once the PDF is read
and cleaned exactly like the app does (same reader, same normalization).
"""

import argparse
import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.modules.documents.domain.entities import FileKind
from app.modules.extraction.domain.normalization import normalize_text
from app.modules.extraction.infrastructure.readers import FileTextExtractor

HERE = Path(__file__).parent
CORPUS = HERE / "corpus"
QUESTIONS = HERE / "questions.json"


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    document: str | None  # slug of the corpus document; None = not answerable from the corpus
    article: str | None
    anchor: str | None
    expected_page: int | None

    @property
    def answerable(self) -> bool:
        return self.document is not None


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_text(text)).strip()


@cache
def page_texts(slug: str) -> list[str]:
    with FileTextExtractor().open(CORPUS / f"{slug}.pdf", FileKind.PDF) as reader:
        return [
            _flat(" ".join(block.text for block in reader.read_page(i).blocks))
            for i in range(reader.page_count)
        ]


def find_page(slug: str, anchor: str) -> int | None:
    needle = _flat(anchor)
    for number, text in enumerate(page_texts(slug), start=1):
        if needle in text:
            return number
    return None


def load_questions() -> list[Question]:
    data = json.loads(QUESTIONS.read_text())
    return [Question(**item) for item in data["questions"]]


def corpus_documents() -> list[str]:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    return [entry["slug"] for entry in manifest["documents"]]


def check(*, fix: bool) -> list[str]:
    """Problems found (empty = all good). With fix, store the pages that were found."""
    data = json.loads(QUESTIONS.read_text())
    problems = []
    for item in data["questions"]:
        if item["document"] is None:
            continue
        page = find_page(item["document"], item["anchor"])
        if page is None:
            problems.append(f"{item['id']}: anchor not found in {item['document']}")
        elif fix:
            item["expected_page"] = page
        elif item["expected_page"] != page:
            problems.append(f"{item['id']}: expected page {item['expected_page']}, found {page}")
    if fix:
        QUESTIONS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true")
    problems = check(fix=parser.parse_args().fix)
    for problem in problems:
        print(problem)
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
