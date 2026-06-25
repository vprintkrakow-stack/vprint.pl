from flask import Flask, request, jsonify
import tempfile
import os
import subprocess

app = Flask(__name__)

def detect_spaces_from_text(text: str):
    t = text or ''
    has_rgb = any(x in t for x in ['DeviceRGB', 'CalRGB'])
    has_cmyk = 'DeviceCMYK' in t
    has_spot = any(x in t for x in ['Separation', 'DeviceN'])
    has_gray = any(x in t for x in ['DeviceGray', 'CalGray'])
    return {
        'has_rgb': has_rgb,
        'has_cmyk': has_cmyk,
        'has_spot': has_spot,
        'has_gray': has_gray,
    }

@app.get('/')
def home():
    return jsonify({'ok': True, 'service': 'pdf-color-check'})

@app.post('/analyze-pdf')
def analyze_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'missing file'}), 400

    f = request.files['file']
    if not f.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'file must be a PDF'}), 400

    tmp_pdf = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as pdf_tmp:
            f.save(pdf_tmp.name)
            tmp_pdf = pdf_tmp.name

        cmd = ['qpdf', '--json', tmp_pdf]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return jsonify({
                'error': 'qpdf failed',
                'details': result.stderr.strip()
            }), 500

        text = result.stdout
        spaces = detect_spaces_from_text(text)
        return jsonify(spaces)

    finally:
        if tmp_pdf and os.path.exists(tmp_pdf):
            os.unlink(tmp_pdf)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)