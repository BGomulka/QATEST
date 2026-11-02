#!/usr/bin/env python3
# Convert documentation/QA.md into a self-contained interactive QA.html page.

import argparse, html, pathlib, re, subprocess, sys

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
HINTS = [
    ("serial", "e.g., SN-1042"),
    ("pcb revision", "e.g., Rev 1.0"),
    ("performed by", "Inspector Name"),
    ("commit", "e.g., a1b2c3d"),
    ("git", "e.g., a1b2c3d"),
    ("notes", "None / describe any observations..."),
    ("deviations", "Record any deviations, waivers, or comments..."),
]

KIBOT_QA_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256" role="img" aria-label="QA Procedure">'
    '<rect x="38" y="28" width="180" height="208" rx="18" fill="#f8fafc" stroke="#0e4e8e" stroke-width="10"/>'
    '<rect x="86" y="14" width="84" height="30" rx="10" fill="#0e4e8e"/><circle cx="128" cy="29" r="5" fill="#fff"/>'
    '<rect x="66" y="76" width="28" height="28" rx="6" fill="#ecfdf5" stroke="#047857" stroke-width="5"/>'
    '<path d="M72 90l7 7 12-14" fill="none" stroke="#047857" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
    '<rect x="110" y="84" width="80" height="12" rx="6" fill="#0e4e8e"/>'
    '<rect x="66" y="124" width="28" height="28" rx="6" fill="#ecfdf5" stroke="#047857" stroke-width="5"/>'
    '<path d="M72 138l7 7 12-14" fill="none" stroke="#047857" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
    '<rect x="110" y="132" width="80" height="12" rx="6" fill="#0e4e8e"/>'
    '<rect x="66" y="172" width="28" height="28" rx="6" fill="#ecfdf5" stroke="#047857" stroke-width="5"/>'
    '<path d="M72 186l7 7 12-14" fill="none" stroke="#047857" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
    '<rect x="110" y="180" width="60" height="12" rx="6" fill="#0e4e8e"/></svg>'
)

TOOLBAR_HTML = """<div class="qa-toolbar no-print" role="region" aria-label="QA Export Actions ({pos})">
  <div class="qa-toolbar-actions">
    <button type="button" class="qa-btn qa-btn-primary" onclick="exportPdf()">Export PDF</button>
    <button type="button" class="qa-btn qa-btn-accent" onclick="downloadCsvRow(this)">Download CSV Row</button>
    <button type="button" class="qa-btn qa-btn-secondary" onclick="copyCsvRow(this)">Copy CSV Row</button>
    <label class="qa-toggle-label"><input type="checkbox" class="include-headers-toggle" onchange="syncHeaderToggles(this)"><span>Include column headers</span></label>
    <button type="button" class="qa-btn qa-btn-danger" onclick="clearQaForm()">Clear Form</button>
  </div>
  <div class="qa-toolbar-meta">
    <span class="qa-progress-badge" aria-live="polite">{checked} / {total} checks verified</span>
    <span class="qa-status-msg" role="status" aria-live="polite"></span>
  </div>
</div>"""

PAGE_CSS = """
:root { --primary: #0f4c81; --accent: #047857; --secondary: #2563eb; --border: #d1d5db; }
*, *::before, *::after { box-sizing: border-box; }
html { font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; color: #1f2937; background: #f5f7fa; }
body { margin: 0; padding: 24px 16px 48px; }
.qa-container { max-width: 920px; margin: 0 auto; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 32px 40px; box-shadow: 0 2px 10px rgba(15,23,42,.05); }
.qa-doc-meta { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px 16px; font-size: .85rem; color: #4b5563; margin: -8px 0 18px; }
.qa-back-link { font-weight: 600; color: var(--primary); text-decoration: none; }
h1, h2, h3 { color: #111827; line-height: 1.25; margin: 1.4em 0 .55em; }
h1 { margin-top: 0; font-size: 1.85rem; border-bottom: 2px solid var(--primary); padding-bottom: .4em; }
h2 { font-size: 1.35rem; border-bottom: 1px solid #e5e7eb; padding-bottom: .25em; }
h3 { font-size: 1.12rem; color: var(--primary); }
p { margin: .65em 0; }
a { color: var(--secondary); }
code { font: .9em ui-monospace, Menlo, Consolas, monospace; background: #f3f4f6; padding: .15em .38em; border-radius: 4px; }
hr { border: 0; border-top: 1px solid #e5e7eb; margin: 1.6em 0; }
ul, ol { margin: .6em 0; padding-left: 1.5em; }
.qa-step-list li { margin: .35em 0; }
.qa-meta-list, .qa-outcome-list { list-style: none; padding-left: 0; }
.qa-meta-item { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin: .55em 0; }
.qa-meta-item.qa-meta-block { flex-direction: column; align-items: stretch; }
.qa-meta-label { min-width: 220px; }
.qa-input { font: inherit; font-size: .95rem; color: #1f2937; background: #fff; border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; min-width: 240px; }
.qa-input-wide { flex: 1 1 360px; }
.qa-textarea { width: 100%; min-height: 76px; resize: vertical; }
.qa-table-input { width: 100%; min-width: 110px; padding: 5px 8px; }
.qa-check-item { margin: .75em 0; }
.qa-check-label { display: inline-flex; align-items: center; gap: 10px; cursor: pointer; padding: 8px 14px; border-radius: 6px; border: 1px solid var(--border); background: #f9fafb; user-select: none; }
.qa-check-label:has(.qa-checkbox:checked) { background: #f0fdf4; border-color: #bbf7d0; }
.qa-table-check { padding: 4px 10px; background: transparent; border-color: transparent; }
.qa-checkbox { width: 1.15rem; height: 1.15rem; margin: 0; accent-color: var(--accent); cursor: pointer; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.qa-table-wrap { overflow-x: auto; margin: .9em 0; }
.qa-table { width: 100%; border-collapse: collapse; font-size: .95rem; }
.qa-table th, .qa-table td { border: 1px solid var(--border); padding: 8px 12px; text-align: left; vertical-align: middle; }
.qa-table thead th { background: #f3f4f6; font-weight: 600; }
.qa-table tbody tr:nth-child(even) { background: #fafafa; }
.qa-toolbar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px 16px; background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; margin: 18px 0; }
.qa-toolbar-actions, .qa-toolbar-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.qa-btn { font: 600 .9rem inherit; padding: 8px 14px; border-radius: 6px; border: 1px solid transparent; cursor: pointer; color: #fff; }
.qa-btn-primary { background: var(--primary); }
.qa-btn-accent { background: var(--accent); }
.qa-btn-secondary { background: var(--secondary); }
.qa-btn-danger { background: #fff1f2; color: #be123c; border-color: #fecdd3; }
.qa-toggle-label { display: inline-flex; align-items: center; gap: 6px; font-size: .9rem; cursor: pointer; user-select: none; }
.qa-progress-badge { background: #e0f2fe; color: #075985; font-weight: 600; padding: 4px 10px; border-radius: 999px; font-size: .85rem; }
.qa-status-msg { font-weight: 600; color: var(--accent); font-size: .9rem; }
@media (max-width: 640px) { body { padding: 10px; } .qa-container { padding: 18px 16px; } .qa-meta-label, .qa-input { width: 100%; min-width: 0; } }
@page { margin: 0.55in; }
@media print {
  .no-print { display: none !important; }
  html, body { background: #fff !important; color: #000 !important; padding: 0 !important; margin: 0 !important; font-size: 10.5pt; line-height: 1.35; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .qa-container { max-width: 100% !important; border: 0 !important; box-shadow: none !important; padding: 0 !important; }
  h1, h2, h3, h4 { break-after: avoid; color: #000 !important; }
  .qa-section, .qa-table-wrap, .qa-table, .qa-table tr, .qa-check-item, .qa-meta-item { break-inside: avoid; }
  .qa-table th, .qa-table td { border: 1px solid #333 !important; padding: 5px 8px !important; }
  .qa-table thead th { background: #eaeaea !important; }
  .qa-input { border: 0 !important; border-bottom: 1px solid #222 !important; border-radius: 0 !important; background: transparent !important; padding: 2px 4px !important; color: #000 !important; }
  .qa-table-input { border-bottom: 0 !important; padding: 0 2px !important; }
  .qa-textarea { border: 1px solid #444 !important; border-radius: 4px !important; padding: 6px !important; height: auto !important; overflow: visible !important; white-space: pre-wrap !important; }
  .qa-check-label { border: 1px solid #555 !important; padding: 4px 8px !important; }
  .qa-table-check { border: 0 !important; padding: 0 !important; }
  a { color: #000 !important; text-decoration: none !important; }
}
"""

PAGE_JS = """
(function () {
  const byOrder = r => [...document.querySelectorAll('[data-csv-role="' + r + '"]')].sort((a, b) => (+a.dataset.csvOrder || 0) - (+b.dataset.csvOrder || 0));
  const csvCell = v => { const s = String(v ?? "").replace(/\\r\\n|\\r|\\n/g, " ").trim(); return /[",\\r\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };

  window.buildCsvPayload = force => {
    const meta = byOrder("metadata"), checks = byOrder("checkbox");
    const headers = [...meta, ...checks].map(el => el.dataset.csvHeader || el.id);
    const vals = [...meta.map(el => el.value || ""), ...checks.map(el => el.checked ? (el.dataset.checkedValue || "Pass") : (el.dataset.uncheckedValue || "Fail"))];
    const row = vals.map(csvCell).join(",");
    const inc = typeof force === "boolean" ? force : Boolean(document.querySelector(".include-headers-toggle")?.checked);
    return inc ? headers.map(csvCell).join(",") + "\\r\\n" + row : row;
  };

  function flash(btn, msg, err) {
    (btn?.closest(".qa-toolbar") ? [btn.closest(".qa-toolbar")] : [...document.querySelectorAll(".qa-toolbar")]).forEach(tb => {
      const el = tb.querySelector(".qa-status-msg");
      if (!el) return;
      el.textContent = msg; el.style.color = err ? "#be123c" : "#047857";
      clearTimeout(el._t); el._t = setTimeout(() => { el.textContent = ""; }, 3500);
    });
  }

  window.syncHeaderToggles = src => document.querySelectorAll(".include-headers-toggle").forEach(el => { el.checked = Boolean(src?.checked); });

  function syncPrint() {
    document.querySelectorAll("input.qa-input, textarea.qa-textarea").forEach(el => {
      if (el.tagName === "INPUT") el.setAttribute("value", el.value);
      else { el.style.height = "auto"; el.style.height = Math.max(76, el.scrollHeight + 4) + "px"; }
      if (el.hasAttribute("placeholder")) { el.dataset.origPh = el.getAttribute("placeholder") || ""; el.removeAttribute("placeholder"); }
    });
    document.querySelectorAll("input.qa-checkbox").forEach(cb => cb.checked ? cb.setAttribute("checked", "checked") : cb.removeAttribute("checked"));
  }
  function restorePrint() { document.querySelectorAll("[data-orig-ph]").forEach(el => { el.setAttribute("placeholder", el.dataset.origPh || ""); delete el.dataset.origPh; }); }

  window.exportPdf = () => { syncPrint(); window.print(); restorePrint(); };

  window.downloadCsvRow = btn => {
    const sn = (document.querySelector('[data-csv-header="Board Serial Number"]')?.value || "").trim().replace(/[^A-Za-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "");
    const name = "QA_Results_" + (sn || new Date().toISOString().slice(0, 10)) + ".csv";
    const url = URL.createObjectURL(new Blob([window.buildCsvPayload() + "\\r\\n"], { type: "text/csv;charset=utf-8;" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    flash(btn, "Downloaded " + name, false);
  };

  window.copyCsvRow = btn => {
    const text = window.buildCsvPayload();
    const fallback = () => {
      const ta = Object.assign(document.createElement("textarea"), { value: text });
      ta.style.cssText = "position:fixed;left:-9999px"; document.body.appendChild(ta); ta.select();
      try { flash(btn, document.execCommand("copy") ? "Copied CSV row to clipboard!" : "Copy blocked.", false); } catch (e) { flash(btn, "Copy failed: " + e, true); }
      ta.remove();
    };
    (navigator.clipboard && window.isSecureContext) ? navigator.clipboard.writeText(text).then(() => flash(btn, "Copied CSV row to clipboard!", false)).catch(fallback) : fallback();
  };

  window.clearQaForm = () => {
    const form = document.getElementById("qa-form");
    if ([...form.querySelectorAll("input.qa-input, textarea.qa-textarea, input.qa-checkbox")].some(el => el.type === "checkbox" ? el.checked : Boolean(el.value)) && !window.confirm("Clear all entered QA measurements and checkboxes?")) return;
    form.reset();
    document.querySelectorAll("input.qa-input, textarea.qa-textarea").forEach(el => { el.value = ""; el.removeAttribute("value"); el.style.height = ""; });
    document.querySelectorAll("input.qa-checkbox").forEach(cb => { cb.checked = false; cb.removeAttribute("checked"); });
    updateProgress(); flash(null, "Form cleared.", false);
  };

  function updateProgress() {
    const boxes = byOrder("checkbox"), done = boxes.filter(cb => cb.checked).length;
    document.querySelectorAll(".qa-progress-badge").forEach(b => { b.textContent = done + " / " + boxes.length + " checks verified"; });
  }

  document.addEventListener("DOMContentLoaded", () => {
    updateProgress();
    document.querySelectorAll("input.qa-checkbox").forEach(cb => cb.addEventListener("change", updateProgress));
    document.querySelectorAll("textarea.qa-textarea").forEach(ta => ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = Math.max(76, ta.scrollHeight + 4) + "px"; }));
    window.addEventListener("beforeprint", syncPrint);
    window.addEventListener("afterprint", restorePrint);
  });
})();
"""


# Strip inline Markdown markers to plain text.
def plain_text(text: str) -> str:
    s = re.sub(r"`([^`]+)`|\[([^\]]+)\]\([^)]+\)", lambda m: m.group(1) or m.group(2), text)
    return " ".join(re.sub(r"(\*\*|__|\*|_)(.+?)\1", r"\2", s).split())


# Render inline Markdown (code, links, bold, italic) to safe HTML.
def render_inline(text: str) -> str:
    s = html.escape(text, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)


# Split a Markdown table row into trimmed cell strings.
def split_row(line: str) -> list[str]:
    return [c.replace(r"\|", "|").strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


# Check if a line is a Markdown table alignment separator.
def is_sep_row(line: str) -> bool:
    cells = split_row(line) if "|" in line else []
    return bool(cells) and all(re.match(r"^:?-{2,}:?$", c) for c in cells)


# Ensure QA.md has no raw HTML tags and only places checkboxes on Pass/Complete items.
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


# Convert validated Markdown into (title, html_body, checkbox_count).
def convert_markdown(md_text: str) -> tuple[str, str, int]:
    lines = md_text.splitlines()
    used_ids: set[str] = set()
    seq = order = checks = 0
    cur_h3, title, in_sec, in_fence = "", "Quality Assurance Procedure", False, False
    blocks: list[str] = []
    fence: list[str] = []

    def uid(prefix: str, label: str) -> str:
        nonlocal seq
        seq += 1
        slug = re.sub(r"[^a-z0-9]+", "-", plain_text(label).lower()).strip("-") or "item"
        cid = f"{prefix}-{slug}-{seq}" if f"{prefix}-{slug}" in used_ids else f"{prefix}-{slug}"
        used_ids.add(cid)
        return cid

    def next_ord() -> int:
        nonlocal order
        order += 1
        return order * 100

    def pair_for(label: str) -> tuple[str, str]:
        low = label.lower()
        return ("Complete", "Incomplete") if ("complete" in low and "pass" not in low) else ("Pass", "Fail")

    # Render a single list item (checkbox, metadata field, or procedural step).
    def make_li(rest: str) -> tuple[str, str]:
        nonlocal checks
        if cm := CHECK_RE.match(rest):
            checks += 1
            plain = plain_text(cm.group(2))
            t_val, f_val = pair_for(plain)
            cid, chk = uid("chk", plain), (" checked" if cm.group(1).lower() == "x" else "")
            return "qa-outcome-list", f'<li class="qa-check-item"><label class="qa-check-label" for="{cid}"><input type="checkbox" id="{cid}" class="qa-checkbox"{chk} data-csv-role="checkbox" data-csv-header="{html.escape(plain, True)}" data-checked-value="{t_val}" data-unchecked-value="{f_val}" data-csv-order="{next_ord()}"><span class="qa-check-text">{render_inline(cm.group(2))}</span></label></li>'
        if mm := META_RE.match(rest):
            clean = plain_text(mm.group(1)).rstrip(":").strip()
            low = clean.lower()
            hdr = f"{cur_h3} - {clean}" if (low in GENERIC_LABELS and cur_h3 and cur_h3.lower() not in {"qa metadata", "final result"}) else clean
            cid, ord_v = uid("meta", hdr), next_ord()
            ph = html.escape(next((v for k, v in HINTS if k in low), ""), True)
            eh, el = html.escape(hdr, True), html.escape(clean)
            if "date" in low:
                return "qa-meta-list", f'<li class="qa-meta-item"><label class="qa-meta-label" for="{cid}"><strong>{el}:</strong></label><input type="date" id="{cid}" class="qa-input qa-date-input" data-csv-role="metadata" data-csv-header="{eh}" data-csv-order="{ord_v}"></li>'
            if any(k in low for k in ("deviations", "waivers", "comments")):
                return "qa-meta-list", f'<li class="qa-meta-item qa-meta-block"><label class="qa-meta-label" for="{cid}"><strong>{el}:</strong></label><textarea id="{cid}" class="qa-input qa-textarea" rows="3" placeholder="{ph}" data-csv-role="metadata" data-csv-header="{eh}" data-csv-order="{ord_v}"></textarea></li>'
            wide = " qa-input-wide" if ("notes" in low or "defects" in low) else ""
            return "qa-meta-list", f'<li class="qa-meta-item"><label class="qa-meta-label" for="{cid}"><strong>{el}:</strong></label><input type="text" id="{cid}" class="qa-input{wide}" placeholder="{ph}" data-csv-role="metadata" data-csv-header="{eh}" data-csv-order="{ord_v}"></li>'
        return "qa-step-list", f"<li>{render_inline(rest)}</li>"

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
            if in_sec:
                blocks.append("</section>")
                in_sec = False
            blocks.append("<hr>")
            idx += 1
        elif hm := HEAD_RE.match(line):
            lvl, h_raw = len(hm.group(1)), hm.group(2)
            h_plain = plain_text(h_raw)
            if lvl == 1 and title == "Quality Assurance Procedure":
                title = h_plain
            elif lvl in (2, 3):
                cur_h3 = h_plain if lvl == 3 else ""
                if in_sec:
                    blocks.append("</section>")
                blocks.append('<section class="qa-section">')
                in_sec = True
            blocks.append(f'<h{lvl} id="{uid("sec", h_plain)}">{render_inline(h_raw)}</h{lvl}>')
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
            tbl = ['<div class="qa-table-wrap"><table class="qa-table"><thead><tr>' + "".join(f"<th>{render_inline(h)}</th>" for h in headers) + "</tr></thead><tbody>"]
            for row in rows:
                rkey = plain_text(row[0]) if row else ""
                tds = []
                for c, h_raw in enumerate(headers):
                    raw, col_h = (row[c] if c < len(row) else ""), plain_text(h_raw)
                    if cm := CELL_CHECK_RE.match(raw):
                        checks += 1
                        pre, suf = cm.group(1).strip(), cm.group(3).strip()
                        pre_p, suf_p = plain_text(pre).rstrip(":").strip(), plain_text(suf).strip()
                        csv_h = f"{rkey} {suf_p}".strip() if (not pre_p and rkey and c > 0) else " ".join(x for x in (pre_p, suf_p) if x)
                        ch_m = CH_RE.search(csv_h)
                        ord_v = (base_ord + int(ch_m.group(1))) if (has_ch and ch_m) else next_ord()
                        t_val, f_val = pair_for(csv_h)
                        cid, chk = uid("chk", csv_h), (" checked" if cm.group(2).lower() == "x" else "")
                        pre_h = f'<span class="qa-cell-prefix">{render_inline(pre)}</span> ' if pre else ""
                        suf_h = f'<span class="qa-check-text">{render_inline(suf)}</span>' if suf else ""
                        tds.append(f'<td><label class="qa-check-label qa-table-check" for="{cid}">{pre_h}<input type="checkbox" id="{cid}" class="qa-checkbox"{chk} data-csv-role="checkbox" data-csv-header="{html.escape(csv_h, True)}" data-checked-value="{t_val}" data-unchecked-value="{f_val}" data-csv-order="{ord_v}">{suf_h}</label></td>')
                    elif not raw and any(k in col_h.lower() for k in FILLABLE_COLS):
                        sec = f"{cur_h3} " if cur_h3 else ""
                        cid = uid("tbl", f"{sec}{rkey}-{col_h}")
                        ph = "Enter value..." if "measured" in col_h.lower() else "Optional notes..."
                        tds.append(f'<td><input type="text" id="{cid}" class="qa-input qa-table-input" aria-label="{html.escape(f"{sec}{rkey} {col_h}".strip(), True)}" placeholder="{ph}"></td>')
                    else:
                        tds.append(f"<td>{render_inline(raw)}</td>")
                tbl.append("<tr>" + "".join(tds) + "</tr>")
            tbl.append("</tbody></table></div>")
            blocks.append("\n".join(tbl))
        elif LIST_RE.match(line):
            groups: list[tuple[str, str, list[str]]] = []
            while idx < len(lines) and lines[idx].strip() and (lm := LIST_RE.match(lines[idx])):
                ind, marker, rest = len(lm.group(1).expandtabs(4)), lm.group(2), lm.group(3)
                idx += 1
                if ind > 0 and groups and groups[-1][2]:
                    sub = [f"<li>{render_inline(rest)}</li>"]
                    while idx < len(lines) and lines[idx].strip() and (sm := LIST_RE.match(lines[idx])) and len(sm.group(1).expandtabs(4)) > 0:
                        sub.append(f"<li>{render_inline(sm.group(3))}</li>")
                        idx += 1
                    groups[-1][2][-1] = groups[-1][2][-1][:-5] + f'<ul class="qa-step-list">{"".join(sub)}</ul></li>'
                else:
                    tag = "ol" if marker.endswith(".") else "ul"
                    cls, li_html = make_li(rest)
                    if not groups or groups[-1][0] != tag or groups[-1][1] != cls:
                        groups.append((tag, cls, []))
                    groups[-1][2].append(li_html)
            blocks.extend(f'<{t} class="{c}">\n' + "\n".join(items) + f"\n</{t}>" for t, c, items in groups)
        else:
            para = []
            while idx < len(lines):
                cur, cs = lines[idx], lines[idx].strip()
                if not cs or cs.startswith("```") or HR_RE.match(cs) or HEAD_RE.match(cur) or LIST_RE.match(cur) or ("|" in cur and idx + 1 < len(lines) and is_sep_row(lines[idx + 1])):
                    break
                para.append(cs)
                idx += 1
            blocks.append(f"<p>{render_inline(' '.join(para))}</p>")

    if in_sec:
        blocks.append("</section>")
    return title, "\n".join(blocks), checks


# Assemble the full standalone QA.html document.
def build_full_html(md_text: str, source_name: str = "QA.md", git_rev: str = "") -> str:
    validate_markdown(md_text, source_name=source_name)
    title, body, total = convert_markdown(md_text)
    checked = body.count('class="qa-checkbox" checked')
    top_bar = TOOLBAR_HTML.format(pos="Top", checked=checked, total=total)
    bot_bar = TOOLBAR_HTML.format(pos="Bottom", checked=checked, total=total)
    rev = f" &middot; Commit <code>{html.escape(git_rev)}</code>" if git_rev else ""
    meta = f'<div class="qa-doc-meta"><span>Generated from <code>documentation/QA.md</code>{rev}</span><a href="./" class="qa-back-link no-print">&larr; Back to Project Outputs</a></div>'
    body = body.replace("</h1>", f"</h1>\n{meta}\n{top_bar}", 1) if "</h1>" in body else f"{meta}\n{top_bar}\n{body}"
    return f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>{html.escape(title)}</title>\n<style>{PAGE_CSS}</style>\n</head>\n<body>\n<main class="qa-container">\n<form id="qa-form" onsubmit="return false;" autocomplete="off">\n{body}\n{bot_bar}\n</form>\n</main>\n<script>{PAGE_JS}</script>\n</body>\n</html>\n'


# Find matching closing tag index accounting for nested tags.
def find_close_tag(text: str, start: int, tag: str) -> int:
    depth = 0
    for m in re.finditer(rf"<(/?){tag}\b[^>]*>", text, re.I):
        if m.start() >= start:
            depth += -1 if m.group(1) == "/" else 1
            if depth == 0:
                return m.start()
    return -1


# Inject QA Procedure tile and sidebar link into KiBot *-navigate*.html pages.
def inject_kibot_navigation(nav_dir: pathlib.Path, qa_href: str = "QA.html") -> int:
    if not nav_dir.is_dir():
        return 0
    href = html.escape(qa_href, True)
    nav_li = f'  <li style="margin-top: 14px;"><a href="{href}">QA Procedure</a></li>\n'
    tile = f' <td><a href="{href}"><table class="cat-img"><tr><td>{KIBOT_QA_SVG}<br>QA Procedure</td></tr></table></a></td>\n'
    count = 0
    for path in sorted(nav_dir.glob("*-navigate*.html")):
        src = path.read_text(encoding="utf-8")
        if f'href="{href}"' in src:
            continue
        out = src
        if sm := re.search(r'<div\s+id="theSideNav"[^>]*>', out):
            end = find_close_tag(out, sm.start(), "div")
            if end != -1 and (pos := out.rfind("</ul>", sm.start(), end)) != -1:
                out = out[:pos] + nav_li + out[pos:]
        if cm := re.search(r'<table\s+class="cat-table"[^>]*>', out):
            end = find_close_tag(out, cm.start(), "table")
            if end != -1 and (pos := out.rfind("</tr>", cm.start(), end)) != -1:
                out = out[:pos] + tile + out[pos:]
        if out != src:
            path.write_text(out, encoding="utf-8")
            count += 1
    return count


# CLI entry point.
def main(argv: list[str] | None = None) -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Generate interactive QA.html from QA.md.")
    ap.add_argument("input", nargs="?", type=pathlib.Path, default=root / "documentation" / "QA.md")
    ap.add_argument("-o", "--output", type=pathlib.Path, default=root / "documentation" / "QA.html")
    ap.add_argument("--inject-nav", type=pathlib.Path, default=None)
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args(argv)

    if not args.input.is_file():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=args.input.resolve().parent, capture_output=True, text=True)
    git_rev = res.stdout.strip() if res.returncode == 0 else ""

    try:
        full_html = build_full_html(args.input.read_text(encoding="utf-8"), str(args.input), git_rev)
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
        print(f"Injected QA navigation links into {inject_kibot_navigation(args.inject_nav, rel)} KiBot page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
