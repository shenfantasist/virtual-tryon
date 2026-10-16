"""
可视化：分割图 与 带图钉的 UV 图 叠放对比。

对比两种映射方式：
  - 仿射变换（pin_mapping.py 当前逻辑）
  - 单应变换（cv2.findHomography）

每种方式生成左/右两图：
  左图：seg-pic 为底，UV 主岛（逆变换回 seg 空间）叠加在上。
  右图：UV 模板为底，分割图（变换到 UV 空间）叠加在 UV 主岛上。

最终输出一张 2x2 网格 PNG。
"""

import os
import sys
import json

_PROJECT_ROOT = r"C:\Users\shenf\Desktop\virtual_tryon"
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import cv2
import numpy as np
from PIL import Image, ImageDraw

from ai.pin_mapping import (
    pin_list_to_array,
    compute_alignment_transform,
    apply_transform_to_image,
)
from ai.apply_texture import load_uv_template, detect_uv_islands


SEG_JSON = r"C:\Users\shenf\Desktop\virtual_tryon\assets\seg-pic\positioning\1789281930_03625e.json"
UV_JSON = r"C:\Users\shenf\Desktop\virtual_tryon\assets\positioning\upper_pins.json"
OUT = r"C:\Users\shenf\Desktop\virtual_tryon\mapping_compare.png"


def warp_homography(img, H, size):
    """用单应矩阵 H 将 RGBA 图片变换到 (w, h) 画布。"""
    w, h = size
    arr = np.array(img)
    bgr = arr[:, :, :3]
    alpha = arr[:, :, 3]
    warped_bgr = cv2.warpPerspective(
        bgr, H, (w, h), flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    warped_alpha = cv2.warpPerspective(
        alpha, H, (w, h), flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    result = np.zeros((h, w, 4), dtype=np.uint8)
    result[:, :, :3] = warped_bgr
    result[:, :, 3] = warped_alpha
    return result


def compute_homography(src_pts, dst_pts):
    """src -> dst 单应矩阵（最小二乘，无 RANSAC），返回 (H, 重投影误差)。"""
    H, _ = cv2.findHomography(src_pts, dst_pts, method=0)
    ones = np.hstack([dst_pts, np.ones((len(dst_pts), 1))]).T  # (3, N)
    mapped = np.linalg.inv(H) @ ones
    mapped = mapped[:2] / mapped[2]
    err = float(np.mean(np.linalg.norm(mapped.T - src_pts, axis=1)))
    return H, err


def _draw_pins(img, pts, radius=8, color=(0, 255, 0), width=4):
    """在 PIL 图上绘制图钉点（绿色圆+中心点）。"""
    draw = ImageDraw.Draw(img)
    for (x, y) in pts:
        draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                     outline=color, width=width)
        draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=color)


def build_pair(transform, label, seg_img, uv_arr, main_mask, wireframe,
               seg_w, seg_h, uv_w, uv_h, src_pts, dst_pts):
    """给定变换函数 transform(img, size) 生成 (左图, 右图, 标签)。

    左图：分割图为底，UV 主岛（橙色半透明填充 + 红色粗线框）叠在上。
    右图：UV 模板为底，完整分割图叠在上，UV 主岛线框再画在最上层。
    两种图都绘制图钉点（绿点）以观察对齐。
    """
    seg_np = np.array(seg_img)

    # 加厚线框，避免 warp / 缩小后线条消失
    kern = np.ones((5, 5), np.uint8)
    wire_thick = cv2.dilate(wireframe.astype(np.uint8), kern).astype(bool)

    # --- 右图：UV 为底，完整分割图叠上，再画 UV 主岛线框与图钉 ---
    warped = transform(seg_img, (uv_w, uv_h))
    right = uv_arr.copy()
    seg_content = warped[:, :, 3] > 10
    right[seg_content] = warped[seg_content]
    # UV 主岛线框（红）画在最上层，便于观察边界对齐
    right[wire_thick] = (255, 60, 60, 255)
    right_img = Image.fromarray(right)
    _draw_pins(right_img, dst_pts)

    # --- 左图：分割图为底，UV 主岛半透明填充+粗线框叠上 ---
    island_rgba = np.zeros((uv_h, uv_w, 4), dtype=np.uint8)
    island_rgba[main_mask] = (255, 140, 0, 110)     # 橙色半透明主岛
    island_rgba[wire_thick] = (255, 40, 40, 255)    # 红色粗线框
    island_img = Image.fromarray(island_rgba)
    warped_island = transform(island_img, (seg_w, seg_h))

    left = seg_np.astype(np.float32).copy()
    a = warped_island[:, :, 3:4].astype(np.float32) / 255.0
    left[:, :, :3] = left[:, :, :3] * (1 - a) + warped_island[:, :, :3] * a
    left_img = Image.fromarray(left.astype(np.uint8))
    _draw_pins(left_img, src_pts)

    return left_img, right_img, label


def main():
    with open(SEG_JSON, 'r', encoding='utf-8') as f:
        seg_data = json.load(f)
    with open(UV_JSON, 'r', encoding='utf-8') as f:
        uv_data = json.load(f)

    seg_name = seg_data['seg_pic_name']
    seg_path = os.path.join(_PROJECT_ROOT, 'assets', 'seg-pic', seg_name)
    seg_img = Image.open(seg_path).convert('RGBA')
    seg_w, seg_h = seg_img.size

    uv_path = uv_data['uv_template']
    uv_img = Image.open(uv_path).convert('RGBA')
    uv_arr = np.array(uv_img)
    uv_h, uv_w = uv_arr.shape[:2]

    _, island_mask, wireframe = load_uv_template(uv_path)
    islands = detect_uv_islands(island_mask)
    main_island = islands[0]
    main_mask = main_island['mask']
    print(f"seg={seg_w}x{seg_h}  uv={uv_w}x{uv_h}  islands={len(islands)} main_area={main_island['area']}")

    # 统一坐标
    src_pts = pin_list_to_array(seg_data['pins'])
    src_pts[:, 0] *= seg_w
    src_pts[:, 1] *= seg_h
    dst_pts = pin_list_to_array(uv_data['pins'])

    # 仿射
    M_aff, err_aff = compute_alignment_transform(src_pts, dst_pts)
    inv_M_aff = cv2.invertAffineTransform(M_aff)
    print(f"仿射误差: {err_aff:.2f}px")

    def affine_transform(img, size):
        # 依据源图尺寸选矩阵：seg 尺寸的图 → 前向(seg→UV)；UV 尺寸的图 → 逆矩阵(UV→seg)
        forward = img.size == (seg_w, seg_h)
        M = M_aff if forward else inv_M_aff
        return apply_transform_to_image(img, M, size)

    # 单应
    H_hom, err_hom = compute_homography(src_pts, dst_pts)
    inv_H_hom = np.linalg.inv(H_hom)
    print(f"单应误差: {err_hom:.2f}px")

    def homography_transform(img, size):
        forward = img.size == (seg_w, seg_h)
        H = H_hom if forward else inv_H_hom
        return warp_homography(img, H, size)

    pairs = [
        build_pair(affine_transform, f"仿射 (误差 {err_aff:.1f}px)",
                   seg_img, uv_arr, main_mask, wireframe,
                   seg_w, seg_h, uv_w, uv_h, src_pts, dst_pts),
        build_pair(homography_transform, f"单应 (误差 {err_hom:.1f}px)",
                   seg_img, uv_arr, main_mask, wireframe,
                   seg_w, seg_h, uv_w, uv_h, src_pts, dst_pts),
    ]

    # ---- 2x2 网格 ----
    pad, label_h = 16, 44
    scale = 0.6
    cells = []
    for left, right, label in pairs:
        lc = left.resize((int(left.width * scale), int(left.height * scale)))
        rc = right.resize((int(right.width * scale), int(right.height * scale)))
        cells.append((lc, rc, label))

    cw = max(max(l.width, r.width) for l, r, _ in cells)
    ch = max(max(l.height, r.height) for l, r, _ in cells)
    H_total = label_h + ch * 2 + pad * 5
    W_total = cw * 2 + pad * 3

    canvas = Image.new('RGB', (W_total, H_total), (245, 245, 245))
    draw = ImageDraw.Draw(canvas)

    def place(img, col, row):
        x = pad + col * (cw + pad)
        y = label_h + row * (ch + pad)
        canvas.paste(img, (x, y))
        return x

    # 列标题
    draw.text((pad, 2), "左: 分割图为底 / UV主岛在上", fill=(0, 0, 0))
    draw.text((pad * 2 + cw, 2), "右: UV模板为底 / 分割图在上", fill=(0, 0, 0))

    for row, (lc, rc, label) in enumerate(cells):
        x = place(lc, 0, row)
        draw.text((x, label_h - 26 + row * (ch + pad) - 6), label, fill=(0, 0, 0))
        place(rc, 1, row)

    canvas.save(OUT)
    print(f"已保存: {OUT}")


if __name__ == '__main__':
    main()