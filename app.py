from flask import Flask, request, jsonify
from flask_cors import CORS
import tempfile
import os
import traceback
import pikepdf
from pikepdf import Pdf, PdfImage

app = Flask(__name__)
CORS(app)

def s(v):
    try:
        return str(v)
    except Exception:
        return ''

def add_token(found, token):
    found['debug_tokens'].add(token)

def mark_rgb(found, token):
    found['has_rgb'] = True
    add_token(found, token)

def mark_spot(found, token):
    found['has_spot'] = True
    add_token(found, token)

def inspect_icc_stream(icc_obj, found):
    try:
        n = icc_obj.get('/N', None)
        alt = s(icc_obj.get('/Alternate', ''))

        if n == 3:
            mark_rgb(found, 'ICCBased(N=3)')
        elif n == 4:
            add_token(found, 'ICCBased(N=4)')
        elif n == 1:
            add_token(found, 'ICCBased(N=1)')
        else:
            add_token(found, 'ICCBased')

        if '/DeviceRGB' in alt:
            mark_rgb(found, 'ICC Alternate DeviceRGB')
        elif alt:
            add_token(found, f'ICC Alternate {alt}')
    except Exception:
        add_token(found, 'ICCBased(unreadable)')

def inspect_colorspace(cs, found, pdf):
    cs_str = s(cs)

    if not cs_str:
        return

    if '/DeviceRGB' in cs_str:
        mark_rgb(found, 'DeviceRGB')

    if '/CalRGB' in cs_str:
        mark_rgb(found, 'CalRGB')

    if '/Separation' in cs_str:
        mark_spot(found, 'Separation')

    if '/DeviceN' in cs_str:
        mark_spot(found, 'DeviceN')

    try:
        if isinstance(cs, pikepdf.Array) and len(cs) > 0:
            head = s(cs[0])

            if head == '/ICCBased' and len(cs) > 1:
                inspect_icc_stream(cs[1], found)

            elif head == '/Separation':
                mark_spot(found, 'Separation(array)')
                if len(cs) > 2:
                    inspect_colorspace(cs[2], found, pdf)

            elif head == '/DeviceN':
                mark_spot(found, 'DeviceN(array)')
                if len(cs) > 2:
                    inspect_colorspace(cs[2], found, pdf)

            elif head == '/Indexed' and len(cs) > 1:
                add_token(found, 'Indexed')
                inspect_colorspace(cs[1], found, pdf)
    except Exception:
        pass

def inspect_image_xobject(xobj, found, pdf):
    try:
        if '/ColorSpace' in xobj:
            inspect_colorspace(xobj['/ColorSpace'], found, pdf)
    except Exception:
        pass

    try:
        pim = PdfImage(xobj)

        cs = getattr(pim, 'colorspace', None)
        if cs:
            inspect_colorspace(cs, found, pdf)

        icc = getattr(pim, 'icc', None)
        if icc is not None:
            inspect_icc_stream(icc, found)

        mode = getattr(pim, 'mode', None)
        if mode == 'RGB':
            mark_rgb(found, 'image-mode-RGB')
    except Exception:
        pass

def inspect_resources(resources, found, pdf, visited=None):
    if not resources:
        return

    if visited is None:
        visited = set()

    try:
        objgen = getattr(resources, 'objgen', None)
        if objgen:
            if objgen in visited:
                return
            visited.add(objgen)
    except Exception:
        pass

    try:
        if '/ColorSpace' in resources:
            cs_dict = resources['/ColorSpace']
            for _, cs_val in cs_dict.items():
                inspect_colorspace(cs_val, found, pdf)
    except Exception:
        pass

    try:
        if '/XObject' in resources:
            xobjects = resources['/XObject']
            for _, xobj in xobjects.items():
                subtype = s(xobj.get('/Subtype', ''))

                if subtype == '/Image':
                    inspect_image_xobject(xobj, found, pdf)

                elif subtype == '/Form':
                    add_token(found, 'FormXObject')
                    if '/Resources' in xobj:
                        inspect_resources(xobj['/Resources'], found, pdf, visited)
    except Exception:
        pass

def inspect_page_content(page, found):
    try:
        contents = page.obj.get('/Contents', None)
        if not contents:
            return

        streams = []
        if isinstance(contents, pikepdf.Array):
            streams.extend(list(contents))
        else:
            streams.append(contents)

        for stream in streams:
            try:
                data = stream.read_bytes().decode('latin-1', errors='ignore')

                if '/DeviceRGB' in data:
                    mark_rgb(found, 'content-DeviceRGB')
                if '/CalRGB' in data:
                    mark_rgb(found, 'content-CalRGB')
                if '/Separation' in data:
                    mark_spot(found, 'content-Separation')
                if '/DeviceN' in data:
                    mark_spot(found, 'content-DeviceN')
            except Exception:
                continue
    except Exception:
        pass

def analyze_pdf_colors(pdf_path):
    found = {
        'has_rgb': False,
        'has_spot': False,
        'debug_tokens': set()
    }

    with Pdf.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                resources = page.obj.get('/Resources', {})
                inspect_resources(resources, found, pdf)
                inspect_page_content(page, found)
            except Exception:
                continue

    found['debug_tokens'] = sorted(found['debug_tokens'])
    return found

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'ok': True,
        'service': 'pdf-rgb-spot-check'
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'ok': True,
        'service': 'pdf-rgb-spot-check',
        'engine': 'pikepdf'
    })

@app.route('/analyze-pdf', methods=['GET', 'POST', 'OPTIONS'])
def analyze_pdf():
    if request.method == 'GET':
        return jsonify({
            'ok': True,
            'message': 'Use POST with multipart/form-data and field name "file".'
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
            'has_spot': result['has_spot'],
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