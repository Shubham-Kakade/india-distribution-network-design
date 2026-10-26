"""One-off: render docs/case_study.md to docs/case_study.pdf (two A4 pages) (D-048).

Not part of the model and not in requirements.txt. Needs the `markdown` package and a Chromium
binary (the one Playwright installs is used by default):

    pip install markdown
    python scripts/build_case_study_pdf.py [--chromium /path/to/chrome]
"""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SOURCE, TARGET = ROOT / "docs" / "case_study.md", ROOT / "docs" / "case_study.pdf"
PLAYWRIGHT_CHROMIUM = Path(os.getenv("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))

CSS = """
@page { size: A4; margin: 14mm 15mm 13mm 15mm; }
body { font-family: "Helvetica Neue", Arial, sans-serif; font-size: 9.6pt; line-height: 1.38;
       color: #1d2733; }
h1 { font-size: 16pt; margin: 0 0 2pt; color: #0d366b; }
h2 { font-size: 11pt; margin: 9pt 0 3pt; color: #1c5cab; border-bottom: 0.6pt solid #cde2fb;
     padding-bottom: 1pt; }
p, li { margin: 0 0 4pt; }
ul, ol { margin: 0 0 4pt 0; padding-left: 15pt; }
table { border-collapse: collapse; margin: 3pt 0 6pt; width: 100%; }
th, td { border-bottom: 0.5pt solid #c8ced6; padding: 2.5pt 6pt; text-align: left; }
th { background: #f3f5f8; }
em { color: #4a5563; }
img { display: block; width: 78%; margin: 4pt auto 2pt; }
"""


def chromium_path(given: str | None) -> Path:
    if given:
        return Path(given)
    hits = sorted(PLAYWRIGHT_CHROMIUM.glob("chromium-*/chrome-*/chrome"))
    if not hits:
        raise SystemExit("No Chromium found; pass --chromium /path/to/chrome")
    return hits[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chromium", help="Chromium or Chrome executable")
    args = parser.parse_args()
    body = markdown.markdown(SOURCE.read_text(encoding="utf-8"), extensions=["tables"])
    # Relative image paths in the Markdown resolve from docs/, as they do on GitHub
    base = f'<base href="{SOURCE.parent.as_uri()}/">'
    html = f'<!doctype html><html><head><meta charset="utf-8">{base}<style>{CSS}</style></head>'
    html += f"<body>{body}</body></html>"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "case_study.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run(
            [
                str(chromium_path(args.chromium)),
                "--headless",
                "--no-sandbox",
                "--no-pdf-header-footer",
                f"--print-to-pdf={TARGET}",
                page.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
    print(f"Wrote {TARGET}")  # noqa: T201  (a script, not library code)


if __name__ == "__main__":
    main()
