#!/usr/bin/env python3
# Convert clean documentation/QA.md into a simple interactive QA.html page.

import argparse, html, pathlib, re, sys

TAG_RE = re.compile(r"<(?:/?[A-Za-z!][^>]*)>")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
HR_RE = re.compile(r"^(?:[-*_]\s*){3,}$")
LIST_RE = re.compile(r"^([ \t]*)([-*+]|\d+\.)\s+(.*)$")
CHECK_RE = re.compile(r"^\[([ xX])\]\s+(.+?)\s*$")
CELL_CHECK_RE = re.compile(r"^(.*?)\[([ xX])\]\s*(.*)$")
META_RE = re.compile(r"^\*\*([^*]+?):\*\*\s*$")
CH_RE = re.compile(r"\bCh(?:annel)?\s*(\d+)\b", re.I)

FILLABLE_COLS = ("measured", "notes", "variance", "reading", "observed", "value", "comment")
GENERIC_LABELS = {"notes", "notes / defects", "git revision / commit used", "comments"}

TOOLBAR_HTML = """<div class="toolbar no-print">
  <button type="button" onclick="exportPdf()">Export PDF</button>
  <button type="button" onclick="downloadCsvRow()">Download CSV Row</button>
  <button type="button" onclick="copyCsvRow()">Copy CSV Row</button>
  <label><input type="checkbox" class="include-headers-toggle" onchange="syncToggles(this)"> Include column headers</label>
  <button type="button" onclick="clearForm()">Clear Form</button>
  <a href="./">Back</a>
  <span class="status-msg"></span>
</div>"""

PAGE_CSS = """
body { font-family: sans-serif; max-width: 850px; margin: 20px auto; padding: 0 15px; line-height: 1.4; color: #000; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; }
th, td { border: 1px solid #888; padding: 6px 8px; text-align: left; }
th { background: #eee; }
textarea { width: 100%; box-sizing: border-box; margin-top: 4px; }
td input[type="text"] { width: 95%; }
.no-bullets { list-style: none; padding-left: 0; }
.toolbar { margin: 15px 0; padding: 8px; border: 1px solid #ccc; background: #f5f5f5; }
.toolbar button, .toolbar label, .toolbar a { margin-right: 8px; }
@media print {
  .no-print { display: none !important; }
  body { max-width: 100%; margin: 0; padding: 0; font-size: 10.5pt; }
  h1, h2, h3 { page-break-after: avoid; break-after: avoid; }
  table, tr { page-break-inside: avoid; break-inside: avoid; }
  input[type="text"], input[type="date"] { border: none; border-bottom: 1px solid #000; background: transparent; }
  td input[type="text"] { border: none; }
}
"""

PAGE_JS = """
function byOrder(role) {
  return [...document.querySelectorAll('[data-csv-role="' + role + '"]')]
    .sort((a, b) => (+a.dataset.csvOrder || 0) - (+b.dataset.csvOrder || 0));
}

function csvCell(val) {
  const s = String(val ?? "").replace(/\\r\\n|\\r|\\n/g, " ").trim();
  return /[",\\r\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function buildCsvPayload(forceHeaders) {
  const meta = byOrder("metadata"), checks = byOrder("checkbox");
  const headers = [...meta, ...checks].map(el => el.dataset.csvHeader);
  const values = [
    ...meta.map(el => el.value || ""),
    ...checks.map(el => el.checked ? el.dataset.checkedValue : el.dataset.uncheckedValue)
  ];
  const row = values.map(csvCell).join(",");
  const inc = typeof forceHeaders === "boolean" ? forceHeaders : Boolean(document.querySelector(".include-headers-toggle")?.checked);
  return inc ? headers.map(csvCell).join(",") + "\\r\\n" + row : row;
}

function setStatus(msg) {
  document.querySelectorAll(".status-msg").forEach(el => {
    el.textContent = msg;
    setTimeout(() => { el.textContent = ""; }, 3000);
  });
}

function syncToggles(src) {
  document.querySelectorAll(".include-headers-toggle").forEach(el => { el.checked = src.checked; });
}

function exportPdf() {
  document.querySelectorAll('input[type="text"], input[type="date"]').forEach(el => el.setAttribute("value", el.value));
  document.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked ? cb.setAttribute("checked", "checked") : cb.removeAttribute("checked"));
  window.print();
}

function downloadCsvRow() {
  const sn = (document.querySelector('[data-csv-header="Board Serial Number"]')?.value || "").trim().replace(/[^A-Za-z0-9_-]+/g, "_");
  const name = "QA_Results_" + (sn || "export") + ".csv";
  const url = URL.createObjectURL(new Blob([buildCsvPayload() + "\\r\\n"], { type: "text/csv;charset=utf-8;" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
  setStatus("Downloaded " + name);
}

function copyCsvRow() {
  const text = buildCsvPayload();
  const fallback = () => {
    const ta = Object.assign(document.createElement("textarea"), { value: text });
    ta.style.cssText = "position:fixed;left:-9999px";
    document.body.appendChild(ta); ta.select();
    document.execCommand("copy"); ta.remove();
    setStatus("Copied!");
  };
  (navigator.clipboard && window.isSecureContext)
    ? navigator.clipboard.writeText(text).then(() => setStatus("Copied!")).catch(fallback)
    : fallback();
}

function clearForm() {
  document.getElementById("qa-form").reset();
  document.querySelectorAll('input[type="text"], input[type="date"], textarea').forEach(el => { el.value = ""; el.removeAttribute("value"); });
  document.querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = false; cb.removeAttribute("checked"); });
  setStatus("Cleared.");
}
"""


# Strip inline Markdown markers to plain text.
def plain_text(text: str) -> str:
    s = re.sub(r"`([^`]+)`|\[([^\]]+)\]\([^)]+\)", lambda m: m.group(1) or m.group(2), text)
    return " ".join(re.sub(r"(\*\*|__|\*|_)(.+?)\1", r"\2", s).split())


# Render inline Markdown (code, links, bold, italic) to HTML.
def render_inline(text: str) -> str:
    s = html.escape(text, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)


# Split a Markdown pipe-table row into trimmed cells.
def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


# Check if a line is a Markdown table alignment separator.
def is_sep_row(line: str) -> bool:
    cells = split_row(line) if "|" in line else []
    return bool(cells) and all(re.match(r"^:?-{2,}:?$", c) for c in cells)


# Verify QA.md has zero raw HTML tags and checkboxes only on Pass/Complete items.
def validate_markdown(md_text: str, source_name: str = "QA.md") -> None:
    in_fence, errors = False, []
    for n, line in enumerate(md_text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if m := TAG_RE.search(line):
            errors.append(f"{source_name}:{n}: Raw HTML found: {m.group(0)!r}")
        if (lm := LIST_RE.match(line)) and (cm := CHECK_RE.match(lm.group(3))):
            if not re.search(r"\b(pass|complete)\b", plain_text(cm.group(2)), re.I):
                errors.append(f"{source_name}:{n}: Checkbox on non-Pass/Complete item: {cm.group(2)!r}")
        elif "|" in line and not is_sep_row(line):
            for cell in split_row(line):
                if (cm := CELL_CHECK_RE.match(cell)) and not re.search(r"\b(pass|complete)\b", plain_text(f"{cm.group(1)} {cm.group(3)}"), re.I):
                    errors.append(f"{source_name}:{n}: Table checkbox on non-Pass/Complete cell: {cell!r}")
    if errors:
        raise ValueError("Markdown validation failed:\n  - " + "\n  - ".join(errors))


# Convert validated Markdown into (title, html_body).
def convert_markdown(md_text: str) -> tuple[str, str]:
    lines = md_text.splitlines()
    order, cur_h3, title, in_fence = 0, "", "QA Procedure", False
    blocks, fence = [], []

    def next_ord() -> int:
        nonlocal order
        order += 1
        return order * 100

    def pair_for(label: str) -> tuple[str, str]:
        low = label.lower()
        return ("Complete", "Incomplete") if ("complete" in low and "pass" not in low) else ("Pass", "Fail")

    # Render a single list item as a checkbox, metadata input, or plain procedural step.
    def make_li(rest: str) -> tuple[str, str]:
        if cm := CHECK_RE.match(rest):
            plain = plain_text(cm.group(2))
            t_val, f_val = pair_for(plain)
            chk = " checked" if cm.group(1).lower() == "x" else ""
            return "no-bullets", f'<li><label><input type="checkbox"{chk} data-csv-role="checkbox" data-csv-header="{html.escape(plain, True)}" data-checked-value="{t_val}" data-unchecked-value="{f_val}" data-csv-order="{next_ord()}"> {render_inline(cm.group(2))}</label></li>'
        if mm := META_RE.match(rest):
            clean = plain_text(mm.group(1)).rstrip(":").strip()
            low = clean.lower()
            hdr = f"{cur_h3} - {clean}" if (low in GENERIC_LABELS and cur_h3 and cur_h3.lower() not in {"qa metadata", "final result"}) else clean
            attrs = f'data-csv-role="metadata" data-csv-header="{html.escape(hdr, True)}" data-csv-order="{next_ord()}"'
            if "date" in low:
                return "no-bullets", f'<li><strong>{html.escape(clean)}:</strong> <input type="date" {attrs}></li>'
            if any(k in low for k in ("deviations", "waivers", "comments")):
                return "no-bullets", f'<li><strong>{html.escape(clean)}:</strong><br><textarea rows="3" {attrs}></textarea></li>'
            return "no-bullets", f'<li><strong>{html.escape(clean)}:</strong> <input type="text" {attrs}></li>'
        return "", f"<li>{render_inline(rest)}</li>"

    idx = 0
    while idx < len(lines):
        line, stripped = lines[idx], lines[idx].strip()
        if stripped.startswith("```"):
            if in_fence:
                blocks.append(f"<pre><code>{html.escape(chr(10).join(fence))}</code></pre>")
                fence.clear()
            in_fence = not in_fence
            idx += 1
        elif in_fence:
            fence.append(line)
            idx += 1
        elif not stripped:
            idx += 1
        elif HR_RE.match(stripped):
            blocks.append("<hr>")
            idx += 1
        elif hm := HEAD_RE.match(line):
            lvl, h_raw = len(hm.group(1)), hm.group(2)
            if lvl == 1 and title == "QA Procedure":
                title = plain_text(h_raw)
            elif lvl in (2, 3):
                cur_h3 = plain_text(h_raw) if lvl == 3 else ""
            blocks.append(f"<h{lvl}>{render_inline(h_raw)}</h{lvl}>")
            idx += 1
        elif "|" in line and idx + 1 < len(lines) and is_sep_row(lines[idx + 1]):
            headers = split_row(lines[idx])
            idx += 2
            rows = []
            while idx < len(lines) and lines[idx].strip() and "|" in lines[idx]:
                rows.append(split_row(lines[idx]))
                idx += 1
            base_ord = next_ord()
            has_ch = any(CH_RE.search(c) for r in rows for c in r if CELL_CHECK_RE.match(c))
            if has_ch:
                order += len(rows) * max(1, len(headers))
            tbl = ["<table><thead><tr>" + "".join(f"<th>{render_inline(h)}</th>" for h in headers) + "</tr></thead><tbody>"]
            for row in rows:
                rkey = plain_text(row[0]) if row else ""
                tds = []
                for c, h_raw in enumerate(headers):
                    raw, col_h = (row[c] if c < len(row) else ""), plain_text(h_raw)
                    if cm := CELL_CHECK_RE.match(raw):
                        pre, suf = cm.group(1).strip(), cm.group(3).strip()
                        pre_p, suf_p = plain_text(pre).rstrip(":").strip(), plain_text(suf).strip()
                        csv_h = f"{rkey} {suf_p}".strip() if (not pre_p and rkey and c > 0) else " ".join(x for x in (pre_p, suf_p) if x)
                        ch_m = CH_RE.search(csv_h)
                        ord_v = (base_ord + int(ch_m.group(1))) if (has_ch and ch_m) else next_ord()
                        t_val, f_val = pair_for(csv_h)
                        chk = " checked" if cm.group(2).lower() == "x" else ""
                        pre_h = f"{render_inline(pre)} " if pre else ""
                        suf_h = f" {render_inline(suf)}" if suf else ""
                        tds.append(f'<td><label>{pre_h}<input type="checkbox"{chk} data-csv-role="checkbox" data-csv-header="{html.escape(csv_h, True)}" data-checked-value="{t_val}" data-unchecked-value="{f_val}" data-csv-order="{ord_v}">{suf_h}</label></td>')
                    elif not raw and any(k in col_h.lower() for k in FILLABLE_COLS):
                        tds.append('<td><input type="text"></td>')
                    else:
                        tds.append(f"<td>{render_inline(raw)}</td>")
                tbl.append("<tr>" + "".join(tds) + "</tr>")
            tbl.append("</tbody></table>")
            blocks.append("\n".join(tbl))
        elif LIST_RE.match(line):
            groups = []
            while idx < len(lines) and lines[idx].strip() and (lm := LIST_RE.match(lines[idx])):
                ind, marker, rest = len(lm.group(1).expandtabs(4)), lm.group(2), lm.group(3)
                idx += 1
                if ind > 0 and groups and groups[-1][2]:
                    sub = [f"<li>{render_inline(rest)}</li>"]
                    while idx < len(lines) and lines[idx].strip() and (sm := LIST_RE.match(lines[idx])) and len(sm.group(1).expandtabs(4)) > 0:
                        sub.append(f"<li>{render_inline(sm.group(3))}</li>")
                        idx += 1
                    groups[-1][2][-1] = groups[-1][2][-1][:-5] + f"<ul>{''.join(sub)}</ul></li>"
                else:
                    tag = "ol" if marker.endswith(".") else "ul"
                    cls, li_html = make_li(rest)
                    if not groups or groups[-1][0] != tag or groups[-1][1] != cls:
                        groups.append((tag, cls, []))
                    groups[-1][2].append(li_html)
            for tag, cls, items in groups:
                cls_attr = f' class="{cls}"' if cls else ""
                blocks.append(f"<{tag}{cls_attr}>\n" + "\n".join(items) + f"\n</{tag}>")
        else:
            para = []
            while idx < len(lines):
                cur, cs = lines[idx], lines[idx].strip()
                if not cs or cs.startswith("```") or HR_RE.match(cs) or HEAD_RE.match(cur) or LIST_RE.match(cur) or ("|" in cur and idx + 1 < len(lines) and is_sep_row(lines[idx + 1])):
                    break
                para.append(cs)
                idx += 1
            blocks.append(f"<p>{render_inline(' '.join(para))}</p>")

    return title, "\n".join(blocks)


# Build the standalone QA.html document.
def build_full_html(md_text: str, source_name: str = "QA.md") -> str:
    validate_markdown(md_text, source_name=source_name)
    title, body = convert_markdown(md_text)
    body = body.replace("</h1>", f"</h1>\n{TOOLBAR_HTML}", 1) if "</h1>" in body else f"{TOOLBAR_HTML}\n{body}"
    return f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>{html.escape(title)}</title>\n<style>{PAGE_CSS}</style>\n</head>\n<body>\n<form id="qa-form" onsubmit="return false;">\n{body}\n{TOOLBAR_HTML}\n</form>\n<script>{PAGE_JS}</script>\n</body>\n</html>\n'


# Add a QA Procedure link to the #theSideNav sidebar in KiBot navigation pages.
def inject_kibot_navigation(nav_dir: pathlib.Path, qa_href: str = "QA.html") -> int:
    if not nav_dir.is_dir():
        return 0
    href = html.escape(qa_href, True)
    nav_li = f'  <li style="margin-top: 14px;"><a href="{href}">QA Procedure</a></li>\n'
    count = 0
    for path in sorted(nav_dir.glob("*-navigate*.html")):
        src = path.read_text(encoding="utf-8")
        if f'href="{href}"' in src:
            continue
        if (sm := re.search(r'<div\s+id="theSideNav"[^>]*>', src)) and (end := src.find("</div>", sm.end())) != -1:
            if (pos := src.rfind("</ul>", sm.start(), end)) != -1:
                path.write_text(src[:pos] + nav_li + src[pos:], encoding="utf-8")
                count += 1
    return count


# CLI entry point.
def main(argv: list[str] | None = None) -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Generate QA.html from QA.md.")
    ap.add_argument("input", nargs="?", type=pathlib.Path, default=root / "documentation" / "QA.md")
    ap.add_argument("-o", "--output", type=pathlib.Path, default=root / "documentation" / "QA.html")
    ap.add_argument("--inject-nav", type=pathlib.Path, default=None)
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args(argv)

    if not args.input.is_file():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    try:
        full_html = build_full_html(args.input.read_text(encoding="utf-8"), str(args.input))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.check_only:
        print(f"Validated {args.input} successfully.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(full_html, encoding="utf-8")
    print(f"Generated {args.output} from {args.input}")

    if args.inject_nav is not None:
        rel = args.output.resolve().relative_to(args.inject_nav.resolve()).as_posix() if args.inject_nav.resolve() in args.output.resolve().parents else args.output.name
        print(f"Injected QA sidebar link into {inject_kibot_navigation(args.inject_nav, rel)} KiBot page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
