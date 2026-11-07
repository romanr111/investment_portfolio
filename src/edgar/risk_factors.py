"""Item 1A (Risk Factors) extraction and diffing from EDGAR 10-K/10-Q HTML.

Standard library only: a small HTMLParser converts block-tag HTML to plain
text, a slice finder isolates Item 1A (between Item 1A and the next Item 1B
marker) and ``difflib`` renders a unified diff. Raw filing HTML is never
persisted; only the extracted slice, its metadata and the capped diff text.
"""
import difflib
import re
from html.parser import HTMLParser

MAX_DIFF_CHARS = 64 * 1024

STATUS_EXTRACTED = "extracted"
STATUS_NOT_FOUND = "item1a_not_found"
STATUS_EMPTY = "empty"

# Block tags in the 10-K/10-Q subset that end a text line.
BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "br",
        "li",
        "ul",
        "ol",
        "tr",
        "table",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "header",
        "footer",
        "blockquote",
        "center",
        "font",
    }
)
_SKIP_TAGS = frozenset({"script", "style", "head", "title"})
_ITEM_1A = re.compile(
    r"Item\s+1A\.?\s*(?:Risk\s+Factors)?(?!\d)", re.IGNORECASE
)
_ITEM_BOUNDARY = re.compile(
    r"Item\s+(?:1B|1C|2)\.?(?!\d)", re.IGNORECASE
)
_ITEM_CODE = re.compile(r"Item\s+(\d\.\d{2})\b", re.IGNORECASE)


class _BlockTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._chunks = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        joined = "".join(self._chunks)
        collapsed = re.sub(r"[ \t]+", " ", joined)
        collapsed = re.sub(r"\n\s*\n\s*\n+", "\n\n", collapsed)
        return collapsed.strip()


def html_to_text(html_text: str) -> str:
    """Convert filing HTML to plain text with newlines between blocks."""
    parser = _BlockTextParser()
    try:
        parser.feed(html_text or "")
    except Exception:  # malformed markup: keep whatever was parsed so far
        pass
    return parser.text()


def _occurrences(text: str, pattern) -> list:
    return [match.start() for match in pattern.finditer(text)]


def extract_item_1a(text: str):
    """Slice Item 1A out of plain filing text.

    Returns (status, section_text). TOC pages also carry "Item 1A" markers,
    so each candidate start is paired with the next Item 1B (or Item 1C/2)
    boundary and the longest candidate wins - a body section is always
    longer than a table-of-contents row.
    """
    if text is None:
        return STATUS_NOT_FOUND, ""
    item_matches = list(_ITEM_1A.finditer(text))
    if not item_matches:
        return STATUS_NOT_FOUND, ""
    boundaries = _occurrences(text, _ITEM_BOUNDARY)
    best = None
    for item_match in item_matches:
        start = item_match.start()
        following_end = next((end for end in boundaries if end > start), None)
        # The body starts after the marker itself (the regex consumes the
        # trailing "Risk Factors" label and following whitespace), so a
        # marker immediately followed by Item 1B counts as empty.
        chunk = text[item_match.end():following_end].strip()
        if best is None or len(chunk) > len(best[0]):
            best = (chunk, following_end is not None)
    if best is None:
        return STATUS_NOT_FOUND, ""
    chunk = best[0].strip()
    if not chunk:
        return STATUS_EMPTY, ""
    return STATUS_EXTRACTED, chunk


def risk_headers(text: str) -> list:
    """Standalone heading-like lines of a plain-text 10-K/10-Q section."""
    headers = []
    if not text:
        return headers
    lines = text.splitlines()
    for index, line in enumerate(lines):
        candidate = line.strip()
        if not (3 <= len(candidate) <= 120):
            continue
        if not any(ch.isalpha() for ch in candidate):
            continue
        if candidate.endswith((".", ",", ";", ":")):
            continue
        previous_blank = index == 0 or not lines[index - 1].strip()
        next_blank = index == len(lines) - 1 or not lines[index + 1].strip()
        if previous_blank and next_blank:
            headers.append(candidate)
    return headers


def diff_text(old_text: str, new_text: str, max_chars: int = MAX_DIFF_CHARS):
    """Unified diff of two plain-text sections.

    Returns (added, removed, diff_text_capped_64k, added_header_lines[:3]).
    """
    old_lines = (old_text or "").splitlines(keepends=True)
    new_lines = (new_text or "").splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(old_lines, new_lines, fromfile="previous", tofile="current", n=2)
    )
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    diff_joined = "".join(diff_lines)
    if len(diff_joined) > max_chars:
        diff_joined = diff_joined[:max_chars]

    header_set = set(risk_headers(new_text or ""))
    headers = []
    for line in diff_lines:
        if not line.startswith("+") or line.startswith("+++"):
            continue
        candidate = line[1:].strip("\n").strip()
        if candidate in header_set and candidate not in headers:
            headers.append(candidate)
    return added, removed, diff_joined, headers[:3]


def scan_item_codes(doc_text: str) -> list:
    """Unique 8-K item codes found in a filing document (8-K/A doc-scan)."""
    found = []
    for match in _ITEM_CODE.finditer(doc_text or ""):
        code = match.group(1)
        if code not in found:
            found.append(code)
    return found
