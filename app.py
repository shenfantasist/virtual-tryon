"""
app.py -- 启动入口
================
实际后端逻辑已迁移至 backend/server.py
AI 推理模块已迁移至 ai/
全局配置已迁移至 config.py

直接运行本文件即可启动服务器（向后兼容）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.server import app, config

if __name__ == '__main__':
    print('Virtual Try-On Backend: http://localhost:5500')
    print(f'  局域网访问: http://<主机IP>:{config.SERVER_PORT}')
    app.run(host=config.SERVER_HOST, port=config.SERVER_PORT, debug=config.SERVER_DEBUG)


from flask import Flask, request, send_file, send_from_directory, jsonify
from PIL import Image
import numpy as np
import io
import os
import sys
import apply_texture

# 将 Function Test 加入 path，以便导入 pipeline_segment
FUNCTION_TEST_DIR = os.path.join(os.path.dirname(__file__), 'Function Test')
sys.path.insert(0, FUNCTION_TEST_DIR)

from pipeline_segment import (
    segment_clothing_from_photo,
    segformer_full_labels,
    CLOTHING_TYPE_MAP,
    CLOTHING_TO_UV,
    CLOTHING_TO_MODEL,
    SEGFORMER_CLASSES,
)

app = Flask(__name__)


# ─── CORS ──────────────────────────────────────────────────────
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


# ─── UV 处理（调用 apply_texture 的透视变换）────────────────

def generate_uv_texture(clothing_rgba, template_path, verbose=True):
    """
    将分割后的服装图片映射为 UV 纹理（透视变换模式）。

    参数:
        clothing_rgba: PIL Image (RGBA) — 分割后的服装
        template_path: UV 模板路径

    返回:
        texture_img: PIL Image (RGBA) — UV 纹理图
    """
    _, island_mask, _ = apply_texture.load_uv_template(template_path)
    h, w = island_mask.shape

    islands = apply_texture.detect_uv_islands(island_mask)
    if len(islands) < 2:
        raise ValueError(f'UV 模板岛数量不足（需要 ≥ 2，实际 {len(islands)}）')

    front_idx = apply_texture.identify_front_body_island(islands, canvas_w=w)
    front_island = islands[front_idx]
    if verbose:
        print(f'  UV: {len(islands)} islands, front=[{front_idx}] area={front_island["area"]}')

    # 正面身体岛 → 透视变换贴图
    full_result = apply_texture.warp_fabric_to_island(
        clothing_rgba, front_island['mask'], w, h)

    # 其余岛 → 主色调纯色填充
    clothing_arr = np.array(clothing_rgba)
    theme_color = apply_texture.extract_dominant_color(clothing_arr)
    if verbose:
        print(f'  Theme color: RGB({theme_color[0]},{theme_color[1]},{theme_color[2]})')

    for idx, isl in enumerate(islands):
        if idx == front_idx:
            continue
        full_result[isl['mask']] = theme_color

    return Image.fromarray(full_result.astype(np.uint8))


# ─── 路由 ──────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/models/<path:filename>')
def models(filename):
    return send_from_directory('models', filename)


@app.route('/Texture/<path:filename>')
def texture(filename):
    return send_from_directory('Texture', filename)


@app.route('/clothing/<path:filename>')
def clothing(filename):
    return send_from_directory('clothing', filename)


@app.route('/api/clothing-types')
def clothing_types():
    """返回前端可选的服装类型列表"""
    types = []
    for key, class_ids in CLOTHING_TYPE_MAP.items():
        names = [SEGFORMER_CLASSES[c] for c in class_ids]
        types.append({
            'id': key,
            'label': '/'.join(names),
            'class_ids': list(class_ids),
            'uv_template': CLOTHING_TO_UV.get(key),
            'model_3d': CLOTHING_TO_MODEL.get(key),
        })
    return jsonify(types)


@app.route('/api/analyze', methods=['POST'])
def analyze():
    """
    分析上传的照片，返回 SegFormer 检测到的服装类别分布。
    前端可据此自动推荐 target clothing type。
    """
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
                'name': SEGFORMER_CLASSES.get(cls_id, f'class_{cls_id}'),
                'pixels': cnt,
                'ratio': round(cnt / total * 100, 1),
            })

        # 自动推荐服装类型
        clothing_classes = {4: 'upper', 5: 'skirt', 6: 'pants', 7: 'dress'}
        suggestion = None
        for cls_id in [4, 7, 5, 6]:  # 优先上衣和连衣裙
            if cls_id in stats and stats[cls_id] > 1000:
                suggestion = clothing_classes[cls_id]
                break

        return jsonify({
            'classes': classes,
            'suggestion': suggestion,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'error': str(e)}, 500


@app.route('/process', methods=['POST'])
def process():
    """
    统一处理管线

    参数 (multipart/form-data):
        photo         — 人物照片 (必需)
        clothing_type — 目标服装类型: upper/skirt/pants/dress (默认 upper)

    流程:
        1. pipeline_segment: BiRefNet + SegFormer → 服装 RGBA
        2. UV 纹理生成 → 贴图 PNG
        3. 返回 PNG
    """
    photo = request.files.get('photo')
    if not photo:
        return {'error': '缺少照片 (photo)'}, 400

    clothing_type = request.form.get('clothing_type', 'upper')
    if clothing_type not in CLOTHING_TYPE_MAP:
        return {'error': f'不支持的服装类型: {clothing_type}，可选: {list(CLOTHING_TYPE_MAP.keys())}'}, 400

    # 检查是否有对应的 UV 模板
    uv_template = CLOTHING_TO_UV.get(clothing_type)
    if uv_template is None:
        return {
            'error': f'「{clothing_type}」暂无对应的 UV 模板，请选择其他服装类型',
            'available_types': [k for k, v in CLOTHING_TO_UV.items() if v is not None],
        }, 400

    template_path = os.path.join(os.path.dirname(__file__), uv_template)

    try:
        # 保存上传的临时文件
        tmp_path = os.path.join(os.path.dirname(__file__), '_tmp_upload.jpg')
        photo.save(tmp_path)

        # ── Stage 1-3: AI 分割管线 ──
        print(f'\n{"="*60}')
        print(f'处理请求: clothing_type={clothing_type}')
        print(f'{"="*60}')

        seg_result = segment_clothing_from_photo(
            tmp_path,
            clothing_type=clothing_type,
            infer_size=1024,
            verbose=True,
        )
        clothing_img = seg_result['image']

        # ── Stage 4: UV 纹理生成 ──
        print(f'\n[Stage 4/4] UV 纹理生成 (template={uv_template})...')
        texture_img = generate_uv_texture(clothing_img, template_path)
        print('          Done')

        # 清理临时文件
        try:
            os.remove(tmp_path)
        except OSError:
            pass

        # 返回 PNG
        img_io = io.BytesIO()
        texture_img.save(img_io, 'PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'error': f'处理失败: {str(e)}'}, 500


if __name__ == '__main__':
    print('Virtual Try-On Backend: http://localhost:5500')
    app.run(host='0.0.0.0', port=5000, debug=True)
