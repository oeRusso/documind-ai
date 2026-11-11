"""Citation markers in an answer: keep the ones that point to a given chunk, drop the rest.

The model is told to cite with [n], where n is the number of a chunk it received. A small model
can still write [7] when it got three chunks, or a number it made up: that citation would point
nowhere (or worse, look real). So every marker is checked against the numbers really given:
- valid ([2], or [1, 3] -> written as [1][3]) -> kept, and reported in `used`;
- invalid ([7], [0]) -> removed from the text, with the space before it, and reported in
  `invalid` (the use case logs them);
- brackets that are not markers ([a], [1-3], [12345]) -> left alone, they are plain text.

The answer arrives in pieces (streaming), and a marker can be split: "[", "1", "4", "]". The
filter holds back only what could still become a marker (a "[" with digits after it) and the
spaces before it; everything else goes out at once.
"""

import re
from collections.abc import Collection
from dataclasses import dataclass

# [n] or [n, m, ...], with 1 to 3 digits each and optional spaces inside the brackets.
_MARKER = re.compile(r"\[\s*(\d{1,3}(?:\s*,\s*\d{1,3})*)\s*\]")
# What a marker looks like before its "]" arrives.
_PARTIAL = re.compile(r"\[[\d,\s]*")
# A "[" followed by more than this without closing is not a marker: release it as text.
_MAX_MARKER_CHARS = 24


@dataclass(frozen=True, slots=True)
class MarkerCheck:
    text: str  # the answer without invalid markers
    used: list[int]  # valid markers, in order of first appearance, without repeats
    invalid: list[int]  # removed markers, same order


class MarkerFilter:
    """Feed it the pieces of the answer; it returns what can be shown now.

    Usage: `shown = f.feed(piece)` for each piece, then `f.finish()` once at the end.
    """

    def __init__(self, valid: Collection[int]) -> None:
        self._valid = frozenset(valid)
        self._pending = ""  # held back: trailing spaces and/or a possible unfinished marker
        self.used: list[int] = []
        self.invalid: list[int] = []

    def feed(self, piece: str) -> str:
        self._pending += piece
        return self._drain(final=False)

    def finish(self) -> str:
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> str:
        out: list[str] = []
        while True:
            buffer = self._pending
            start = buffer.find("[")
            if start == -1:
                if final:
                    out.append(buffer)
                    self._pending = ""
                else:
                    # Keep trailing spaces: if a marker comes next and is invalid, they go too.
                    text = buffer.rstrip()
                    out.append(text)
                    self._pending = buffer[len(text) :]
                break

            before, rest = buffer[:start], buffer[start:]
            text = before.rstrip()
            spaces = before[len(text) :]
            out.append(text)

            marker = _MARKER.match(rest)
            if marker:
                numbers = [int(n) for n in marker.group(1).split(",")]
                kept = [n for n in numbers if n in self._valid]
                for n in numbers:
                    seen = self.used if n in self._valid else self.invalid
                    if n not in seen:
                        seen.append(n)
                if kept:
                    out.append(spaces + "".join(f"[{n}]" for n in kept))
                self._pending = rest[marker.end() :]
                continue

            might_be_marker = _PARTIAL.fullmatch(rest) and len(rest) <= _MAX_MARKER_CHARS
            if might_be_marker and not final:
                self._pending = spaces + rest  # wait for the next piece
                break

            out.append(spaces + "[")  # a plain bracket: show it and go on after it
            self._pending = rest[1:]
        return "".join(out)


def check_markers(text: str, valid: Collection[int]) -> MarkerCheck:
    """The same check on a whole text at once (used by tests and the evaluation)."""
    markers = MarkerFilter(valid)
    clean = markers.feed(text) + markers.finish()
    return MarkerCheck(clean, markers.used, markers.invalid)
