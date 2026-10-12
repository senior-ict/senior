"""Render EXPERIMENT_LOG.md to a PDF with matplotlib, nothing else installed.

Headings are set larger and bold; everything else -- prose, tables, code --
is laid out verbatim in monospace so the tables keep their columns. Long
lines wrap on spaces. Pages break at a fixed line count, never inside a table
or code block when that can be helped.

    python docs/experiments/2026-09_test_captures/render_log_pdf.py
"""
import pathlib
import textwrap

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / "EXPERIMENT_LOG.md"
OUTPUT = HERE / "EXPERIMENT_LOG.pdf"

PAGE_SIZE = (11.69, 8.27)          # A4 landscape, inches
LINES_PER_PAGE = 46
WRAP_COLUMNS = 118
MONO_SIZE = 7.6
LINE_HEIGHT = 0.0185               # figure fraction per rendered line
INK, MUTED, ACCENT = "#1a1a1a", "#5a5a5a", "#0b5fa5"


def wrap_line(line):
    """Split one source line into rendered lines, keeping indentation."""
    if not line.strip():
        return [""]
    indent = len(line) - len(line.lstrip(" "))
    body = line.strip()
    pieces = textwrap.wrap(body, width=WRAP_COLUMNS - indent,
                           break_long_words=False, break_on_hyphens=False)
    return [" " * indent + piece for piece in pieces] or [""]


def classify(line):
    """('heading', level, text) for markdown headings, else ('text', 0, line)."""
    stripped = line.lstrip()
    if stripped.startswith("#"):
        level = len(stripped) - len(stripped.lstrip("#"))
        return "heading", level, stripped.lstrip("#").strip()
    return "text", 0, line


def paginate(source_lines):
    """Group rendered lines into pages, avoiding breaks inside fenced blocks."""
    pages, current, in_fence = [], [], False
    for raw in source_lines:
        kind, level, text = classify(raw)
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        rendered = [(kind, level, text)] if kind == "heading" else [
            ("text", 0, piece) for piece in wrap_line(raw)]
        # Start a new page before a heading that would land near the bottom,
        # and only break inside a code block if it cannot be avoided.
        if kind == "heading" and len(current) > LINES_PER_PAGE - 6:
            pages.append(current)
            current = []
        for item in rendered:
            if len(current) >= LINES_PER_PAGE and not in_fence:
                pages.append(current)
                current = []
            current.append(item)
    if current:
        pages.append(current)
    return pages


def draw_page(pdf, page_lines, page_number, page_total, footer_name=SOURCE.name):
    """Lay one page's lines onto a figure and save it to the PDF."""
    figure = plt.figure(figsize=PAGE_SIZE)
    y_position = 0.955
    for kind, level, text in page_lines:
        if kind == "heading":
            size = {1: 15, 2: 12, 3: 10.5}.get(level, 10)
            y_position -= LINE_HEIGHT * 0.6
            figure.text(0.05, y_position, text, fontsize=size, weight="bold",
                        color=ACCENT if level == 2 else INK, va="top")
            y_position -= LINE_HEIGHT * (1.6 if level == 1 else 1.3)
        else:
            figure.text(0.05, y_position, text, fontsize=MONO_SIZE,
                        family="monospace", color=INK, va="top")
            y_position -= LINE_HEIGHT
    figure.text(0.95, 0.03, f"{page_number} / {page_total}", fontsize=7,
                color=MUTED, ha="right")
    figure.text(0.05, 0.03, f"docs/experiments/2026-09_test_captures/{footer_name}",
                fontsize=7, color=MUTED)
    pdf.savefig(figure)
    plt.close(figure)


def main():
    """Read the markdown, paginate it, write the PDF beside it.

    With no argument this renders EXPERIMENT_LOG.md; a path on the command
    line renders that file instead, to a .pdf of the same name.
    """
    import sys
    source = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else SOURCE
    output = source.with_suffix(".pdf")
    source_lines = source.read_text().splitlines()
    pages = paginate(source_lines)
    with PdfPages(output) as pdf:
        for index, page_lines in enumerate(pages, start=1):
            draw_page(pdf, page_lines, index, len(pages), footer_name=source.name)
    print(f"{output}  ({len(pages)} pages)")


if __name__ == "__main__":
    main()
