# SAA

Tools for scraping the [State Archives of Assyria Online (SAAO)](https://oracc.museum.upenn.edu/saao) corpus from Oracc and compiling it into a single PDF.

## Pipeline

1. `collect_links.py` – crawls the SAAO sections with Playwright and saves all text links to `links_metadata.json`.
2. `print_with_fix.py` – renders pages for printing, using `inject_print_styles.js` and `print_fix_styles.css`.
3. `generate_combined_pdf.py` – downloads the texts in chunks and merges them into one PDF with a table of contents.

Helper scripts live in `utils/`.

## Setup

```sh
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/playwright install chromium
```

## Usage

```sh
venv/bin/python collect_links.py
venv/bin/python generate_combined_pdf.py
```

Generated data (`links_metadata.json`, chunks, logs, PDFs) is git-ignored.
