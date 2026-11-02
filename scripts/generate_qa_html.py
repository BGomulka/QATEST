#!/usr/bin/env python3
"""Generate a self-contained interactive QA.html page from documentation/QA.md.

This script enforces that `documentation/QA.md` remains pure Markdown (zero raw
HTML tags or angle-bracket elements, and checkboxes only on Pass/Complete
verification outcomes) and builds an interactive HTML form supporting:
  - Interactive checkboxes exclusively on Pass / Complete outcomes
  - Interactive text / date / textarea inputs for QA metadata and table readings
  - Whole-page PDF export via window.print() and @media print styles
  - Single-row CSV export (Download .csv and Copy to Clipboard) with an optional
    column header row toggle for spreadsheet tracking
"""

from __future__ import annotations

import argparse
import html
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass, field


RAW_HTML_TAG_RE = re.compile(r"<(?:/?[A-Za-z!][^>]*)>")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
HR_RE = re.compile(r"^(?:-\s*){3,}$|^(?:\*\s*){3,}$|^(?:_\s*){3,}$")
LIST_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>(?:[-*+])|(?:\d+\.))\s+(?P<rest>.*)$")
CHECKBOX_ITEM_RE = re.compile(r"^\[(?P<state>[ xX])\]\s+(?P<label>.+?)\s*$")
CELL_CHECKBOX_RE = re.compile(r"^(?P<prefix>.*?)\[(?P<state>[ xX])\]\s*(?P<suffix>.*)$")
META_FIELD_RE = re.compile(r"^\*\*(?P<label>[^*]+?):\*\*\s*$")
TABLE_ALIGN_CELL_RE = re.compile(r"^:?-{2,}:?$")
CHANNEL_NUM_RE = re.compile(r"\bCh(?:annel)?\s*(\d+)\b", re.IGNORECASE)

FILLABLE_COL_KEYWORDS = (
    "measured",
    "notes",
    "variance",
    "reading",
    "observed",
    "value",
    "comment",
)

GENERIC_META_LABELS = {
    "notes",
    "notes / defects",
    "git revision / commit used",
    "comments",
}


def strip_markdown_formatting(text: str) -> str:
    """Return plain text with inline Markdown markers removed."""
    cleaned = re.sub(r"`([^`]+)`", r"\1", text)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)
    return " ".join(cleaned.split())


def slugify(text: str) -> str:
    """Create a URL-safe slug for heading and input IDs."""
    plain = strip_markdown_formatting(text).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")
    return slug or "section"


def render_inline(text: str) -> str:
    """Render inline Markdown (code spans, links, bold, emphasis) safely to HTML."""
    tokens: list[str] = []

    def stash(fragment: str) -> str:
        idx = len(tokens)
        tokens.append(fragment)
        return f"\x00TOK{idx}\x00"

    # 1. Stash inline code spans first so inner characters are not parsed as Markdown
    def replace_code(match: re.Match[str]) -> str:
        return stash(f"<code>{html.escape(match.group(1))}</code>")

    work = re.sub(r"`([^`]+)`", replace_code, text)

    # 2. Escape remaining raw text
    work = html.escape(work, quote=False)

    # 3. Links: [label](url)
    def replace_link(match: re.Match[str]) -> str:
        label_html = match.group(1)
        href = html.escape(html.unescape(match.group(2)).strip(), quote=True)
        return stash(
            f'<a href="{href}" target="_blank" rel="noopener noreferrer">{label_html}</a>'
        )

    work = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, work)

    # 4. Bold and italic emphasis
    work = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", work)
    work = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", work)
    work = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", work)

    # 5. Restore stashed HTML fragments
    for idx, fragment in enumerate(tokens):
        work = work.replace(f"\x00TOK{idx}\x00", fragment)

    return work


def is_outcome_label(plain_text: str) -> bool:
    """Return True iff text represents a Pass or Complete verification outcome."""
    lowered = plain_text.lower()
    return bool(re.search(r"\b(pass|complete)\b", lowered))


def outcome_values_for_label(plain_text: str) -> tuple[str, str]:
    """Return (checked_value, unchecked_value) matching the item label."""
    lowered = plain_text.lower()
    if re.search(r"\bcomplete\b", lowered) and not re.search(r"\bpass\b", lowered):
        return ("Complete", "Incomplete")
    return ("Pass", "Fail")


def split_table_row(line: str) -> list[str]:
    """Split a Markdown pipe-table row into stripped cell strings."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    cells = re.split(r"(?<!\\)\|", stripped)
    return [c.replace(r"\|", "|").strip() for c in cells]


def is_table_Separator(line: str) -> bool:
    """Return True if line is a Markdown pipe-table alignment row."""
    if "|" not in line:
        return False
    cells = split_table_row(line)
    return bool(cells) and all(bool(TABLE_ALIGN_CELL_RE.match(c)) for c in cells)


def validate_markdown(md_text: str, source_name: str = "QA.md") -> None:
    """Validate that QA.md contains zero raw HTML tags and only outcome checkboxes."""
    in_fence = False
    errors: list[str] = []

    for lineno, raw_line in enumerate(md_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # 1. Check for raw HTML tags or comments
        tag_match = RAW_HTML_TAG_RE.search(raw_line)
        if tag_match:
            errors.append(
                f"{source_name}:{lineno}: Raw HTML / angle-bracket element found: {tag_match.group(0)!r}"
            )

        # 2. Check list checkboxes
        list_match = LIST_ITEM_RE.match(raw_line)
        if list_match:
            cb_match = CHECKBOX_ITEM_RE.match(list_match.group("rest"))
            if cb_match:
                plain = strip_markdown_formatting(cb_match.group("label"))
                if not is_outcome_label(plain):
                    errors.append(
                        f"{source_name}:{lineno}: Checkbox on non-Pass/Complete procedural item: {plain!r}"
                    )
            continue

        # 3. Check table cell checkboxes
        if "|" in raw_line and not is_table_Separator(raw_line):
            for cell in split_table_row(raw_line):
                cell_cb = CELL_CHECKBOX_RE.match(cell)
                if cell_cb:
                    combined = strip_markdown_formatting(
                        f"{cell_cb.group('prefix')} {cell_cb.group('suffix')}"
                    )
                    if not is_outcome_label(combined):
                        errors.append(
                            f"{source_name}:{lineno}: Table checkbox on non-Pass/Complete cell: {cell!r}"
                        )

    if errors:
        raise ValueError("Markdown validation failed:\n  - " + "\n  - ".join(errors))


@dataclass
class BuildContext:
    """Tracks generated control IDs, section headings, and export ordering."""

    current_h2: str = ""
    current_h3: str = ""
    control_Seq: int = 0
    csv_order_seq: int = 0
    used_ids: set[str] = field(default_factory=set)
    metadata_headers: list[str] = field(default_factory=list)
    checkbox_headers: list[str] = field(default_factory=list)

    def next_id(self, prefix: str, label: str) -> str:
        self.control_Seq += 1
        base = f"{prefix}-{slugify(label)}"
        candidate = base
        if candidate in self.used_ids:
            candidate = f"{base}-{self.control_Seq}"
        self.used_ids.add(candidate)
        return candidate

    def next_csv_order(self) -> int:
        self.csv_order_seq += 1
        return self.csv_order_seq * 100


def placeholder_for_metadata(label: str) -> str:
    """Return a concise placeholder hint for a metadata input field."""
    lower = label.lower()
    if "serial" in lower:
        return "e.g., SN-1042"
    if "pcb revision" in lower or lower == "revision":
        return "e.g., Rev 1.0"
    if "performed by" in lower or "tester" in lower or "inspector" in lower:
        return "Inspector Name"
    if "commit" in lower or "git revision" in lower:
        return "e.g., a1b2c3d"
    if "notes" in lower or "defects" in lower:
        return "None / describe any observations..."
    if "deviations" in lower or "waivers" in lower or "comments" in lower:
        return "Record any deviations, waivers, or comments..."
    return ""


def build_metadata_item_html(label: str, ctx: BuildContext) -> str:
    """Render a metadata list item as an interactive text, date, or textarea field."""
    clean_label = strip_markdown_formatting(label).rstrip(":").strip()
    csv_header = clean_label
    if (
        clean_label.lower() in GENERIC_META_LABELS
        and ctx.current_h3
        and ctx.current_h3.lower() not in {"qa metadata", "final result"}
    ):
        csv_header = f"{ctx.current_h3} - {clean_label}"

    input_id = ctx.next_id("meta", csv_header)
    csv_order = ctx.next_csv_order()
    ctx.metadata_headers.append(csv_header)

    esc_header = html.escape(csv_header, quote=True)
    esc_label = html.escape(clean_label)
    placeholder = html.escape(placeholder_for_metadata(clean_label), quote=True)
    lower = clean_label.lower()

    if "date" in lower:
        control_html = (
            f'<input type="date" id="{input_id}" class="qa-input qa-date-input" '
            f'data-csv-role="metadata" data-csv-header="{esc_header}" '
            f'data-csv-order="{csv_order}">'
        )
        return (
            f'<li class="qa-meta-item">'
            f'<label class="qa-meta-label" for="{input_id}"><strong>{esc_label}:</strong></label>'
            f"{control_html}</li>"
        )

    if any(k in lower for k in ("deviations", "waivers", "comments")):
        control_html = (
            f'<textarea id="{input_id}" class="qa-input qa-textarea" rows="3" '
            f'placeholder="{placeholder}" data-csv-role="metadata" '
            f'data-csv-header="{esc_header}" data-csv-order="{csv_order}"></textarea>'
        )
        return (
            f'<li class="qa-meta-item qa-meta-block">'
            f'<label class="qa-meta-label" for="{input_id}"><strong>{esc_label}:</strong></label>'
            f"{control_html}</li>"
        )

    wide_cls = " qa-input-wide" if ("notes" in lower or "defects" in lower) else ""
    control_html = (
        f'<input type="text" id="{input_id}" class="qa-input{wide_cls}" '
        f'placeholder="{placeholder}" data-csv-role="metadata" '
        f'data-csv-header="{esc_header}" data-csv-order="{csv_order}">'
    )
    return (
        f'<li class="qa-meta-item">'
        f'<label class="qa-meta-label" for="{input_id}"><strong>{esc_label}:</strong></label>'
        f"{control_html}</li>"
    )


def build_checkbox_item_html(
    state_char: str, label_md: str, ctx: BuildContext
) -> str:
    """Render a Pass/Complete task list item as an interactive HTML checkbox."""
    plain_label = strip_markdown_formatting(label_md)
    checked_val, unchecked_val = outcome_values_for_label(plain_label)
    input_id = ctx.next_id("chk", plain_label)
    csv_order = ctx.next_csv_order()
    ctx.checkbox_headers.append((csv_order, plain_label))

    checked_attr = " checked" if state_char.lower() == "x" else ""
    esc_header = html.escape(plain_label, quote=True)
    rendered_label = render_inline(label_md)

    return (
        f'<li class="qa-check-item">'
        f'<label class="qa-check-label" for="{input_id}">'
        f'<input type="checkbox" id="{input_id}" class="qa-checkbox"{checked_attr} '
        f'data-csv-role="checkbox" data-csv-header="{esc_header}" '
        f'data-checked-value="{checked_val}" data-unchecked-value="{unchecked_val}" '
        f'data-csv-order="{csv_order}">'
        f'<span class="qa-check-text">{rendered_label}</span>'
        f"</label></li>"
    )


def indent_width(indent_str: str) -> int:
    """Compute column width of leading indentation."""
    return len(indent_str.expandtabs(4))


def parse_list_block(
    lines: list[str], start_idx: int, ctx: BuildContext
) -> tuple[str, int]:
    """Parse a contiguous (possibly nested) Markdown list block into HTML."""
    parsed_items: list[tuple[int, str, str]] = []
    idx = start_idx
    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            # Look ahead: if next non-empty line is deeply indented continuation, stop if top-level break
            break
        m = LIST_ITEM_RE.match(line)
        if not m:
            break
        ind = indent_width(m.group("indent"))
        marker = m.group("marker")
        list_type = "ol" if marker.endswith(".") else "ul"
        parsed_items.append((ind, list_type, m.group("rest")))
        idx += 1

    def classify_item_kind(rest: str) -> str:
        if CHECKBOX_ITEM_RE.match(rest):
            return "checkbox"
        if META_FIELD_RE.match(rest):
            return "meta"
        return "step"

    def render_level(pos: int, min_indent: int) -> tuple[str, int]:
        if pos >= len(parsed_items):
            return ("", pos)

        base_indent, list_type, first_rest = parsed_items[pos]
        first_kind = classify_item_kind(first_rest)
        list_classes: list[str] = []
        if first_kind == "checkbox":
            list_classes.append("qa-outcome-list")
        elif first_kind == "meta":
            list_classes.append("qa-meta-list")
        else:
            list_classes.append("qa-step-list")

        cls_attr = f' class="{" ".join(list_classes)}"' if list_classes else ""
        out: list[str] = [f"<{list_type}{cls_attr}>"]

        while pos < len(parsed_items):
            cur_indent, cur_type, cur_rest = parsed_items[pos]
            if cur_indent < base_indent:
                break
            cur_kind = classify_item_kind(cur_rest)
            # Split into a separate sibling list if list type (ul/ol) or semantic kind changes at same indent
            if cur_indent == base_indent and (
                cur_type != list_type or cur_kind != first_kind
            ):
                break

            if cur_indent > base_indent:
                nested_html, pos = render_level(pos, cur_indent)
                if out and out[-1].endswith("</li>"):
                    out[-1] = out[-1][:-5] + nested_html + "</li>"
                else:
                    out.append(nested_html)
                continue

            # Render item at base_indent
            cb_match = CHECKBOX_ITEM_RE.match(cur_rest)
            meta_match = META_FIELD_RE.match(cur_rest)
            if cb_match:
                li_html = build_checkbox_item_html(
                    cb_match.group("state"), cb_match.group("label"), ctx
                )
            elif meta_match:
                li_html = build_metadata_item_html(meta_match.group("label"), ctx)
            else:
                li_html = f"<li>{render_inline(cur_rest)}</li>"

            pos += 1
            if pos < len(parsed_items) and parsed_items[pos][0] > base_indent:
                nested_html, pos = render_level(pos, parsed_items[pos][0])
                li_html = li_html[:-5] + nested_html + "</li>"

            out.append(li_html)

        out.append(f"</{list_type}>")
        return ("\n".join(out), pos)

    pos = 0
    blocks: list[str] = []
    while pos < len(parsed_items):
        block_html, pos = render_level(pos, parsed_items[pos][0])
        blocks.append(block_html)

    return ("\n".join(blocks), idx)


def parse_table_block(
    lines: list[str], start_idx: int, ctx: BuildContext
) -> tuple[str, int]:
    """Parse a Markdown pipe table and inject interactive checkboxes and inputs."""
    header_cells = split_table_row(lines[start_idx])
    align_cells = split_table_row(lines[start_idx + 1])

    alignments: list[str] = []
    for ac in align_cells:
        if ac.startswith(":") and ac.endswith(":"):
            alignments.append("center")
        elif ac.endswith(":"):
            alignments.append("right")
        elif ac.startswith(":"):
            alignments.append("left")
        else:
            alignments.append("")

    idx = start_idx + 2
    body_rows: list[list[str]] = []
    while idx < len(lines):
        line = lines[idx]
        if not line.strip() or "|" not in line:
            break
        body_rows.append(split_table_row(line))
        idx += 1

    # Detect whether this table is a numbered channel matrix (e.g., Ch 0 .. Ch 15)
    table_base_order = ctx.next_csv_order()
    has_channel_numbers = any(
        CHANNEL_NUM_RE.search(cell)
        for row in body_rows
        for cell in row
        if CELL_CHECKBOX_RE.match(cell)
    )
    if has_channel_numbers:
        # Reserve enough ordering slots for all channels in this table
        ctx.csv_order_seq += len(body_rows) * max(1, len(header_cells))

    out: list[str] = ['<div class="qa-table-wrap"><table class="qa-table">']
    out.append("<thead><tr>")
    for col_i, h_text in enumerate(header_cells):
        align = alignments[col_i] if col_i < len(alignments) else ""
        style_attr = f' style="text-align: {align};"' if align else ""
        out.append(f"<th{style_attr}>{render_inline(h_text)}</th>")
    out.append("</tr></thead>")

    out.append("<tbody>")
    for row in body_rows:
        out.append("<tr>")
        row_key = strip_markdown_formatting(row[0]) if row else ""
        for col_i in range(len(header_cells)):
            cell_raw = row[col_i] if col_i < len(row) else ""
            col_header = strip_markdown_formatting(header_cells[col_i])
            align = alignments[col_i] if col_i < len(alignments) else ""
            style_attr = f' style="text-align: {align};"' if align else ""

            cell_cb = CELL_CHECKBOX_RE.match(cell_raw)
            if cell_cb:
                prefix_raw = cell_cb.group("prefix").strip()
                suffix_raw = cell_cb.group("suffix").strip()
                state_char = cell_cb.group("state")

                prefix_plain = strip_markdown_formatting(prefix_raw).rstrip(":").strip()
                suffix_plain = strip_markdown_formatting(suffix_raw).strip()
                combined_plain = " ".join(p for p in (prefix_plain, suffix_plain) if p)

                # Include row identifier in CSV header when checkbox is in a status column
                if not prefix_plain and row_key and col_i > 0:
                    csv_header = f"{row_key} {suffix_plain}".strip()
                else:
                    csv_header = combined_plain

                ch_match = CHANNEL_NUM_RE.search(csv_header)
                if has_channel_numbers and ch_match:
                    csv_order = table_base_order + int(ch_match.group(1))
                else:
                    csv_order = ctx.next_csv_order()

                checked_val, unchecked_val = outcome_values_for_label(csv_header)
                ctx.checkbox_headers.append((csv_order, csv_header))
                input_id = ctx.next_id("chk", csv_header)
                checked_attr = " checked" if state_char.lower() == "x" else ""
                esc_header = html.escape(csv_header, quote=True)

                prefix_html = (
                    f'<span class="qa-cell-prefix">{render_inline(prefix_raw)}</span> '
                    if prefix_raw
                    else ""
                )
                suffix_html = (
                    f'<span class="qa-check-text">{render_inline(suffix_raw)}</span>'
                    if suffix_raw
                    else ""
                )
                cell_html = (
                    f'<label class="qa-check-label qa-table-check" for="{input_id}">'
                    f"{prefix_html}"
                    f'<input type="checkbox" id="{input_id}" class="qa-checkbox"{checked_attr} '
                    f'data-csv-role="checkbox" data-csv-header="{esc_header}" '
                    f'data-checked-value="{checked_val}" data-unchecked-value="{unchecked_val}" '
                    f'data-csv-order="{csv_order}">'
                    f"{suffix_html}</label>"
                )
                out.append(f"<td{style_attr}>{cell_html}</td>")
            elif not cell_raw and any(
                kw in col_header.lower() for kw in FILLABLE_COL_KEYWORDS
            ):
                sec_prefix = f"{ctx.current_h3} " if ctx.current_h3 else ""
                aria_lbl = html.escape(
                    f"{sec_prefix}{row_key} {col_header}".strip(), quote=True
                )
                input_id = ctx.next_id("tbl", f"{sec_prefix}{row_key}-{col_header}")
                placeholder = (
                    "Enter value..."
                    if "measured" in col_header.lower()
                    else "Optional notes..."
                )
                cell_html = (
                    f'<input type="text" id="{input_id}" class="qa-input qa-table-input" '
                    f'aria-label="{aria_lbl}" placeholder="{placeholder}">'
                )
                out.append(f"<td{style_attr}>{cell_html}</td>")
            else:
                out.append(f"<td{style_attr}>{render_inline(cell_raw)}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return ("\n".join(out), idx)


def convert_markdown_body(md_text: str) -> tuple[str, str, BuildContext]:
    """Convert validated Markdown into HTML body content and return (title, html, ctx)."""
    lines = md_text.splitlines()
    ctx = BuildContext()
    blocks: list[str] = []
    doc_title = "Quality Assurance Procedure"

    idx = 0
    in_fence = False
    fence_lines: list[str] = []

    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        # Fenced code blocks
        if stripped.startswith("```"):
            if in_fence:
                blocks.append(
                    f"<pre><code>{html.escape(chr(10).join(fence_lines))}</code></pre>"
                )
                fence_lines = []
                in_fence = False
            else:
                in_fence = True
            idx += 1
            continue

        if in_fence:
            fence_lines.append(line)
            idx += 1
            continue

        # Blank line
        if not stripped:
            idx += 1
            continue

        # Horizontal rule
        if HR_RE.match(stripped):
            if getattr(ctx, "in_section", False):
                blocks.append("</section>")
                ctx.in_section = False
            blocks.append("<hr>")
            idx += 1
            continue

        # Heading
        h_match = HEADING_RE.match(line)
        if h_match:
            level = len(h_match.group(1))
            raw_heading = h_match.group(2)
            plain_heading = strip_markdown_formatting(raw_heading)
            if level == 1 and doc_title == "Quality Assurance Procedure":
                doc_title = plain_heading
            elif level == 2:
                ctx.current_h2 = plain_heading
                ctx.current_h3 = ""
            elif level == 3:
                ctx.current_h3 = plain_heading

            if level in (2, 3) and getattr(ctx, "in_section", False):
                blocks.append("</section>")
                ctx.in_section = False

            h_id = ctx.next_id("sec", plain_heading)
            if level in (2, 3):
                blocks.append('<section class="qa-section">')
                ctx.in_section = True
            blocks.append(
                f'<h{level} id="{h_id}">{render_inline(raw_heading)}</h{level}>'
            )
            idx += 1
            continue

        # Pipe table
        if (
            "|" in line
            and idx + 1 < len(lines)
            and is_table_Separator(lines[idx + 1])
        ):
            table_html, idx = parse_table_block(lines, idx, ctx)
            blocks.append(table_html)
            continue

        # List block
        if LIST_ITEM_RE.match(line):
            list_html, idx = parse_list_block(lines, idx, ctx)
            blocks.append(list_html)
            continue

        # Paragraph
        para_lines: list[str] = []
        while idx < len(lines):
            cur = lines[idx]
            cur_stripped = cur.strip()
            if (
                not cur_stripped
                or cur_stripped.startswith("```")
                or HR_RE.match(cur_stripped)
                or HEADING_RE.match(cur)
                or LIST_ITEM_RE.match(cur)
                or (
                    "|" in cur
                    and idx + 1 < len(lines)
                    and is_table_Separator(lines[idx + 1])
                )
            ):
                break
            para_lines.append(cur_stripped)
            idx += 1

        blocks.append(f"<p>{render_inline(' '.join(para_lines))}</p>")

    if getattr(ctx, "in_section", False):
        blocks.append("</section>")
        ctx.in_section = False

    return doc_title, "\n".join(blocks), ctx


def detect_git_revision(repo_dir: pathlib.Path) -> str:
    """Return short git SHA of HEAD if available, else empty string."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return res.stdout.strip()
    except Exception:
        return ""


TOOLBAR_HTML = """\
<div class="qa-toolbar no-print" role="region" aria-label="QA Export Actions ({position})">
  <div class="qa-toolbar-actions">
    <button type="button" class="qa-btn qa-btn-primary" onclick="exportPdf()">
      Export PDF
    </button>
    <button type="button" class="qa-btn qa-btn-accent" onclick="downloadCsvRow(this)">
      Download CSV Row
    </button>
    <button type="button" class="qa-btn qa-btn-secondary" onclick="copyCsvRow(this)">
      Copy CSV Row
    </button>
    <label class="qa-toggle-label" title="Prepend the column header row above the exported data row">
      <input type="checkbox" class="include-headers-toggle" onchange="syncHeaderToggles(this)">
      <span>Include column headers</span>
    </label>
    <button type="button" class="qa-btn qa-btn-danger" onclick="clearQaForm()">
      Clear Form
    </button>
  </div>
  <div class="qa-toolbar-meta">
    <span class="qa-progress-badge" aria-live="polite">{initial_checked} / {total_checks} checks verified</span>
    <span class="qa-status-msg" role="status" aria-live="polite"></span>
  </div>
</div>"""


PAGE_CSS = """\
:root {
  --bg-page: #f5f7fa;
  --bg-card: #ffffff;
  --text-main: #1f2937;
  --text-muted: #4b5563;
  --border-color: #d1d5db;
  --border-subtle: #e5e7eb;
  --primary: #0f4c81;
  --primary-hover: #0b3961;
  --accent: #047857;
  --accent-hover: #065f46;
  --secondary: #2563eb;
  --secondary-hover: #1d4ed8;
  --danger-bg: #fff1f2;
  --danger-text: #be123c;
  --danger-border: #fecdd3;
  --check-bg: #f0fdf4;
  --check-border: #bbf7d0;
}

*, *::before, *::after {
  box-sizing: border-box;
}

html {
  font-size: 16px;
  color: var(--text-main);
  background-color: var(--bg-page);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.55;
}

body {
  margin: 0;
  padding: 24px 16px 48px;
}

.qa-container {
  max-width: 920px;
  margin: 0 auto;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 32px 40px;
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.05);
}

.qa-doc-meta {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-top: -8px;
  margin-bottom: 18px;
}

h1, h2, h3, h4, h5, h6 {
  color: #111827;
  line-height: 1.25;
  margin-top: 1.4em;
  margin-bottom: 0.55em;
}

h1 {
  margin-top: 0;
  font-size: 1.85rem;
  border-bottom: 2px solid var(--primary);
  padding-bottom: 0.4em;
}

h2 {
  font-size: 1.35rem;
  border-bottom: 1px solid var(--border-subtle);
  padding-bottom: 0.25em;
}

h3 {
  font-size: 1.12rem;
  color: var(--primary);
}

p {
  margin: 0.65em 0;
}

a {
  color: var(--secondary);
  text-decoration: underline;
}

code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  font-size: 0.9em;
  background: #f3f4f6;
  padding: 0.15em 0.38em;
  border-radius: 4px;
}

hr {
  border: none;
  border-top: 1px solid var(--border-subtle);
  margin: 1.6em 0;
}

/* Lists */
ul, ol {
  margin: 0.6em 0;
  padding-left: 1.5em;
}

.qa-step-list li {
  margin: 0.35em 0;
}

.qa-meta-list,
.qa-outcome-list {
  list-style: none;
  padding-left: 0;
}

.qa-meta-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin: 0.55em 0;
}

.qa-meta-item.qa-meta-block {
  flex-direction: column;
  align-items: stretch;
}

.qa-meta-label {
  min-width: 220px;
  color: var(--text-main);
}

/* Inputs */
.qa-input {
  font: inherit;
  font-size: 0.95rem;
  color: var(--text-main);
  background: #ffffff;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 6px 10px;
  min-width: 240px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.qa-input:focus {
  outline: none;
  border-color: var(--secondary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}

.qa-input-wide {
  flex: 1 1 360px;
}

.qa-textarea {
  width: 100%;
  min-height: 76px;
  resize: vertical;
}

.qa-table-input {
  width: 100%;
  min-width: 110px;
  padding: 5px 8px;
}

/* Outcome Checkboxes */
.qa-check-item {
  margin: 0.75em 0;
}

.qa-check-label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 8px 14px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  background: #f9fafb;
  user-select: none;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.qa-check-label:hover {
  background: #f3f4f6;
}

.qa-check-label:has(.qa-checkbox:checked) {
  background: var(--check-bg);
  border-color: var(--check-border);
}

.qa-table-check {
  padding: 4px 10px;
  background: transparent;
  border-color: transparent;
}

.qa-table-check:hover {
  background: #f3f4f6;
}

.qa-checkbox {
  width: 1.15rem;
  height: 1.15rem;
  margin: 0;
  accent-color: var(--accent);
  cursor: pointer;
  flex-shrink: 0;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

/* Tables */
.qa-table-wrap {
  overflow-x: auto;
  margin: 0.9em 0;
}

.qa-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.95rem;
}

.qa-table th,
.qa-table td {
  border: 1px solid var(--border-color);
  padding: 8px 12px;
  text-align: left;
  vertical-align: middle;
}

.qa-table thead th {
  background: #f3f4f6;
  font-weight: 600;
  color: #111827;
}

.qa-table tbody tr:nth-child(even) {
  background: #fafafa;
}

/* Action Toolbars */
.qa-toolbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 12px 16px;
  background: #f8fafc;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px 16px;
  margin: 18px 0;
}

.qa-toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.qa-toolbar-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  font-size: 0.9rem;
}

.qa-btn {
  font: inherit;
  font-size: 0.9rem;
  font-weight: 600;
  padding: 8px 14px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.qa-btn-primary {
  background: var(--primary);
  color: #ffffff;
}

.qa-btn-primary:hover {
  background: var(--primary-hover);
}

.qa-btn-accent {
  background: var(--accent);
  color: #ffffff;
}

.qa-btn-accent:hover {
  background: var(--accent-hover);
}

.qa-btn-secondary {
  background: var(--secondary);
  color: #ffffff;
}

.qa-btn-secondary:hover {
  background: var(--secondary-hover);
}

.qa-btn-danger {
  background: var(--danger-bg);
  color: var(--danger-text);
  border-color: var(--danger-border);
}

.qa-btn-danger:hover {
  background: #ffe4e6;
}

.qa-toggle-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.9rem;
  color: var(--text-main);
  cursor: pointer;
  padding: 4px 8px;
  user-select: none;
}

.qa-toggle-label input[type="checkbox"] {
  width: 1rem;
  height: 1rem;
  accent-color: var(--secondary);
  cursor: pointer;
}

.qa-progress-badge {
  background: #e0f2fe;
  color: #075985;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.85rem;
}

.qa-status-msg {
  font-weight: 600;
  color: var(--accent);
}

@media (max-width: 640px) {
  body {
    padding: 10px;
  }
  .qa-container {
    padding: 18px 16px;
  }
  .qa-meta-label {
    min-width: 100%;
  }
  .qa-input {
    width: 100%;
    min-width: 0;
  }
}

/* Dedicated Print / PDF Styles */
@page {
  margin: 0.55in;
}

@media print {
  .no-print {
    display: none !important;
  }

  html, body {
    background: #ffffff !important;
    color: #000000 !important;
    padding: 0 !important;
    margin: 0 !important;
    font-size: 10.5pt;
    line-height: 1.35;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .qa-container {
    max-width: 100% !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    margin: 0 !important;
  }

  h1, h2, h3, h4 {
    break-after: avoid;
    page-break-after: avoid;
    color: #000000 !important;
  }

  p, li {
    orphans: 3;
    widows: 3;
  }

  .qa-section,
  .qa-table-wrap,
  .qa-table,
  .qa-check-item,
  .qa-meta-item {
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .qa-table tr {
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .qa-table th,
  .qa-table td {
    border: 1px solid #333333 !important;
    padding: 5px 8px !important;
  }

  .qa-table thead th {
    background: #eaeaea !important;
  }

  .qa-input {
    border: none !important;
    border-bottom: 1px solid #222222 !important;
    border-radius: 0 !important;
    background: transparent !important;
    padding: 2px 4px !important;
    color: #000000 !important;
  }

  .qa-table-input {
    border-bottom: none !important;
    padding: 0 2px !important;
  }

  .qa-input::placeholder {
    color: transparent !important;
  }

  .qa-textarea {
    border: 1px solid #444444 !important;
    border-radius: 4px !important;
    padding: 6px !important;
    height: auto !important;
    overflow: visible !important;
    white-space: pre-wrap !important;
  }

  .qa-check-label {
    border: 1px solid #555555 !important;
    padding: 4px 8px !important;
  }

  .qa-table-check {
    border: none !important;
    padding: 0 !important;
  }

  .qa-checkbox {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  a {
    color: #000000 !important;
    text-decoration: none !important;
  }
}
"""


PAGE_JS = """\
(function () {
  "use strict";

  function getSortedControls(role) {
    const nodes = Array.from(
      document.querySelectorAll('[data-csv-role="' + role + '"]')
    );
    nodes.sort(function (a, b) {
      const ordA = parseInt(a.getAttribute("data-csv-order") || "0", 10);
      const ordB = parseInt(b.getAttribute("data-csv-order") || "0", 10);
      return ordA - ordB;
    });
    return nodes;
  }

  function escapeCsvCell(value) {
    if (value === null || value === undefined) {
      return "";
    }
    const normalized = String(value).replace(/\\r\\n|\\r|\\n/g, " ").trim();
    if (/[",\\r\\n]/.test(normalized)) {
      return '"' + normalized.replace(/"/g, '""') + '"';
    }
    return normalized;
  }

  function includeHeadersEnabled() {
    const toggle = document.querySelector(".include-headers-toggle");
    return Boolean(toggle && toggle.checked);
  }

  window.buildCsvPayload = function (forceHeaders) {
    const metaControls = getSortedControls("metadata");
    const checkControls = getSortedControls("checkbox");

    const headers = [];
    const values = [];

    metaControls.forEach(function (ctrl) {
      headers.push(ctrl.getAttribute("data-csv-header") || ctrl.id);
      values.push(ctrl.value || "");
    });

    checkControls.forEach(function (ctrl) {
      headers.push(ctrl.getAttribute("data-csv-header") || ctrl.id);
      const checkedVal = ctrl.getAttribute("data-checked-value") || "Pass";
      const uncheckedVal = ctrl.getAttribute("data-unchecked-value") || "Fail";
      values.push(ctrl.checked ? checkedVal : uncheckedVal);
    });

    const dataRow = values.map(escapeCsvCell).join(",");
    const withHeaders =
      typeof forceHeaders === "boolean" ? forceHeaders : includeHeadersEnabled();

    if (withHeaders) {
      const headerRow = headers.map(escapeCsvCell).join(",");
      return headerRow + "\\r\\n" + dataRow;
    }
    return dataRow;
  };

  function showToolbarStatus(triggerEl, message, isError) {
    const toolbars = document.querySelectorAll(".qa-toolbar");
    const targetToolbar = triggerEl ? triggerEl.closest(".qa-toolbar") : null;
    const targets = targetToolbar ? [targetToolbar] : Array.from(toolbars);

    targets.forEach(function (tb) {
      const msgEl = tb.querySelector(".qa-status-msg");
      if (!msgEl) return;
      msgEl.textContent = message;
      msgEl.style.color = isError ? "#be123c" : "#047857";
      if (msgEl._clearTimer) {
        clearTimeout(msgEl._clearTimer);
      }
      msgEl._clearTimer = setTimeout(function () {
        msgEl.textContent = "";
      }, 3500);
    });
  }

  window.syncHeaderToggles = function (sourceToggle) {
    const checked = Boolean(sourceToggle && sourceToggle.checked);
    document.querySelectorAll(".include-headers-toggle").forEach(function (el) {
      el.checked = checked;
    });
  };

  function syncInputsForPrint() {
    document.querySelectorAll("input.qa-input").forEach(function (inp) {
      inp.setAttribute("value", inp.value);
      if (inp.hasAttribute("placeholder")) {
        inp.setAttribute("data-orig-placeholder", inp.getAttribute("placeholder") || "");
        inp.removeAttribute("placeholder");
      }
    });
    document.querySelectorAll("textarea.qa-textarea").forEach(function (ta) {
      ta.style.height = "auto";
      ta.style.height = Math.max(76, ta.scrollHeight + 4) + "px";
      if (ta.hasAttribute("placeholder")) {
        ta.setAttribute("data-orig-placeholder", ta.getAttribute("placeholder") || "");
        ta.removeAttribute("placeholder");
      }
    });
    document.querySelectorAll("input.qa-checkbox").forEach(function (cb) {
      if (cb.checked) {
        cb.setAttribute("checked", "checked");
      } else {
        cb.removeAttribute("checked");
      }
    });
  }

  function restoreInputsAfterPrint() {
    document.querySelectorAll("[data-orig-placeholder]").forEach(function (el) {
      el.setAttribute("placeholder", el.getAttribute("data-orig-placeholder") || "");
      el.removeAttribute("data-orig-placeholder");
    });
  }

  window.exportPdf = function () {
    syncInputsForPrint();
    window.print();
    restoreInputsAfterPrint();
  };

  function getSerialFilenameSlug() {
    const serialInput = document.querySelector(
      '[data-csv-header="Board Serial Number"]'
    );
    const raw = serialInput && serialInput.value ? serialInput.value.trim() : "";
    if (raw) {
      const clean = raw.replace(/[^A-Za-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "");
      if (clean) return clean;
    }
    return new Date().toISOString().slice(0, 10);
  }

  window.downloadCsvRow = function (btnEl) {
    const csvText = window.buildCsvPayload();
    const filename = "QA_Results_" + getSerialFilenameSlug() + ".csv";
    const blob = new Blob([csvText + "\\r\\n"], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
    showToolbarStatus(btnEl, "Downloaded " + filename, false);
  };

  window.copyCsvRow = function (btnEl) {
    const csvText = window.buildCsvPayload();

    function fallbackCopy() {
      const temp = document.createElement("textarea");
      temp.value = csvText;
      temp.setAttribute("readonly", "");
      temp.style.position = "fixed";
      temp.style.left = "-9999px";
      document.body.appendChild(temp);
      temp.select();
      try {
        const ok = document.execCommand("copy");
        if (ok) {
          showToolbarStatus(btnEl, "Copied CSV row to clipboard!", false);
        } else {
          showToolbarStatus(btnEl, "Clipboard copy blocked by browser.", true);
        }
      } catch (err) {
        showToolbarStatus(btnEl, "Copy failed: " + err, true);
      }
      document.body.removeChild(temp);
    }

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard
        .writeText(csvText)
        .then(function () {
          showToolbarStatus(btnEl, "Copied CSV row to clipboard!", false);
        })
        .catch(fallbackCopy);
    } else {
      fallbackCopy();
    }
  };

  window.clearQaForm = function () {
    const form = document.getElementById("qa-form");
    if (!form) return;
    const hasData = Array.from(
      form.querySelectorAll("input.qa-input, textarea.qa-textarea, input.qa-checkbox")
    ).some(function (el) {
      return el.type === "checkbox" ? el.checked : Boolean(el.value);
    });
    if (hasData && !window.confirm("Clear all entered QA measurements and checkboxes?")) {
      return;
    }
    form.reset();
    document.querySelectorAll("input.qa-input").forEach(function (inp) {
      inp.value = "";
      inp.removeAttribute("value");
    });
    document.querySelectorAll("textarea.qa-textarea").forEach(function (ta) {
      ta.value = "";
      ta.style.height = "";
    });
    document.querySelectorAll("input.qa-checkbox").forEach(function (cb) {
      cb.checked = false;
      cb.removeAttribute("checked");
    });
    updateProgressBadges();
    showToolbarStatus(null, "Form cleared.", false);
  };

  function updateProgressBadges() {
    const boxes = getSortedControls("checkbox");
    const total = boxes.length;
    const checked = boxes.filter(function (cb) {
      return cb.checked;
    }).length;
    document.querySelectorAll(".qa-progress-badge").forEach(function (badge) {
      badge.textContent = checked + " / " + total + " checks verified";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    updateProgressBadges();
    document.querySelectorAll("input.qa-checkbox").forEach(function (cb) {
      cb.addEventListener("change", updateProgressBadges);
    });
    document.querySelectorAll("textarea.qa-textarea").forEach(function (ta) {
      ta.addEventListener("input", function () {
        ta.style.height = "auto";
        ta.style.height = Math.max(76, ta.scrollHeight + 4) + "px";
      });
    });
    window.addEventListener("beforeprint", syncInputsForPrint);
    window.addEventListener("afterprint", restoreInputsAfterPrint);
  });
})();
"""


def build_full_html(md_text: str, source_name: str = "QA.md", git_rev: str = "") -> str:
    """Validate Markdown and assemble the complete self-contained QA.html document."""
    validate_markdown(md_text, source_name=source_name)
    doc_title, body_html, ctx = convert_markdown_body(md_text)

    total_checks = len(ctx.checkbox_headers)
    initial_checked = body_html.count('class="qa-checkbox" checked')

    top_toolbar = TOOLBAR_HTML.format(
        position="Top",
        initial_checked=initial_checked,
        total_checks=total_checks,
    )
    bottom_toolbar = TOOLBAR_HTML.format(
        position="Bottom",
        initial_checked=initial_checked,
        total_checks=total_checks,
    )

    rev_note = (
        f'<div class="qa-doc-meta">Generated from <code>documentation/QA.md</code>'
        f' &middot; Commit <code>{html.escape(git_rev)}</code></div>'
        if git_rev
        else '<div class="qa-doc-meta">Generated from <code>documentation/QA.md</code></div>'
    )

    # Insert revision note and top toolbar immediately after <h1> if present
    h1_close = "</h1>"
    if h1_close in body_html:
        first_h1_end = body_html.index(h1_close) + len(h1_close)
        body_with_top = (
            body_html[:first_h1_end]
            + "\n"
            + rev_note
            + "\n"
            + top_toolbar
            + body_html[first_h1_end:]
        )
    else:
        body_with_top = rev_note + "\n" + top_toolbar + "\n" + body_html

    esc_title = html.escape(doc_title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc_title}</title>
  <style>
{PAGE_CSS}  </style>
</head>
<body>
  <main class="qa-container">
    <form id="qa-form" onsubmit="return false;" autocomplete="off">
{body_with_top}
{bottom_toolbar}
    </form>
  </main>
  <script>
{PAGE_JS}  </script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    default_input = repo_root / "documentation" / "QA.md"
    default_output = repo_root / "documentation" / "QA.html"

    parser = argparse.ArgumentParser(
        description="Convert clean documentation/QA.md into an interactive QA.html page."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=pathlib.Path,
        default=default_input,
        help="Path to clean Markdown QA procedure (default: documentation/QA.md)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=pathlib.Path,
        default=default_output,
        help="Output path for generated HTML (default: documentation/QA.html)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate QA.md and test conversion without writing an output file.",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    md_text = args.input.read_text(encoding="utf-8")
    git_rev = detect_git_revision(args.input.resolve().parent)

    try:
        full_html = build_full_html(
            md_text, source_name=str(args.input), git_rev=git_rev
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.check_only:
        print(f"Validated {args.input} successfully.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(full_html, encoding="utf-8")
    print(f"Generated {args.output} from {args.input}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
