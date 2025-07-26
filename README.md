# Menu Profit Optimizer Backend

This FastAPI service powers the Menu Profit Optimizer. It accepts uploaded menu files, extracts item names and prices, estimates costs and margins, and generates PDF reports.

## Features

* **PDF text extraction** – Uses [PyMuPDF](https://pymupdf.readthedocs.io/) to extract embedded text from PDF menus.
* **Image OCR (optional)** – If you supply a `GOOGLE_VISION_API_KEY` environment variable, the service will call the Google Cloud Vision API to extract text from uploaded PNG/JPG images. Without the API key, images will return an empty result.
* **Menu parsing** – A simple regex‑based parser identifies lines containing a dollar sign followed by a price and treats preceding text as the dish name.
* **Analysis** – Estimates ingredient cost (30 % of price) and computes profit and margin. Suggests price increases if margins fall below 60 %. Benchmarks are based on research indicating that restaurants aim for food cost percentages around 28–32 %【263601965871716†L206-L214】.
* **PDF report generation** – Uses matplotlib to assemble a multi‑page PDF summarizing each item’s analysis.

## Environment Variables

* `GOOGLE_VISION_API_KEY` – Your Google Cloud Vision API key. If provided, the service will perform OCR on images; otherwise, only PDF text extraction is supported.

## Running Locally

Install dependencies (FastAPI, uvicorn, PyMuPDF, matplotlib). Then start the server:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Use the `/upload` endpoint to POST a PDF or image and receive parsed items and analysis. Use `/report` to POST the same payload and receive a PDF report.