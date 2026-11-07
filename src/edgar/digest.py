"""Digest rendering for the EDGAR watch.

Plain text (no parse_mode), one message per run. Sections order RED ->
WARN -> INFO, with Form 4 folded per ticker and a truncation marker
pointing at the alerts log. Zero new filings render the heartbeat line.
Truncation drops the lowest priority first (INFO lines, then Form 4 fold
lines, then WARN lines); RED lines are kept while the budget holds and
hard-truncated only as a last resort.
"""
import logging

logger = logging.getLogger(__name__)

DEFAULT_CHAR_BUDGET = 4000
DEFAULT_MAX_RED_LINES = 12
DEFAULT_MAX_INFO_LINES = 10
DEFAULT_MAX_FORM4_LINES = 4

MARK_RED = "\U0001F534"  # red circle
MARK_WARN = "⚠️"  # warning sign
MARK_INFO = "ℹ️"  # information sign
MARK_OK = "✅"  # check mark

ALERTS_LOG_PATH = "data/edgar/alerts.jsonl"

_FORM_4 = "4"

# Lower rank wins when several items land on one filing.
_LEVEL_RANK = {"RED": 0, "WARN": 1, "INFO": 2}

RF_SUFFIXES = {
    "document_fetch_failed": "document fetch failed",
    "item1a_not_found": "item 1A not found",
    "empty": "empty 1A",
    "no_baseline": "no baseline",
}


def digest_settings(config) -> dict:
    settings = dict(config or {})
    return {
        "max_red_lines": int(settings.get("max_red_lines", DEFAULT_MAX_RED_LINES)),
        "max_info_lines": int(settings.get("max_info_lines", DEFAULT_MAX_INFO_LINES)),
        "max_form4_lines": int(settings.get("max_form4_lines", DEFAULT_MAX_FORM4_LINES)),
        "char_budget": int(settings.get("char_budget", DEFAULT_CHAR_BUDGET)),
    }


def build_digest(results, skipped, ctx) -> str:
    """Render the run digest text.

    results: per processed position dicts (ticker, cik, error, events, rf).
    skipped: dict with unresolved/fund/excluded lists plus value_filtered and
    hidden_by_limit counts. ctx: ts, positions, monitored, processed, new,
    failures, digest settings.
    """
    settings = digest_settings(ctx.get("digest"))
    monitor_count = int(ctx.get("monitored", 0))
    red_blocks = []
    warn_blocks = []
    form4_lines = []
    info_blocks = []

    for result in results or []:
        ticker = result.get("ticker", "")
        events = result.get("events") or []
        form4_count = 0
        item_events = []
        for event in events:
            if event.get("form") == _FORM_4:
                form4_count += 1
            else:
                item_events.append(event)
        for group in _group_events(item_events):
            block = _filing_block(ticker, group)
            level = group["level"]
            if level == "RED":
                red_blocks.append(block)
            elif level == "WARN":
                warn_blocks.append(block)
            else:
                info_blocks.append(block)
        if form4_count:
            form4_lines.append(
                f"{MARK_INFO} [{ticker}] {form4_count} × Form 4 (insider changes)"
            )
        for rf_entry in result.get("rf") or []:
            info_blocks.append(_rf_block(ticker, rf_entry))

    red_blocks = red_blocks[: max(0, settings["max_red_lines"])]
    form4_lines = form4_lines[: max(0, settings["max_form4_lines"])]
    info_blocks = info_blocks[: max(0, settings["max_info_lines"])]

    failures = ctx.get("failures") or []
    new_count = int(ctx.get("new", 0))
    has_content = bool(red_blocks or warn_blocks or form4_lines or info_blocks)
    if new_count == 0 and not has_content and not failures:
        return (
            f"{MARK_OK} EDGAR watch ok · 0 new filings · {monitor_count} monitored"
        )

    header = (
        f"EDGAR watch · {ctx.get('ts', '')} · positions "
        f"{int(ctx.get('positions', 0))} · monitored {monitor_count} · new {new_count}"
    )
    failure_blocks = [
        f"{MARK_WARN} CIK error [{failure.get('ticker', '')}] - "
        f"{_one_line(str(failure.get('error', 'unknown error')))}"
        for failure in failures
    ]

    footer = _render_footer(skipped, ctx)
    body, dropped = _assemble(
        header, red_blocks, warn_blocks, failure_blocks, form4_lines, info_blocks, settings
    )
    body += "\n".join(line if line.startswith("\n") else "\n" + line for line in footer)
    if dropped:
        body += f"\n… (+{dropped} entries in {ALERTS_LOG_PATH})"
    return body


def _group_events(events):
    """Group per-item events of one filing: key (form, accession), EDGAR order."""
    groups = {}
    order = []
    for event in events:
        key = (str(event.get("form", "")), str(event.get("accession", "")))
        if key not in groups:
            groups[key] = {
                "form": key[0],
                "accession": key[1],
                "filed": event.get("filed", ""),
                "url": event.get("url", ""),
                "level": "INFO",
                "items": [],
            }
            order.append(key)
        group = groups[key]
        code = event.get("item_code") or event.get("items") or ""
        title = event.get("title") or ""
        group["items"].append((code, title))
        level = event.get("level", "INFO")
        if _LEVEL_RANK.get(level, 2) < _LEVEL_RANK.get(group["level"], 2):
            group["level"] = level
    return [groups[key] for key in order]


def _filing_block(ticker: str, group: dict) -> list:
    mark = {"RED": MARK_RED, "WARN": MARK_WARN, "INFO": MARK_INFO}.get(group["level"], MARK_INFO)
    codes = [code for code, _ in group["items"] if code]
    titles = [title for _, title in group["items"] if title]
    items_part = f" item {','.join(codes)}" if codes else ""
    if len(codes) > 1:
        items_part = f" items {','.join(codes)}"
    title_part = f" - {'; '.join(dict.fromkeys(titles))}" if titles else ""
    filed_part = f" (filed {group['filed']})" if group.get("filed") else ""
    header_line = f"{mark} [{ticker}] {group['form']}{items_part}{title_part}{filed_part}"
    block = [header_line]
    url = group.get("url") or ""
    if url:
        block.append(url)
    return block


def _rf_block(ticker: str, rf_entry: dict) -> list:
    form = rf_entry.get("form", "")
    filed = rf_entry.get("filed", "")
    status = rf_entry.get("status", "extracted")
    header_line = f"{MARK_INFO} [{ticker}] {form} filed {filed} - "
    if status == "extracted":
        added = int(rf_entry.get("added", 0))
        removed = int(rf_entry.get("removed", 0))
        header_line += f"Risk Factors: +{added}/-{removed}"
        headers = rf_entry.get("headers") or []
        if rf_entry.get("no_baseline"):
            header_line += f" ({RF_SUFFIXES['no_baseline']})"
        elif headers:
            quoted = ", ".join(f'"{header}"' for header in headers)
            header_line += f"; new: {quoted}"
    else:
        suffix = RF_SUFFIXES.get(status, status)
        header_line += f"Risk Factors unavailable ({suffix})"
    block = [header_line]
    url = rf_entry.get("url") or ""
    if url:
        block.append(url)
    return block


def _render_footer(skipped, ctx) -> list:
    if not skipped:
        return []
    unresolved = len(skipped.get("unresolved") or [])
    fund = len(skipped.get("fund") or [])
    excluded = len(skipped.get("excluded") or [])
    parts = []
    if unresolved or fund:
        parts.append(f"Skipped: {unresolved} unresolved, {fund} fund-like")
    if excluded:
        parts.append(f"Excluded: {excluded} by config")
    value_filtered = int(skipped.get("value_filtered") or 0)
    if value_filtered:
        parts.append(f"Below value floor: {value_filtered}")
    hidden = int(skipped.get("hidden_by_limit") or 0)
    if hidden:
        parts.append(
            f"--limit-tickers hid {hidden} of {int(ctx.get('monitored', 0))} monitored"
        )
    if not parts:
        return []
    return [". ".join(parts) + "."]


def _one_line(message: str, limit: int = 200) -> str:
    collapsed = " ".join(str(message).split())
    return collapsed[:limit]


def _assemble(header, red_blocks, warn_blocks, failure_blocks, form4_lines, info_blocks, settings):
    """Join blocks by priority; returns (text, dropped_count).

    RED blocks are always kept (the budget can be exceeded by RED only, in
    which case the text is hard-truncated). WARN, FORM 4 and INFO blocks are
    dropped in ascending priority when the budget is exhausted.
    """
    budget = max(0, int(settings["char_budget"]))
    text = header
    dropped = 0

    for block in red_blocks:
        text += "\n\n" + "\n".join(block)

    def _add_droppable(blocks):
        nonlocal text, dropped
        for block in blocks:
            lines = [block] if isinstance(block, str) else block
            candidate = text + "\n\n" + "\n".join(lines)
            if len(candidate) > budget:
                dropped += 1
                continue
            text = candidate

    _add_droppable(warn_blocks)
    for block in failure_blocks:
        text += "\n\n" + block
    _add_droppable(form4_lines)
    _add_droppable(info_blocks)

    if len(text) > budget:
        text = text[:budget].rstrip()
    return text, dropped
