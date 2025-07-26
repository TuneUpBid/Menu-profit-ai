import os
import io
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image
import fitz  # PyMuPDF for PDF text extraction
import re
import json
from fpdf import FPDF


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

app = Flask(__name__)

app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_image(image: Image.Image) -> str:
    """
    Placeholder for future OCR support. Currently returns an empty string.
    To enable image OCR, install and configure an OCR engine such as Tesseract.
    """
    return ""


def extract_text(file_path: str) -> str:
    """
    Extract text from file. If the file is a PDF we use PyMuPDF to extract text directly.
    Image OCR is currently unsupported due to environment limitations; for images this
    function will return an empty string. Future versions may integrate an OCR engine.
    """
    ext = file_path.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        doc = fitz.open(file_path)
        texts = []
        for page in doc:
            texts.append(page.get_text())
        doc.close()
        return "\n".join(texts)
    else:
        # Image OCR not supported; return empty string
        return ""


def parse_menu(text: str):
    """
    Very naive parser that attempts to extract menu items with prices.
    Returns a list of dicts with name, description, and price.
    """
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    items = []
    price_pattern = re.compile(r'\$\s*([0-9]+(?:\.[0-9]{2})?)')
    current_item = None
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


def estimate_cost(item_name: str, price: float) -> float:
    """
    Estimate the cost of making an item based on the industry standard of 28-32% of the menu price【179994080388295†L140-L143】.
    We'll use the midpoint of 30%.
    """
    return price * 0.30


def analyze_items(items):
    """
    For each item, compute estimated cost, profit, margin and
    generate simple recommendations. This is a placeholder algorithm.
    """
    analysis = []
    for item in items:
        cost = estimate_cost(item['name'], item['price'])
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


def generate_report(items, analysis):
    """
    Generate a PDF report summarizing the menu analysis.
    Returns bytes of the PDF.
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'Menu Profit Optimization Report', ln=True)
    pdf.ln(5)
    pdf.set_font('Arial', '', 12)
    for item, ana in zip(items, analysis):
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 8, item['name'], ln=True)
        pdf.set_font('Arial', '', 10)
        if item['description']:
            pdf.multi_cell(0, 5, item['description'].strip())
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 5, f"Price: ${item['price']:.2f}", ln=True)
        pdf.cell(0, 5, f"Estimated Cost: ${ana['estimated_cost']:.2f}", ln=True)
        pdf.cell(0, 5, f"Estimated Profit: ${ana['estimated_profit']:.2f}", ln=True)
        pdf.cell(0, 5, f"Margin: {ana['estimated_margin']}%", ln=True)
        pdf.multi_cell(0, 5, f"Recommendation: {ana['recommendation']}")
        pdf.ln(3)
    # generate PDF in memory
    output = pdf.output(dest='S').encode('latin-1')
    return output


@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        text = extract_text(filepath)
        items = parse_menu(text)
        analysis = analyze_items(items)
        # Save analysis and items to session or return them immediately
        return jsonify({'items': items, 'analysis': analysis})
    else:
        return jsonify({'error': 'Invalid file type'}), 400


@app.route('/report', methods=['POST'])
def report():
    data = request.get_json()
    items = data.get('items')
    analysis = data.get('analysis')
    if not items or not analysis:
        return jsonify({'error': 'Missing items or analysis'}), 400
    pdf_bytes = generate_report(items, analysis)
    return send_file(io.BytesIO(pdf_bytes), download_name='report.pdf', as_attachment=True)


if __name__ == '__main__':
    # Optionally run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)