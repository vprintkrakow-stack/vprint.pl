from flask import Flask, request, jsonify
from flask_cors import CORS
import tempfile
import os
import traceback
import pikepdf
from pikepdf import Name, Pdf, PdfImage

app = Flask(__name__)
CORS(app)

def normalize_name(value):
    try:
        return str(value)
    except Exception:
        return ''

def inspect_colorspace_value(cs, found):
    cs_str = normalize_name(cs)

    if not cs_str:
        return

    if '/DeviceCMYK' in cs_str:
        found['has_cmyk'] = True
        found['debug_tokens'].add('DeviceCMYK')

    if '/DeviceRGB' in cs_str or '/CalRGB' in cs_str:
        found['has_rgb'] = True
        found['debug_tokens'].add('DeviceRGB/CalRGB')

    if '/DeviceGray' in cs_str or '/CalGray' in cs_str:
        found['has_gray'] = True
        found['debug_tokens'].add('DeviceGray/CalGray')

    if '/Separation' in cs_str or '/DeviceN' in cs_str:
        found['has_spot'] = True
        found['debug_tokens'].add('Separation/DeviceN')

    if '/ICCBased' in cs_str:
        found['debug_tokens'].add('ICCBased')

    if '/Indexed' in cs_str:
        found['debug_tokens'].add('Indexed')

def inspect_image_xobject(xobj, found):
    try:
        pim = PdfImage(xobj)
        cs = getattr(pim, 'colorspace', None)
        if cs:
            inspect_colorspace_value(cs, found)

        mode = getattr(pim, 'mode', None)
        if mode == 'CMYK':
            found['has_cmyk'] = True
            found['debug_tokens'].add('image-mode-CMYK')
        elif mode == 'RGB':
            found['has_rgb'] = True
            found['debug_tokens'].add('image-mode-RGB')
        elif mode in ('L', '1', 'LA'):
            found['has_gray'] = True
            found['debug_tokens'].add('image-mode-GRAY')
    except Exception:
        pass

    try:
        if '/ColorSpace' in xobj:
            inspect_colorspace_value(xobj['/ColorSpace'], found)
    except Exception:
        pass

def inspect_resources(resources, found):
    if not resources:
        return

    try:
        if '/ColorSpace' in resources:
            cs_dict = resources['/ColorSpace']
            for _, cs_val in cs_dict.items():
                inspect_colorspace_value(cs_val, found)
    except Exception:
        pass

    try:
        if '/XObject' in resources:
            xobjects = resources['/XObject']
            for _, xobj in xobjects.items():
                subtype = normalize_name(xobj.get('/Subtype', ''))
                if subtype == '/Image':
                    inspect_image_xobject(xobj, found)
                elif subtype == '/Form':
                    if '/Resources' in xobj:
                        inspect_resources(xobj['/Resources'], found)
    except Exception:
        pass

def analyze_pdf_colors(pdf_path):
    found = {
        'has_rgb': False,
        'has_cmyk': False,
        'has_spot': False,
        'has_gray': False,
        'debug_tokens': set()
    }

    with Pdf.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                resources = page.obj.get('/Resources', {})
                inspect_resources(resources, found)
            except Exception:
                continue

    found['debug_tokens'] = sorted(found['debug_tokens'])
    return found

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'ok': True,
        'service': 'pdf-color-check'
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'ok': True,
        'service': 'pdf-color-check',
        'engine': 'pikepdf'
    })

@app.route('/analyze-pdf', methods=['GET', 'POST', 'OPTIONS'])
def analyze_pdf():
    if request.method == 'GET':
        return jsonify({
            'ok': True,
            'message': 'Use POST with multipart/form-data and field name \"file\".'
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

    tmp_pdf = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as pdf_tmp:
            f.save(pdf_tmp.name)
            tmp_pdf = pdf_tmp.name

        result = analyze_pdf_colors(tmp_pdf)

        return jsonify({
            'ok': True,
            'filename': f.filename,
            'has_rgb': result['has_rgb'],
            'has_cmyk': result['has_cmyk'],
            'has_spot': result['has_spot'],
            'has_gray': result['has_gray'],
            'debug_tokens': result['debug_tokens']
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