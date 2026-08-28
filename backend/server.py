"""
backend/server.py — Flask 后端服务
====================================
统一管线：BiRefNet 前景分割 -> SegFormer B2 服装分割 -> UV 纹理生成 -> Three.js 展示

端点:
  GET  /                 前端页面
  GET  /models/<path>    模型/纹理文件
  GET  /api/clothing-types  返回可选的服装类型列表
  POST /api/analyze         分析照片中的服装类别分布
  POST /process             统一处理管线
"""

import io
import os
import sys

# 将项目根目录加入 path，以便导入 config 和 ai 模块
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

app = Flask(__name__)


# --- CORS ---
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


# --- UV 处理 ---

def generate_uv_texture(clothing_rgba, template_path, verbose=True):
    """将分割后的服装图片映射为 UV 纹理（透视变换模式）"""
    _, island_mask, _ = load_uv_template(template_path)
    h, w = island_mask.shape

    islands = detect_uv_islands(island_mask)
    if len(islands) < 2:
        raise ValueError(f'UV 模板岛数量不足（需要 >= 2，实际 {len(islands)}）')

    front_idx = identify_front_body_island(islands, canvas_w=w)
    front_island = islands[front_idx]
    if verbose:
        print(f'  UV: {len(islands)} islands, front=[{front_idx}] area={front_island["area"]}')

    full_result = warp_fabric_to_island(
        clothing_rgba, front_island['mask'], w, h)

    clothing_arr = np.array(clothing_rgba)
    theme_color = extract_dominant_color(clothing_arr)
    if verbose:
        print(f'  Theme color: RGB({theme_color[0]},{theme_color[1]},{theme_color[2]})')

    for idx, isl in enumerate(islands):
        if idx == front_idx:
            continue
        full_result[isl['mask']] = theme_color

    return Image.fromarray(full_result.astype(np.uint8))


# --- 路由 ---

@app.route('/')
def index():
    return send_from_directory(_PROJECT_ROOT, 'index.html')


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
    """返回前端可选的服装类型列表"""
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
    """分析上传照片，返回 SegFormer 检测到的服装类别分布"""
    photo = request.files.get('photo')
    if not photo:
        return {'error': '缺少图片'}, 400

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


@app.route('/process', methods=['POST'])
def process():
    """
    统一处理管线
    参数 (multipart/form-data):
        photo         -- 人物照片 (必需)
        clothing_type -- 目标服装类型: upper/skirt/pants/dress (默认 upper)
    """
    photo = request.files.get('photo')
    if not photo:
        return {'error': '缺少照片 (photo)'}, 400

    clothing_type = request.form.get('clothing_type', 'upper')
    if clothing_type not in config.CLOTHING_TYPE_MAP:
        return {'error': f'不支持的服装类型: {clothing_type}，可选: {list(config.CLOTHING_TYPE_MAP.keys())}'}, 400

    uv_template = config.CLOTHING_TO_UV.get(clothing_type)
    if uv_template is None:
        return {
            'error': f'"{clothing_type}" 暂无对应的 UV 模板，请选择其他服装类型',
            'available_types': [k for k, v in config.CLOTHING_TO_UV.items() if v is not None],
        }, 400

    template_path = os.path.join(_PROJECT_ROOT, 'assets', uv_template)
    # 兼容旧路径：如果 assets/ 下没有，尝试根目录
    if not os.path.exists(template_path):
        template_path = os.path.join(_PROJECT_ROOT, uv_template)

    try:
        tmp_path = os.path.join(_PROJECT_ROOT, '_tmp_upload.jpg')
        photo.save(tmp_path)

        print(f'\n{"="*60}')
        print(f'处理请求: clothing_type={clothing_type}')
        print(f'{"="*60}')

        seg_result = segment_clothing_from_photo(
            tmp_path,
            clothing_type=clothing_type,
            infer_size=config.BIREFNET_INFER_SIZE,
            verbose=True,
        )
        clothing_img = seg_result['image']

        print(f'\n[Stage 4/4] UV 纹理生成 (template={uv_template})...')
        texture_img = generate_uv_texture(clothing_img, template_path)
        print('          Done')

        try:
            os.remove(tmp_path)
        except OSError:
            pass

        img_io = io.BytesIO()
        texture_img.save(img_io, 'PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'error': f'处理失败: {str(e)}'}, 500


if __name__ == '__main__':
    print(f'Virtual Try-On Backend: http://{config.SERVER_HOST}:{config.SERVER_PORT}')
    app.run(
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        debug=config.SERVER_DEBUG,
    )
