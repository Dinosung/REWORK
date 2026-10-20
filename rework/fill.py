"""Fill a template's placeholder text (on the cover, in headers and footers) with the document's values.

`replace` pairs are plain text, not regular expressions: template placeholders such as
"[Client Name]" or "<date>" are full of characters a regex would misread. All pairs are applied
in one pass over the original text, so a value inserted by one pair is never re-matched by another.
"""
import bisect
import re
import string
from collections import Counter

from .ooxml import w

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def check_pairs(pairs) -> list[tuple[str, str]]:
    shape = '"replace" must be a list of ["text in the template", "replacement"] pairs'
    if not isinstance(pairs, list):
        raise ValueError(shape)
    for i, pair in enumerate(pairs, 1):
        if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(s, str) for s in pair)):
            raise ValueError(f"{shape}; entry {i} is {pair!r}")
        if not pair[0]:
            raise ValueError(f'"replace" entry {i} has empty text to find')
    return [tuple(p) for p in pairs]


class Filler:
    def __init__(self, pairs, values: dict[str, str]):
        pairs = check_pairs(pairs)
        missing = sorted({f for _, repl in pairs for _, f, _, _ in string.Formatter().parse(repl)
                          if f and f not in values})
        if missing:
            sets = " ".join(f"--set {f}=..." for f in missing)
            raise ValueError(f"no value for {', '.join('{' + f + '}' for f in missing)}: "
                             f"add {'it' if len(missing) == 1 else 'them'} to the front matter or pass {sets}")
        self.filled = {text: repl.format_map(values) for text, repl in pairs}
        longest_first = sorted(self.filled, key=len, reverse=True)
        self.pattern = re.compile("|".join(map(re.escape, longest_first))) if pairs else None
        self.hits: Counter = Counter()

    def paragraph(self, p) -> bool:
        """Replace placeholders in paragraph `p`. Returns True if its text changed.

        Each replacement goes into the run where the placeholder starts, so the placeholder's
        formatting (underline, bold, colour) is kept and the rest of the paragraph is untouched.
        """
        runs = list(p.iter(w("t")))
        if not runs or self.pattern is None:
            return False
        starts, pos = [], 0
        for t in runs:
            starts.append(pos)
            pos += len(t.text or "")
        matches = list(self.pattern.finditer("".join(t.text or "" for t in runs)))
        for m in reversed(matches):  # back to front, so earlier offsets stay valid
            first = _run_at(starts, m.start())
            last = _run_at(starts, m.end() - 1)
            head = runs[first].text[: m.start() - starts[first]]
            tail = runs[last].text[m.end() - starts[last]:]
            for t in runs[first + 1:last + 1]:
                t.text = ""
            runs[first].text = head + self._swap(m) + (tail if first == last else "")
            if first != last:
                runs[last].text = tail
            for t in (runs[first], runs[last]):
                t.set(XML_SPACE, "preserve")
        return bool(matches)

    def _swap(self, match) -> str:
        self.hits[match.group()] += 1
        return self.filled[match.group()]

    def unused(self) -> list[str]:
        return [text for text in self.filled if not self.hits[text]]


def _run_at(starts: list[int], index: int) -> int:
    """Index of the run holding character `index` (empty runs share a start; the last one wins)."""
    return bisect.bisect_right(starts, index) - 1
