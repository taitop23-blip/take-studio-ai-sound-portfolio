"""Export the ten editable SVG pages to a matching submission PDF with Chrome."""
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NumberObject, RectangleObject


ROOT = Path(__file__).resolve().parent
WORK = ROOT / "tmp" / "pdfs"
OUT = ROOT / "output" / "pdf" / "ParkJunmin_AI_Sound_Engineer_Portfolio.pdf"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def main() -> None:
    if not CHROME.exists():
        raise SystemExit("Chrome was not found at the expected Windows path")
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pages = sorted((ROOT / "figma_pages").glob("*.svg"))
    if len(pages) != 10:
        raise SystemExit(f"Expected ten SVG pages, found {len(pages)}")

    images = []
    for page in pages:
        encoded = base64.b64encode(page.read_bytes()).decode("ascii")
        images.append(f'<section class="page"><img alt="{page.stem}" src="data:image/svg+xml;base64,{encoded}"></section>')
    html = (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<style>@page{size:1600px 900px;margin:0}'
        '*{box-sizing:border-box}html,body{margin:0;padding:0}'
        '.page{width:1600px;height:900px;break-after:page;page-break-after:always;overflow:hidden}'
        '.page:last-child{break-after:auto;page-break-after:auto}'
        'img{display:block;width:1600px;height:900px}'
        '</style></head><body>' + "".join(images) + '</body></html>'
    )
    html_path = WORK / "print.html"
    html_path.write_text(html, encoding="utf-8")

    command = [
        str(CHROME),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-sandbox",
        "--disable-extensions",
        "--no-pdf-header-footer",
        "--print-to-pdf=" + str(OUT),
        "--user-data-dir=" + str(WORK / "chrome-profile"),
        html_path.as_uri(),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if result.returncode != 0 or not OUT.exists():
        raise SystemExit(result.stderr or f"Chrome exited with {result.returncode}")

    reader = PdfReader(str(OUT))
    if len(reader.pages) != 10:
        raise SystemExit(f"Expected ten PDF pages, found {len(reader.pages)}")
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    def link(page: int, uri: str, x1: float, y1: float, x2: float, y2: float) -> None:
        # Source layout is 1600 × 900 SVG pixels; PDF uses 1200 × 675 pt.
        rect = RectangleObject((x1 * .75, (900 - y2) * .75, x2 * .75, (900 - y1) * .75))
        writer.add_uri(
            page,
            uri,
            rect,
            border=ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0)]),
        )

    repo = "https://github.com/taitop23-blip/take-studio-ai-sound-portfolio"
    listen = "https://taitop23-blip.github.io/take-studio-ai-sound-portfolio/listen.html"
    youtube_1 = "https://www.youtube.com/watch?v=lJyOIjUblrU"
    youtube_2 = "https://www.youtube.com/watch?v=melVFdUn6LA"
    link(7, youtube_1, 105, 590, 780, 630)
    link(7, youtube_2, 855, 590, 1530, 630)
    link(8, listen, 70, 780, 1520, 820)
    for i, uri in enumerate((listen, repo, youtube_1, youtube_2, "mailto:taito.p23@gmail.com")):
        y = 367 + i * 83
        link(9, uri, 175, y + 5, 1480, y + 45)

    linked = WORK / "linked.pdf"
    with linked.open("wb") as stream:
        writer.write(stream)
    linked.replace(OUT)
    print(f"Created {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
