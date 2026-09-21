"""Render docs/pipeline/current_pipeline.md as an A4 PDF beside it.

The Markdown is the source; this turns the small subset it uses (headings,
paragraphs, bullet and numbered lists, tables, code blocks, images, bold and
inline code) into HTML, and PyMuPDF's Story lays that out across pages.

    python docs/pipeline/make_current_pipeline_pdf.py
"""
import html
import pathlib
import re

import pymupdf

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / "current_pipeline.md"
OUTPUT = HERE / "current_pipeline.pdf"
PAGE = pymupdf.paper_rect("a4")
MARGIN = 50

STYLE = """
body { font-family: sans-serif; font-size: 10pt; color: #1a1a1a; line-height: 1.4; }
h1 { font-size: 19pt; margin-bottom: 6pt; }
h2 { font-size: 14pt; margin-top: 14pt; margin-bottom: 4pt; color: #0b3d75; }
p { margin-top: 3pt; margin-bottom: 5pt; }
li { margin-bottom: 2pt; }
code { font-family: monospace; font-size: 9pt; color: #3a3a3a; }
pre { font-family: monospace; font-size: 8.5pt; background-color: #f2f1ec; padding: 6pt; }
table { border-collapse: collapse; margin-top: 4pt; margin-bottom: 8pt; }
th { font-size: 9pt; text-align: left; border-bottom: 1px solid #1a1a1a; padding: 2pt 6pt 2pt 2pt; }
td { font-size: 9pt; border-bottom: 1px solid #dddad2; padding: 2pt 6pt 2pt 2pt; }
img { width: 100%; }
"""


def inline_markup(text):
    """Escape the text, then turn **bold** and `code` into HTML."""
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def table_to_html(table_lines):
    """A Markdown table (header, divider, rows) as an HTML table."""
    rows = []
    for line in table_lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    header = rows[0]
    body_rows = rows[2:]
    parts = ["<table><tr>"]
    for cell in header:
        parts.append(f"<th>{inline_markup(cell)}</th>")
    parts.append("</tr>")
    for row in body_rows:
        parts.append("<tr>")
        for cell in row:
            parts.append(f"<td>{inline_markup(cell)}</td>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def list_item_start(line):
    """('ul' or 'ol', item text) if this line starts a list item, else None."""
    bullet = re.match(r"^- (.*)$", line)
    if bullet:
        return "ul", bullet.group(1)
    numbered = re.match(r"^\d+\. (.*)$", line)
    if numbered:
        return "ol", numbered.group(1)
    return None


def markdown_to_html(markdown_text):
    """Convert the document's Markdown subset to an HTML body."""
    lines = markdown_text.split("\n")
    parts = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            code_lines = []
            index += 1
            while not lines[index].startswith("```"):
                code_lines.append(html.escape(lines[index]))
                index += 1
            parts.append("<pre>" + "\n".join(code_lines) + "</pre>")
            index += 1
        elif line.startswith("# "):
            parts.append(f"<h1>{inline_markup(line[2:])}</h1>")
            index += 1
        elif line.startswith("## "):
            parts.append(f"<h2>{inline_markup(line[3:])}</h2>")
            index += 1
        elif line.startswith("!["):
            image = re.match(r"!\[(.*?)\]\((.*?)\)", line)
            # Images are referenced from docs/pipeline/; the archive is rooted at docs/.
            image_path = image.group(2).replace("../", "", 1)
            parts.append(f'<p><img src="{image_path}"/></p>')
            index += 1
        elif line.startswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index])
                index += 1
            parts.append(table_to_html(table_lines))
        elif list_item_start(line):
            list_kind = list_item_start(line)[0]
            items = []
            while index < len(lines) and (list_item_start(lines[index]) or lines[index].startswith("   ")
                                          or lines[index].startswith("  ")):
                started = list_item_start(lines[index])
                if started:
                    items.append(started[1])
                else:
                    items[-1] = items[-1] + " " + lines[index].strip()
                index += 1
            number_start = ""
            if list_kind == "ol":
                first_number = re.match(r"^(\d+)\.", line).group(1)
                number_start = f' start="{first_number}"'
            parts.append(f"<{list_kind}{number_start}>")
            for item in items:
                parts.append(f"<li>{inline_markup(item)}</li>")
            parts.append(f"</{list_kind}>")
        elif line.strip() == "":
            index += 1
        else:
            paragraph_lines = []
            while index < len(lines) and lines[index].strip() != "" and not lines[index].startswith(
                    ("#", "|", "```", "![", "- ")) and not re.match(r"^\d+\. ", lines[index]):
                paragraph_lines.append(lines[index].strip())
                index += 1
            parts.append(f"<p>{inline_markup(' '.join(paragraph_lines))}</p>")
    return "\n".join(parts)


def main():
    """Lay the document out on A4 pages and number them."""
    body = markdown_to_html(SOURCE.read_text())
    archive = pymupdf.Archive(str(HERE.parent))
    story = pymupdf.Story(html=f"<body>{body}</body>", user_css=STYLE, archive=archive)
    unnumbered_path = OUTPUT.with_suffix(".unnumbered.pdf")
    writer = pymupdf.DocumentWriter(str(unnumbered_path))
    content_area = PAGE + (MARGIN, MARGIN, -MARGIN, -MARGIN)
    more_to_place = True
    while more_to_place:
        device = writer.begin_page(PAGE)
        more_to_place, _ = story.place(content_area)
        story.draw(device)
        writer.end_page()
    writer.close()

    document = pymupdf.open(str(unnumbered_path))
    for page_number, page in enumerate(document, start=1):
        page.insert_text((PAGE.width - MARGIN - 20, PAGE.height - 25), f"{page_number}",
                         fontsize=8, color=(0.5, 0.5, 0.5))
        page.insert_text((MARGIN, PAGE.height - 25), "Pipeline, 21 September 2026 (keng-branch)",
                         fontsize=8, color=(0.5, 0.5, 0.5))
    page_count = len(document)
    document.save(str(OUTPUT))
    document.close()
    unnumbered_path.unlink()
    print(f"{OUTPUT} ({page_count} pages)")


if __name__ == "__main__":
    main()
