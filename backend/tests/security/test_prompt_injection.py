"""Prompt injection without a model (stage 9): what a malicious document can reach.

The model itself is tested by `python -m evaluation.eval_injection` (real model, through the
API, also against the deployed version). Here, in CI, the defenses that do not depend on it:
1. Hidden text (white, transparent, microscopic) never reaches the chunks.
2. Visible attacks reach the model only inside their <fragmento>, with fake tags defused, and
   the fixed rules (system message) are never touched.
3. End to end through the API, the model receives exactly that.
"""

import re
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.documents.domain.entities import FileKind
from app.modules.extraction.domain.normalization import normalize_pages
from app.modules.extraction.infrastructure.readers import FileTextExtractor, is_hidden_span
from app.modules.ingestion.domain.chunking import chunk_blocks
from app.modules.knowledge.application.prompt import SYSTEM_PROMPT, build_messages
from app.modules.knowledge.domain.context import ContextSource
from evaluation.injection import ATTACKS, Attack, build_file

KINDS = {"pdf": FileKind.PDF, "md": FileKind.MARKDOWN}


def chunk_text(attack: Attack, folder: Path) -> str:
    path = build_file(attack, folder)
    with FileTextExtractor().open(path, KINDS[attack.kind]) as reader:
        pages = [reader.read_page(i) for i in range(reader.page_count)]
    return " ".join(" ".join(c.content.split()) for c in chunk_blocks(normalize_pages(pages)))


def flat(text: str) -> str:
    return " ".join(text.split())


@pytest.mark.parametrize("attack", [a for a in ATTACKS if a.hidden], ids=lambda a: a.id)
def test_hidden_text_never_reaches_the_chunks(attack: Attack, tmp_path: Path) -> None:
    text = chunk_text(attack, tmp_path)
    assert "remoto" in text  # the visible fact is there
    for marker in attack.forbidden:
        assert marker.lower() not in text.lower()


def test_what_counts_as_hidden() -> None:
    visible = {"text": "x", "color": 0, "alpha": 255, "size": 11.0}
    assert not is_hidden_span(visible)
    assert is_hidden_span({**visible, "color": 0xFFFFFF})  # white
    assert is_hidden_span({**visible, "color": 0xF5F5F5})  # almost white
    assert is_hidden_span({**visible, "alpha": 0})  # transparent / invisible render mode
    assert is_hidden_span({**visible, "size": 0.5})  # microscopic
    assert not is_hidden_span({**visible, "color": 0x1F3A93})  # blue headings are fine


@pytest.mark.parametrize("attack", [a for a in ATTACKS if not a.hidden], ids=lambda a: a.id)
def test_visible_attacks_reach_the_model_only_as_delimited_data(
    attack: Attack, tmp_path: Path
) -> None:
    content = chunk_text(attack, tmp_path)
    source = ContextSource(
        marker=1,
        document_id=uuid4(),
        document_title=attack.title,
        section=None,
        page_start=1,
        page_end=1,
        content=content,
        chunk_ids=(uuid4(),),
    )
    system, user = build_messages(attack.question, [source])

    assert system.content == SYSTEM_PROMPT  # the rules are never built from a document
    # Exactly one block of fragments, one fragment and one question: the real ones.
    assert len(re.findall(r"<fragmentos>", user.content)) == 1
    assert len(re.findall(r"</fragmentos>", user.content)) == 1
    assert len(re.findall(r"<fragmento ", user.content)) == 1
    assert len(re.findall(r"</fragmento>", user.content)) == 1
    assert len(re.findall(r"<pregunta>", user.content)) == 1
    # The attack is inside the fragment, and the question is the person's, at the end.
    start, end = user.content.index("<fragmento "), user.content.index("</fragmento>")
    assert flat(attack.fact)[:40] in flat(user.content[start:end])
    assert user.content.endswith(f"<pregunta>\n{attack.question}\n</pregunta>")
