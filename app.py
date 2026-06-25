from flask import Flask, request, jsonify
from flask_cors import CORS
import tempfile
import os
import subprocess
import shutil
import traceback

app = Flask(__name__)
CORS(app)

def detect_spaces_from_text(text: str):
    t = text or ''
    has_rgb = ('DeviceRGB' in t) or ('CalRGB' in t)
    has_cmyk = 'DeviceCMYK' in t
    has_spot = ('Separation' in t) or ('DeviceN' in t)
    has_gray = ('DeviceGray' in t) or ('CalGray' in t)

    return {
        'has_rgb': has_rgb,
        'has_cmyk': has_cmyk,
        'has_spot': has_spot,
        'has_gray': has_gray,
    }

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'ok': True,
        'service': 'pdf-color-check'
    })

@app.route('/health', methods=['GET'])
def health():
    qpdf_path = shutil.which('qpdf')
    return jsonify({
        'ok': True,
        'qpdf_found': bool(qpdf_path),
        'qpdf_path': qpdf_path
    })

@app.route('/analyze-pdf', methods=['GET', 'POST', 'OPTIONS'])
def analyze_pdf():
    if request.method == 'GET':
        qpdf_path = shutil.which('qpdf')
        return jsonify({
            'ok': True,
            'message': 'Use POST with multipart/form-data and field name "file".',
            'qpdf_found': bool(qpdf_path),
            'qpdf_path': qpdf_path
        })

    if request.method == 'OPTIONS':
        return ('', 204)

    if 'file' not in request.files:
        return jsonify({
            'ok': False,
            'error': 'missing file',
            'received_keys': list(request.files.keys())
        }), 400

    f = request.files['file']

    if not f.filename:
        return jsonify({
            'ok': False,
            'error': 'empty filename'
        }), 400

    if not f.filename.lower().endswith('.pdf'):
        return jsonify({
            'ok': False,
            'error': 'file must be a PDF'
        }), 400

    qpdf_path = shutil.which('qpdf')
    if not qpdf_path:
        return jsonify({
            'ok': False,
            'error': 'qpdf not found in PATH'
        }), 500

    tmp_pdf = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as pdf_tmp:
            f.save(pdf_tmp.name)
            tmp_pdf = pdf_tmp.name

        result = subprocess.run(
            [qpdf_path, '--json', tmp_pdf],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return jsonify({
                'ok': False,
                'error': 'qpdf failed',
                'stderr': result.stderr.strip(),
                'returncode': result.returncode
            }), 500

        spaces = detect_spaces_from_text(result.stdout)

        return jsonify({
            'ok': True,
            'filename': f.filename,
            **spaces
        }), 200

    except Exception as e:
        return jsonify({
            'ok': False,
            'error': 'server exception',
            'details': str(e),
            'trace': traceback.format_exc()
        }), 500

    finally:
        if tmp_pdf and os.path.exists(tmp_pdf):
            os.unlink(tmp_pdf)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)