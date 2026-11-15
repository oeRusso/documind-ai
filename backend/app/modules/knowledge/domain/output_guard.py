"""Remove from an answer what an answer never needs and an attack would use (stage 9).

A document can ask the model to "copy this HTML" or "add this image": a Markdown image
(`![x](https://...)`) makes some viewers load a URL by themselves, which can leak the question
to someone else's server; HTML can carry scripts. The web already shows answers as plain text,
but the API is also used by other clients, and small models do obey sometimes (measured with
evaluation.eval_injection). So, before anything leaves the server:
- HTML tags (`<img ...>`, `<script>`, `</b>`, `<!-- -->`) are removed;
- Markdown images are removed;
Links stay as text (a document may legitimately contain an address); the web does not make them
clickable.

Like the citation filter, it works on pieces of a stream: a tag can arrive as "<im", "g src=".
It holds back only what could still become a tag or an image, up to a limit; a "<" that turns
out to be plain text ("a < b") is released as it was. Pure Python.
"""

import re

# What a tag looks like: "<" followed by a letter, "/" or "!".
_TAG_START = re.compile(r"<[A-Za-z/!]")
_TAG = re.compile(r"<[A-Za-z/!][^<>]*>")
_IMAGE = re.compile(r"!\[[^\]\n]*\]\([^)\n]*\)")
_IMAGE_START = "!["
# Longer than this without closing: it is not a tag / image, release it as text.
_MAX_HELD = 400


class OutputGuard:
    """Usage: `shown = guard.feed(piece)` for each piece, then `guard.finish()` once."""

    def __init__(self) -> None:
        self._pending = ""
        self.removed: list[str] = []  # what was taken out (the use case logs it)

    def feed(self, piece: str) -> str:
        self._pending += piece
        return self._drain(final=False)

    def finish(self) -> str:
        return self._drain(final=True)

    def _clean(self, text: str) -> str:
        for pattern in (_IMAGE, _TAG):
            self.removed.extend(m.group(0) for m in pattern.finditer(text))
            text = pattern.sub("", text)
        return text

    def _drain(self, *, final: bool) -> str:
        text = self._clean(self._pending)
        if final:
            self._pending = ""
            return text
        # Hold back from the last place where a tag or an image could be starting.
        candidates = [m.start() for m in _TAG_START.finditer(text)]
        image = text.rfind(_IMAGE_START)
        if image != -1:
            candidates.append(image)
        if text.endswith(("<", "!")):
            candidates.append(len(text) - 1)
        hold_from = max(candidates, default=len(text))
        if len(text) - hold_from > _MAX_HELD:
            hold_from = len(text)  # never closed: plain text after all
        self._pending = text[hold_from:]
        return text[:hold_from]
