"""
backend/server.py — Flask backend service
==========================================
Unified pipeline: BiRefNet + SegFormer -> UV texture -> Three.js display
"""

import io
import os
import sys
import time
import uuid
import json

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from flask import Flask, request, send_file, send_from_directory, jsonify
from PIL import Image
import numpy as np

import config
from ai.apply_texture import (
    load_uv_template, detect_uv_islands, identify_front_body_island,
    extract_dominant_color, warp_fabric_to_island,
)
from ai.pipeline_segment import segment_clothing_from_photo, segformer_full_labels
from ai.pin_mapping import crop_transparent_margin, map_with_pins

app = Flask(__name__)

def map_pins_logic(clothing_rgba, template_path, clothing_type, base_name):
    """通过图钉对齐生成纹理"""
    user_pin_file = os.path.join(SEG_POSITIONING_DIR, base_name + '.json')
    uv_pin_file = os.path.join(POSITIONING_DIR, f'{clothing_type}_pins.json')
    with open(user_pin_file, 'r', encoding='utf-8') as f:
        user_pins = json.load(f).get('pins', [])
    with open(uv_pin_file, 'r', encoding='utf-8') as f:
        uv_pins = json.load(f).get('pins', [])
    return map_with_pins(clothing_rgba, template_path, user_pins, uv_pins, verbose=True)


# --- Ensure directories exist ---
PROCESS_DIR = os.path.join(config.ASSETS_DIR, 'process')
SEG_PIC_DIR = os.path.join(config.ASSETS_DIR, 'seg-pic')
TEXTURE_DIR = config.TEXTURE_DIR
POSITIONING_DIR = os.path.join(config.ASSETS_DIR, 'positioning')
SEG_POSITIONING_DIR = os.path.join(SEG_PIC_DIR, 'positioning')
for d in [PROCESS_DIR, SEG_PIC_DIR, TEXTURE_DIR, POSITIONING_DIR, SEG_POSITIONING_DIR]:
    os.makedirs(d, exist_ok=True)


# --- CORS + no-cache for HTML (avoid stale cached UI) ---
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    # 让浏览器每次重新校验 HTML（index/com/pho），避免缓存旧界面
    if response.mimetype == 'text/html':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


# --- UV processing (legacy method, kept for compatibility) ---
def generate_uv_texture(clothing_rgba, template_path, verbose=True):
    """Map segmented clothing to UV template (perspective transform mode)"""
    _, island_mask, _ = load_uv_template(template_path)
    h, w = island_mask.shape
    islands = detect_uv_islands(island_mask)
    if len(islands) < 2:
        raise ValueError(f'UV template islands insufficient (need >= 2, got {len(islands)})')
    front_idx = identify_front_body_island(islands, canvas_w=w)
    front_island = islands[front_idx]
    if verbose:
        print(f'  UV: {len(islands)} islands, front=[{front_idx}] area={front_island["area"]}')
    full_result = warp_fabric_to_island(clothing_rgba, front_island['mask'], w, h)
    clothing_arr = np.array(clothing_rgba)
    theme_color = extract_dominant_color(clothing_arr)
    if verbose:
        print(f'  Theme color: RGB({theme_color[0]},{theme_color[1]},{theme_color[2]})')
    for idx, isl in enumerate(islands):
        if idx == front_idx:
            continue
        full_result[isl['mask']] = theme_color
    return Image.fromarray(full_result.astype(np.uint8))


# --- Routes ---

@app.route('/')
def index():
    return send_from_directory(_PROJECT_ROOT, 'index.html')

@app.route('/com-index.html')
def com_index():
    return send_from_directory(_PROJECT_ROOT, 'com-index.html')

@app.route('/pho-index.html')
def pho_index():
    return send_from_directory(_PROJECT_ROOT, 'pho-index.html')

@app.route('/assets/<path:filename>')
def assets(filename):
    return send_from_directory(config.ASSETS_DIR, filename)

@app.route('/models/<path:filename>')
def models(filename):
    return send_from_directory(config.MODELS_DIR, filename)

@app.route('/Texture/<path:filename>')
def texture(filename):
    return send_from_directory(config.TEXTURE_DIR, filename)

@app.route('/clothing/<path:filename>')
def clothing(filename):
    return send_from_directory(config.CLOTHING_DIR, filename)


@app.route('/api/clothing-types')
def clothing_types():
    types = []
    for key, class_ids in config.CLOTHING_TYPE_MAP.items():
        names = [config.SEGFORMER_CLASSES[c] for c in class_ids]
        types.append({
            'id': key,
            'label': '/'.join(names),
            'class_ids': list(class_ids),
            'uv_template': config.CLOTHING_TO_UV.get(key),
            'model_3d': config.CLOTHING_TO_MODEL.get(key),
        })
    return jsonify(types)


@app.route('/api/analyze', methods=['POST'])
def analyze():
    photo = request.files.get('photo')
    if not photo:
        return {'error': 'Missing photo'}, 400
    try:
        img = Image.open(photo).convert('RGB')
        stats = segformer_full_labels(img)
        total = sum(stats.values())
        classes = []
        for cls_id, cnt in sorted(stats.items(), key=lambda x: -x[1]):
            classes.append({
                'id': cls_id,
                'name': config.SEGFORMER_CLASSES.get(cls_id, f'class_{cls_id}'),
                'pixels': cnt,
                'ratio': round(cnt / total * 100, 1),
            })
        clothing_classes = {4: 'upper', 5: 'skirt', 6: 'pants', 7: 'dress'}
        suggestion = None
        for cls_id in [4, 7, 5, 6]:
            if cls_id in stats and stats[cls_id] > 1000:
                suggestion = clothing_classes[cls_id]
                break
        return jsonify({'classes': classes, 'suggestion': suggestion})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'error': str(e)}, 500


@app.route('/api/process-history')
def process_history():
    items = []
    if not os.path.exists(TEXTURE_DIR):
        return jsonify(items)
    for fn in sorted(os.listdir(TEXTURE_DIR)):
        if not fn.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue
        name = os.path.splitext(fn)[0]
        seg_fn = None
        for ext in ('.png', '.jpg', '.jpeg'):
            candidate = name + ext
            if os.path.exists(os.path.join(SEG_PIC_DIR, candidate)):
                seg_fn = candidate
                break
        items.append({
            'name': name,
            'texture_url': f'assets/Texture/{fn}',
            'seg_pic_url': f'assets/seg-pic/{seg_fn}' if seg_fn else None,
        })
    return jsonify(items)


# ================================================================
#  Workbench (pin) API
# ================================================================

@app.route('/api/seg-pics')
def seg_pics():
    """Return list of images in seg-pic for the workbench page"""
    items = []
    if not os.path.exists(SEG_PIC_DIR):
        return jsonify(items)
    for fn in sorted(os.listdir(SEG_PIC_DIR), reverse=True):
        if not fn.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue
        base = os.path.splitext(fn)[0]
        pin_file = os.path.join(SEG_POSITIONING_DIR, base + '.json')
        pins = []
        if os.path.exists(pin_file):
            try:
                with open(pin_file, 'r', encoding='utf-8') as f:
                    pins = json.load(f).get('pins', [])
            except Exception:
                pins = []
        items.append({
            'name': fn,
            'url': f'assets/seg-pic/{fn}',
            'pins': pins,
        })
    return jsonify(items)


@app.route('/api/seg-pic/<path:name>/pins')
def get_seg_pic_pins(name):
    base = os.path.splitext(name)[0]
    pin_file = os.path.join(SEG_POSITIONING_DIR, base + '.json')
    if os.path.exists(pin_file):
        with open(pin_file, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify({'pins': []})


@app.route('/api/save-pins', methods=['POST'])
def save_pins():
    """
    Save pin data.
    JSON body: { seg_pic_name, pins: [{x,y},...], clothing_type }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON body'}), 400
    seg_pic_name = data.get('seg_pic_name', '')
    pins = data.get('pins', [])
    clothing_type = data.get('clothing_type', 'upper')
    if not seg_pic_name:
        return jsonify({'error': 'Missing seg_pic_name'}), 400

    base = os.path.splitext(seg_pic_name)[0]
    pin_file = os.path.join(SEG_POSITIONING_DIR, base + '.json')
    pin_data = {
        'seg_pic_name': seg_pic_name,
        'clothing_type': clothing_type,
        'pins': pins,
        'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    try:
        os.makedirs(SEG_POSITIONING_DIR, exist_ok=True)
        with open(pin_file, 'w', encoding='utf-8') as f:
            json.dump(pin_data, f, ensure_ascii=False, indent=2)
        print(f'  Pins saved: {pin_file} ({len(pins)} pins)')
        return jsonify({'ok': True, 'pin_file': pin_file, 'count': len(pins)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/map-pins', methods=['POST'])
def map_pins():
    """
    Map clothing image to UV template using pin alignment.
    JSON body: { seg_pic_name, clothing_type }
    User pins from seg-pic/positioning/, UV pins from assets/positioning/
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON body'}), 400

    seg_pic_name = data.get('seg_pic_name', '')
    clothing_type = data.get('clothing_type', 'upper')
    if not seg_pic_name:
        return jsonify({'error': 'Missing seg_pic_name'}), 400

    # Read user pins
    base = os.path.splitext(seg_pic_name)[0]
    user_pin_file = os.path.join(SEG_POSITIONING_DIR, base + '.json')
    if not os.path.exists(user_pin_file):
        return jsonify({'error': f'Pin data not found: {user_pin_file}'}), 404

    with open(user_pin_file, 'r', encoding='utf-8') as f:
        user_pin_data = json.load(f)
    user_pins = user_pin_data.get('pins', [])
    if len(user_pins) < 2:
        return jsonify({'error': 'Need at least 2 pins'}), 400

    # Read UV pins (set by tailor.py)
    uv_pin_file = os.path.join(POSITIONING_DIR, f'{clothing_type}_pins.json')
    if not os.path.exists(uv_pin_file):
        uv_pin_file = os.path.join(POSITIONING_DIR, 'uv_pins.json')
    if not os.path.exists(uv_pin_file):
        return jsonify({'error': 'UV pin data not found. Run tailor.py first.'}), 404

    with open(uv_pin_file, 'r', encoding='utf-8') as f:
        uv_pin_data = json.load(f)
    uv_pins = uv_pin_data.get('pins', [])

    if len(uv_pins) != len(user_pins):
        return jsonify({
            'error': f'Pin count mismatch: user={len(user_pins)}, uv={len(uv_pins)}'
        }), 400

    # Load segmented image
    seg_pic_path = os.path.join(SEG_PIC_DIR, seg_pic_name)
    if not os.path.exists(seg_pic_path):
        return jsonify({'error': f'Segmented image not found: {seg_pic_path}'}), 404

    seg_img = Image.open(seg_pic_path).convert('RGBA')

    # Get UV template path
    uv_template = config.CLOTHING_TO_UV.get(clothing_type)
    if uv_template is None:
        return jsonify({'error': f'No UV template for "{clothing_type}"'}), 400

    template_path = os.path.join(_PROJECT_ROOT, 'assets', uv_template)
    if not os.path.exists(template_path):
        template_path = os.path.join(_PROJECT_ROOT, uv_template)

    try:
        print(f'\n{"="*60}')
        print(f'Pin mapping: {seg_pic_name} -> {uv_template}')
        print(f'  User pins: {len(user_pins)}, UV pins: {len(uv_pins)}')
        print(f'{"="*60}')

        texture_img = map_with_pins(
            seg_img, template_path, user_pins, uv_pins, verbose=True)

        ts = int(time.time())
        uid = uuid.uuid4().hex[:6]
        texture_name = f'{ts}_{uid}.png'
        texture_path = os.path.join(TEXTURE_DIR, texture_name)
        texture_img.save(texture_path)
        print(f'  Texture saved: {texture_path}')

        return jsonify({
            'texture_url': f'assets/Texture/{texture_name}',
            'seg_pic_url': f'assets/seg-pic/{seg_pic_name}',
            'clothing_type': clothing_type,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Mapping failed: {str(e)}'}), 500


# ================================================================
#  Unified processing pipeline
# ================================================================

@app.route('/process', methods=['POST'])
def process():
    """
    Unified processing pipeline.
    Parameters (multipart/form-data):
        photo         -- person photo (required)
        clothing_type -- upper/skirt/pants/dress (default: upper)
    Returns JSON:
        { seg_pic_url, texture_url, clothing_type }
    """
    photo = request.files.get('photo')
    if not photo:
        return jsonify({'error': 'Missing photo'}), 400

    clothing_type = request.form.get('clothing_type', 'upper')
    if clothing_type not in config.CLOTHING_TYPE_MAP:
        return jsonify({
            'error': f'Unsupported clothing type: {clothing_type}',
            'available': list(config.CLOTHING_TYPE_MAP.keys()),
        }), 400

    uv_template = config.CLOTHING_TO_UV.get(clothing_type)
    if uv_template is None:
        return jsonify({
            'error': f'No UV template for "{clothing_type}"',
            'available_types': [k for k, v in config.CLOTHING_TO_UV.items() if v is not None],
        }), 400

    template_path = os.path.join(_PROJECT_ROOT, 'assets', uv_template)
    if not os.path.exists(template_path):
        template_path = os.path.join(_PROJECT_ROOT, uv_template)

    try:
        ts = int(time.time())
        uid = uuid.uuid4().hex[:6]
        base_name = f'{ts}_{uid}'

        orig_ext = os.path.splitext(photo.filename)[1] or '.jpg'
        orig_path = os.path.join(PROCESS_DIR, base_name + orig_ext)
        photo.save(orig_path)

        print(f'\n{"="*60}')
        print(f'Process request: clothing_type={clothing_type}')
        print(f'Original photo: {orig_path}')
        print(f'{"="*60}')

        seg_result = segment_clothing_from_photo(
            orig_path, clothing_type=clothing_type,
            infer_size=config.BIREFNET_INFER_SIZE, verbose=True)
        clothing_img = seg_result['image']

        # Crop transparent margins (10px)
        clothing_img = crop_transparent_margin(clothing_img, margin=10)
        print(f'  Cropped size: {clothing_img.size}')

        seg_pic_name = base_name + '.png'
        seg_pic_path = os.path.join(SEG_PIC_DIR, seg_pic_name)
        clothing_img.save(seg_pic_path)
        print(f'  Seg pic saved: {seg_pic_path}')

        # 检查图钉：必须先在案台上定位
        user_pin_file = os.path.join(SEG_POSITIONING_DIR, base_name + '.json')
        uv_pin_file = os.path.join(POSITIONING_DIR, f'{clothing_type}_pins.json')
        if not os.path.exists(user_pin_file) or not os.path.exists(uv_pin_file):
            return jsonify({
                'error': '需要先在案台完成图钉定位。请到案台页面放置图钉后再生成纹理。',
                'stage': 'workbench',
                'seg_pic_url': f'assets/seg-pic/{seg_pic_name}',
                'seg_pic_name': seg_pic_name,
                'clothing_type': clothing_type,
            }), 400

        print(f'\n[Stage 4/4] UV texture generation via pin mapping (template={uv_template})...')
        # 通过图钉映射生成纹理（取代旧透视变换）
        texture_img = map_pins_logic(clothing_img, template_path, clothing_type, base_name)
        print('          Done')

        texture_name = base_name + '.png'
        texture_path = os.path.join(TEXTURE_DIR, texture_name)
        texture_img.save(texture_path)
        print(f'  Texture saved: {texture_path}')

        return jsonify({
            'seg_pic_url': f'assets/seg-pic/{seg_pic_name}',
            'texture_url': f'assets/Texture/{texture_name}',
            'clothing_type': clothing_type,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500


if __name__ == '__main__':
    print(f'Virtual Try-On Backend: http://{config.SERVER_HOST}:{config.SERVER_PORT}')
    app.run(
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        debug=config.SERVER_DEBUG,
        use_reloader=False,
    )
