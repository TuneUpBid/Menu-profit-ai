"""
FastAPI backend for the Restaurant Menu Profit Optimizer.

This backend exposes two primary endpoints:

1. `/upload`: Accepts a multipart form with a PDF file and extracts textual menu information. It then parses
   menu items and estimates their cost, profit and margin.

2. `/report`: Accepts JSON payload containing the menu items and analysis generated from `/upload` and returns
   a PDF report summarizing the analysis.

Due to environment limitations, OCR on image files (PNG, JPG) is currently unsupported. Only PDFs with
embedded text will work for extraction. Future versions of this service may integrate an OCR engine for
images.
"""

import io
import os
import re
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

import fitz  # PyMuPDF for PDF text extraction
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

app = FastAPI(title="Menu Profit Optimizer Backend")


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF given its bytes using PyMuPDF."""
    # load from bytes
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    texts: List[str] = []
    for page in doc:
        texts.append(page.get_text())
    doc.close()
    return "\n".join(texts)


def extract_text_from_image_with_google_vision(image_bytes: bytes) -> str:
    """
    Use Google Cloud Vision API to extract text from an image. Requires the
    environment variable `GOOGLE_VISION_API_KEY` to be set. If the API key is
    missing or the request fails, returns an empty string.
    """
    api_key = os.environ.get('GOOGLE_VISION_API_KEY')
    if not api_key:
        # API key not configured
        return ""
    import base64
    import requests
    encoded = base64.b64encode(image_bytes).decode('utf-8')
    url = f'https://vision.googleapis.com/v1/images:annotate?key={api_key}'
    payload = {
        "requests": [
            {
                "image": {"content": encoded},
                "features": [
                    {"type": "DOCUMENT_TEXT_DETECTION"}
                ]
            }
        ]
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        result = response.json()
        text = result['responses'][0].get('fullTextAnnotation', {}).get('text', '')
        return text
    except Exception as exc:
        print(f"[ERROR] Vision API call failed: {exc}")
        return ""


def parse_menu(text: str):
    """
    Very naive parser that attempts to extract menu items with prices.
    Returns a list of dicts with name, description, and price.
    """
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    items = []
    price_pattern = re.compile(r'\$\s*([0-9]+(?:\.[0-9]{2})?)')
    for line in lines:
        price_match = price_pattern.search(line)
        if price_match:
            price = float(price_match.group(1))
            name = price_pattern.sub('', line).strip()
            items.append({
                'name': name,
                'description': '',
                'price': price
            })
        else:
            # treat as description if we have current item
            if items:
                items[-1]['description'] += (' ' + line)
    return items


def estimate_cost(price: float) -> float:
    """
    Estimate the cost of making an item based on the industry standard of 28-32% of the menu price【179994080388295†L140-L143】.
    We'll use the midpoint of 30%.
    """
    return price * 0.30


def analyze_items(items):
    analysis = []
    for item in items:
        cost = estimate_cost(item['price'])
        profit = item['price'] - cost
        margin = profit / item['price'] if item['price'] else 0
        recommendation = ''
        # Suggest price increase if margin < 0.6 (i.e., cost more than 40%)
        if margin < 0.6:
            new_price = round(cost / 0.28, 2)  # price to achieve 28% cost of goods
            recommendation = f"Consider increasing price to ${new_price} to achieve a 28% food cost."
        else:
            recommendation = "Price seems reasonable based on typical food cost percentages."
        analysis.append({
            'name': item['name'],
            'price': item['price'],
            'estimated_cost': round(cost, 2),
            'estimated_profit': round(profit, 2),
            'estimated_margin': round(margin * 100, 2),
            'recommendation': recommendation
        })
    return analysis


def generate_report(items, analysis) -> bytes:
    """
    Generate a PDF report summarizing the menu analysis using matplotlib.
    Returns bytes of the PDF.
    """
    # We'll assemble all content onto a single PDF. We'll create a figure per page
    # if the number of items is large. For simplicity, each item will be a separate
    # page. A summary page is also included.
    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf_pages:
        # summary page
        fig, ax = plt.subplots(figsize=(8.27, 11.69))  # A4 size in inches
        ax.axis('off')
        y = 0.95
        ax.text(0.5, y, 'Menu Profit Optimization Report', fontsize=20, ha='center', va='top')
        y -= 0.05
        ax.text(0.5, y, f'Total Items Analyzed: {len(items)}', fontsize=12, ha='center')
        y -= 0.05
        avg_margin = sum(a['estimated_margin'] for a in analysis) / len(analysis) if analysis else 0
        ax.text(0.5, y, f'Average Margin: {avg_margin:.2f}%', fontsize=12, ha='center')
        pdf_pages.savefig(fig)
        plt.close(fig)
        for item, ana in zip(items, analysis):
            fig, ax = plt.subplots(figsize=(8.27, 11.69))
            ax.axis('off')
            y = 0.95
            ax.text(0.01, y, item['name'], fontsize=16, ha='left', va='top', weight='bold')
            y -= 0.04
            if item['description']:
                # Wrap description
                desc = item['description'].strip()
                ax.text(0.01, y, desc, fontsize=10, ha='left', va='top', wrap=True)
                y -= 0.05
            ax.text(0.01, y, f"Price: ${item['price']:.2f}", fontsize=10, ha='left')
            y -= 0.03
            ax.text(0.01, y, f"Estimated Cost: ${ana['estimated_cost']:.2f}", fontsize=10, ha='left')
            y -= 0.03
            ax.text(0.01, y, f"Estimated Profit: ${ana['estimated_profit']:.2f}", fontsize=10, ha='left')
            y -= 0.03
            ax.text(0.01, y, f"Margin: {ana['estimated_margin']}%", fontsize=10, ha='left')
            y -= 0.03
            # wrap recommendation
            rec = ana['recommendation']
            ax.text(0.01, y, f"Recommendation: {rec}", fontsize=10, ha='left', wrap=True)
            pdf_pages.savefig(fig)
            plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    filename = file.filename
    if not filename or not allowed_file(filename):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF, PNG, JPG images are supported.")
    file_bytes = await file.read()
    ext = filename.rsplit('.', 1)[1].lower()
    text = ""
    try:
        if ext == 'pdf':
            text = extract_text_from_pdf(file_bytes)
        else:
            text = extract_text_from_image_with_google_vision(file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to extract text: {exc}")
    if not text:
        return JSONResponse({"items": [], "analysis": []})
    items = parse_menu(text)
    analysis = analyze_items(items)
    return JSONResponse({"items": items, "analysis": analysis})


@app.post("/report")
async def report(payload: dict):
    items = payload.get('items')
    analysis = payload.get('analysis')
    if not items or not analysis:
        raise HTTPException(status_code=400, detail="Missing items or analysis in request body.")
    pdf_bytes = generate_report(items, analysis)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=report.pdf"})
