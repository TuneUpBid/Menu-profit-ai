import io
import os
import re
import base64
import requests
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from PyPDF2 import PdfReader
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# Allowed file types
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

app = FastAPI(title="Menu Profit Optimizer")

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF using PyPDF2."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        texts: List[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            texts.append(text)
        return "\n".join(texts)
    except Exception as exc:
        print(f"[ERROR] Failed to read PDF: {exc}")
        return ""

def extract_text_from_image_with_google_vision(image_bytes: bytes) -> str:
    """
    Use Google Cloud Vision API to extract text from an image.
    Requires the environment variable `GOOGLE_VISION_API_KEY` to be set.
    If the API key is missing or the request fails, returns an empty string.
    """
    api_key = os.environ.get("GOOGLE_VISION_API_KEY")
    if not api_key:
        return ""
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
    payload = {
        "requests": [
            {
                "image": {"content": encoded},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            }
        ]
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        result = response.json()
        text = result["responses"][0].get("fullTextAnnotation", {}).get("text", "")
        return text
    except Exception as exc:
        print(f"[ERROR] Vision API call failed: {exc}")
        return ""

def parse_menu(text: str):
    """Naively parse menu items and prices from extracted text."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    items = []
    price_pattern = re.compile(r"\$\s*([0-9]+(?:\.[0-9]{2})?)")
    current_item = None
    for line in lines:
        price_match = price_pattern.search(line)
        if price_match:
            price = float(price_match.group(1))
            name_desc = line[: price_match.start()].strip()
            if current_item:
                items.append(current_item)
            current_item = {"name": name_desc, "description": "", "price": price}
        else:
            if current_item:
                if current_item["description"]:
                    current_item["description"] += " " + line
                else:
                    current_item["description"] = line
    if current_item:
        items.append(current_item)
    return items

def estimate_food_cost_and_profit(items: list):
    """Estimate food cost (30 % of price) and profit/margin for each item."""
    analysis = []
    for item in items:
        price = item["price"]
        cost = round(price * 0.3, 2)
        profit = round(price - cost, 2)
        margin = round(profit / price * 100, 2)
        analysis.append(
            {
                "name": item["name"],
                "description": item["description"],
                "price": price,
                "food_cost": cost,
                "profit": profit,
                "margin": margin,
            }
        )
    return analysis

def create_report_pdf(analysis: list) -> bytes:
    """Generate a PDF report using matplotlib."""
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        fig, ax = plt.subplots(figsize=(8, 10))
        ax.axis("off")
        y = 1.0
        ax.set_title("Menu Profit Analysis", fontsize=16, pad=20)
        for idx, item in enumerate(analysis, start=1):
            line = (
                f"{idx}. {item['name']} — Price: ${item['price']:.2f}, "
                f"Cost: ${item['food_cost']:.2f}, Profit: ${item['profit']:.2f}, "
                f"Margin: {item['margin']:.1f}%"
            )
            ax.text(0.01, y, line, fontsize=10)
            y -= 0.05
            if y < 0.1:
                pdf.savefig(fig)
                plt.close(fig)
                fig, ax = plt.subplots(figsize=(8, 10))
                ax.axis("off")
                y = 1.0
        if y < 1.0:
            pdf.savefig(fig)
            plt.close(fig)
    buf.seek(0)
    return buf.read()

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """Handle menu file upload (PDF or image)."""
    if not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported file type")
    content = await file.read()
    ext = file.filename.rsplit(".", 1)[1].lower()
    if ext == "pdf":
        text = extract_text_from_pdf(content)
    else:
        text = extract_text_from_image_with_google_vision(content)
    items = parse_menu(text)
    analysis = estimate_food_cost_and_profit(items)
    return JSONResponse({"items": items, "analysis": analysis})

@app.post("/report")
async def report(data: dict):
    """Generate and return a PDF report for previously analysed items."""
    analysis = data.get("analysis", [])
    if not analysis:
        raise HTTPException(status_code=400, detail="No analysis data provided")
    pdf_bytes = create_report_pdf(analysis)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=report.pdf"},
    )
