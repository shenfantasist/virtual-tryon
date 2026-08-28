"""
ai/apply_texture.py — UV 纹理映射模块
========================================
将服装图片透视映射到 UV 模板上：
  1. 加载 UV 模板，检测 UV 岛
  2. 透视变换将服装「映射」到 UV 岛形状
  3. 主色调填充其余岛区域
"""

import os
import sys
import time

import cv2
import numpy as np
from PIL import Image


# ================================================================
#  UV 工具函数
# ================================================================

def load_uv_template(template_path):
    """加载 UV 模板，提取 island_mask 和 wireframe"""
    img = Image.open(template_path).convert('RGBA')
    arr = np.array(img)
    alpha = arr[:, :, 3]
    island_mask = alpha > 30
    wireframe = island_mask & (np.max(arr[:, :, :3], axis=2) < 128)
    return arr, island_mask, wireframe


def detect_uv_islands(island_mask):
    """连通组件检测 UV 岛，按面积降序"""
    mask_u8 = island_mask.astype(np.uint8)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        mask_u8, connectivity=4)
    islands = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        w, h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        cx, cy = centroids[i]
        islands.append({
            'label': i, 'mask': labels == i, 'area': int(area),
            'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h),
            'cx': float(cx), 'cy': float(cy),
        })
    islands.sort(key=lambda d: d['area'], reverse=True)
    return islands


def identify_front_body_island(islands, canvas_w=1024):
    """最大岛 = 正面身体"""
    if not islands:
        raise ValueError('未检测到 UV 岛')
    return max(range(len(islands)), key=lambda i: islands[i]['area'])


def extract_dominant_color(rgba, n_colors=5):
    """K-means 提取主色调 -> (R,G,B,255)"""
    alpha = rgba[:, :, 3]
    fg = alpha > 30
    pixels = rgba[fg][:, :3].astype(np.float32)
    if len(pixels) == 0:
        return (255, 255, 255, 255)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(
        pixels, n_colors, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
    unique, counts = np.unique(labels, return_counts=True)
    r, g, b = centers[unique[np.argmax(counts)]].astype(np.uint8).tolist()
    return (r, g, b, 255)


def get_fabric_bbox(fabric_img):
    """布料内容 bounding box"""
    arr = np.array(fabric_img)
    alpha = arr[:, :, 3]
    rows = np.any(alpha > 30, axis=1)
    cols = np.any(alpha > 30, axis=0)
    if not np.any(rows) or not np.any(cols):
        return 0, 0, arr.shape[1], arr.shape[0]
    y_min, y_max = np.where(rows)[0][[0, -1]]
    x_min, x_max = np.where(cols)[0][[0, -1]]
    return x_min, y_min, x_max - x_min + 1, y_max - y_min + 1


def order_points(pts):
    """将 4 个点排序为: 左上 -> 右上 -> 右下 -> 左下"""
    sorted_y = pts[np.argsort(pts[:, 1])]
    top_two = sorted_y[:2]
    bottom_two = sorted_y[2:]
    top_two = top_two[np.argsort(top_two[:, 0])]
    bottom_two = bottom_two[np.argsort(bottom_two[:, 0])]
    return np.array([
        top_two[0], top_two[1],
        bottom_two[1], bottom_two[0],
    ], dtype=np.float32)


def warp_fabric_to_island(fabric_img, island_mask, canvas_w, canvas_h):
    """
    使用透视变换将服装图片映射到 UV 岛区域。
    返回: (H, W, 4) uint8 numpy 数组
    """
    result = np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)

    fx, fy, fw, fh = get_fabric_bbox(fabric_img)
    if fw <= 0 or fh <= 0:
        return result
    fabric_cropped = np.array(fabric_img.crop((fx, fy, fx + fw, fy + fh)))

    mask_uint8 = island_mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return result

    contour = max(contours, key=cv2.contourArea)
    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    dst_pts = order_points(box)

    src_pts = np.array([
        [0, 0], [fw - 1, 0],
        [fw - 1, fh - 1], [0, fh - 1],
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(
        fabric_cropped, M, (canvas_w, canvas_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )

    warped[~island_mask] = 0
    return warped


def fill_island_on_template(template_arr, fill_arr, island_mask):
    """将 fill_arr 覆盖到 template_arr 上，仅限 island_mask 区域"""
    mask_3d = np.stack([island_mask] * 4, axis=-1)
    template_arr[mask_3d] = fill_arr[mask_3d]


def fill_island_color(template_arr, island_mask, color_rgba):
    """在 template_arr 上用纯色填充 island_mask 区域"""
    template_arr[island_mask] = color_rgba


# ================================================================
#  独立运行入口（调试用）
# ================================================================

if __name__ == '__main__':
    # 默认调试路径（移植时需修改）
    CLOTHING_PATH = r'C:\Users\shenf\Desktop\virtual_tryon\clothing\Blue-T-Shirt_no_sleeves.png'
    TEMPLATE_PATH = r'C:\Users\shenf\Desktop\virtual_tryon\UV\T-Shirt.png'
    OUTPUT_PATH   = r'C:\Users\shenf\Desktop\virtual_tryon\Texture\T-Shirt.png'

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    t_start = time.time()

    print(f'加载 UV 模板: {TEMPLATE_PATH}')
    uv_arr, island_mask, wireframe = load_uv_template(TEMPLATE_PATH)
    h, w = island_mask.shape
    print(f'  尺寸: {w} x {h}')

    base = uv_arr.copy().astype(np.uint8)

    print('检测 UV 岛...')
    islands = detect_uv_islands(island_mask)
    print(f'  检测到 {len(islands)} 个岛:')
    for idx, isl in enumerate(islands):
        print(f'    [{idx}] area={isl["area"]:>8}  bbox=({isl["x"]:>4},{isl["y"]:>4} {isl["w"]:>4}x{isl["h"]:>4})  cx={isl["cx"]:.0f}')

    front_idx = identify_front_body_island(islands, canvas_w=w)
    front_island = islands[front_idx]
    print(f'正面身体岛: index={front_idx}, area={front_island["area"]}')

    print(f'加载服装图片: {CLOTHING_PATH}')
    fabric_nobg = Image.open(CLOTHING_PATH).convert('RGBA')
    fabric_arr = np.array(fabric_nobg)
    fg_pixels = (fabric_arr[:, :, 3] > 30).sum()
    print(f'  前景像素: {fg_pixels} ({fg_pixels / fabric_arr.size * 100:.1f}%)')

    print('提取服装主色调...')
    theme_color = extract_dominant_color(fabric_arr)
    print(f'  主色调: RGB({theme_color[0]}, {theme_color[1]}, {theme_color[2]})')

    print('正面身体岛: 透视映射服装纹理 ...')
    warped_fabric = warp_fabric_to_island(fabric_nobg, front_island['mask'], w, h)
    fill_island_on_template(base, warped_fabric, front_island['mask'])
    print('  映射完成')

    for idx, isl in enumerate(islands):
        if idx == front_idx:
            continue
        print(f'  岛 [{idx}] (area={isl["area"]:>8}): 填充主题色')
        fill_island_color(base, isl['mask'], theme_color)

    result_img = Image.fromarray(base)
    result_img.save(OUTPUT_PATH)
    t_elapsed = time.time() - t_start
    file_size = os.path.getsize(OUTPUT_PATH) / 1024
    print(f'\n[OK] 完成！耗时 {t_elapsed:.1f}s')
    print(f'   输出: {OUTPUT_PATH}')
    print(f'   尺寸: {w} x {h}')
    print(f'   文件: {file_size:.1f} KB')
