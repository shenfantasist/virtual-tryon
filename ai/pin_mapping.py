"""
ai/pin_mapping.py — 图钉对齐映射算法
=========================================
基于用户放置的图钉（定位点）将分割图对齐到 UV 模板：

  1. 裁剪透明区域 (crop_transparent_margin)
  2. 通过图钉对应关系计算单应（透视）变换（图钉不足 4 个时回退到仿射）
  3. 微调边界
  4. 为其余岛填充主色调纯色

默认使用单应变换（warpPerspective），比仿射更能处理非平面偏差。
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import cv2
import numpy as np
from PIL import Image


# ================================================================
#  图片裁剪：移除透明区域 + margin
# ================================================================

def crop_transparent_margin(img, margin=10):
    """
    裁剪 RGBA 图片的透明区域，保留内容区域 + margin 像素。

    参数:
        img:    PIL Image (RGBA) 或 numpy array (H, W, 4)
        margin: 边距像素数（默认 10）

    返回:
        PIL Image (RGBA) — 已裁剪的图片
    """
    if isinstance(img, np.ndarray):
        arr = img
    else:
        arr = np.array(img)

    if arr.ndim == 2:
        return Image.fromarray(arr)

    alpha = arr[:, :, 3]
    rows = np.any(alpha > 10, axis=1)
    cols = np.any(alpha > 10, axis=0)

    if not np.any(rows) or not np.any(cols):
        # 全透明 → 返回原始图片
        return Image.fromarray(arr) if isinstance(img, np.ndarray) else img

    y_min, y_max = np.where(rows)[0][[0, -1]]
    x_min, x_max = np.where(cols)[0][[0, -1]]

    # 加 margin，但不超出图片边界
    h, w = arr.shape[:2]
    y_min = max(0, y_min - margin)
    y_max = min(h - 1, y_max + margin)
    x_min = max(0, x_min - margin)
    x_max = min(w - 1, x_max + margin)

    cropped = arr[y_min:y_max + 1, x_min:x_max + 1]
    return Image.fromarray(cropped)


# ================================================================
#  图钉坐标系
# ================================================================

def pin_list_to_array(pins):
    """
    将图钉列表 [{x, y}, ...] 转换为 (N, 2) float32 数组。
    """
    return np.array([[p['x'], p['y']] for p in pins], dtype=np.float32)


# ================================================================
#  仿射变换：基于图钉的最优刚性对齐
# ================================================================

def compute_alignment_transform(src_pins, dst_pins):
    """
    计算从 src_pins → dst_pins 的最优仿射变换。
    使用最小二乘法求解：dst = src @ A^T + b

    参数:
        src_pins: (N, 2) float32 — 分割图上的图钉坐标
        dst_pins: (N, 2) float32 — UV 模板上的图钉坐标

    返回:
        M:    (2, 3) float64 — 仿射变换矩阵（cv2 格式）
        error: float — 平均重投影误差（像素）
    """
    n = len(src_pins)
    if n < 2:
        raise ValueError(f'至少需要 2 个图钉进行对齐，当前只有 {n} 个')

    if n == 2:
        # 两点：计算缩放 + 旋转 + 平移
        src_vec = src_pins[1] - src_pins[0]
        dst_vec = dst_pins[1] - dst_pins[0]

        src_len = np.linalg.norm(src_vec)
        dst_len = np.linalg.norm(dst_vec)
        if src_len < 1e-6:
            scale = 1.0
        else:
            scale = dst_len / src_len

        src_angle = np.arctan2(src_vec[1], src_vec[0])
        dst_angle = np.arctan2(dst_vec[1], dst_vec[0])
        angle = dst_angle - src_angle

        cos_a = scale * np.cos(angle)
        sin_a = scale * np.sin(angle)

        M = np.array([
            [cos_a, -sin_a, dst_pins[0][0] - (cos_a * src_pins[0][0] - sin_a * src_pins[0][1])],
            [sin_a,  cos_a, dst_pins[0][1] - (sin_a * src_pins[0][0] + cos_a * src_pins[0][1])],
        ], dtype=np.float64)

        # 计算误差
        transformed = cv2.transform(src_pins.reshape(1, -1, 2), M)[0]
        error = float(np.mean(np.linalg.norm(transformed - dst_pins, axis=1)))
        return M, error

    # 3+ 个点：最小二乘拟合仿射变换
    # dst = src @ A^T + b  →  solve for A, b
    # 使用 cv2.estimateAffinePartial2D（带 RANSAC，对异常值更鲁棒）
    # 或简单最小二乘
    src = src_pins.astype(np.float64)
    dst = dst_pins.astype(np.float64)

    if n >= 3:
        # 使用最小二乘法求解
        # 构建方程组: [x, y, 1] @ [a11, a12, a21, a22, tx, ty] = [u, v]
        A = np.column_stack([src, np.ones(n)])  # (N, 3)
        # 求解 X: A @ X = dst
        # X = (A^T A)^{-1} A^T dst
        X, residuals, rank, sv = np.linalg.lstsq(A, dst, rcond=None)
        # X: (3, 2), M = [[a11, a12, tx], [a21, a22, ty]]
        M = X.T  # (2, 3)
    else:
        # 两个点的 fallback（不应该到这里）
        M = np.eye(2, 3, dtype=np.float64)

    # 计算误差
    transformed = cv2.transform(src_pins.reshape(1, -1, 2), M)[0]
    error = float(np.mean(np.linalg.norm(transformed - dst_pins, axis=1)))
    return M, error


def apply_transform_to_image(src_img, M, canvas_size, border_value=(0, 0, 0)):
    """
    将图片应用仿射变换到画布上。

    参数:
        src_img:      PIL Image (RGBA)
        M:            (2, 3) 仿射变换矩阵
        canvas_size:  (W, H) 输出画布大小
        border_value: 边界填充色 (B, G, R)，默认黑色

    返回:
        numpy array (H, W, 4) uint8
    """
    w, h = canvas_size
    arr = np.array(src_img)

    # 分离颜色和 alpha
    bgr = arr[:, :, :3]
    alpha = arr[:, :, 3]

    # 变换颜色
    warped_bgr = cv2.warpAffine(
        bgr, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )

    # 变换 alpha
    warped_alpha = cv2.warpAffine(
        alpha, M, (w, h),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    result = np.zeros((h, w, 4), dtype=np.uint8)
    result[:, :, :3] = warped_bgr
    result[:, :, 3] = warped_alpha
    return result


# ================================================================
#  单应变换：基于图钉的透视对齐（默认方式）
# ================================================================

def compute_homography_transform(src_pins, dst_pins):
    """
    计算从 src_pins → dst_pins 的单应（透视）变换。
    使用 cv2.findHomography 最小二乘求解（method=0，无 RANSAC）。

    参数:
        src_pins: (N, 2) float32 — 分割图上的图钉坐标
        dst_pins: (N, 2) float32 — UV 模板上的图钉坐标

    返回:
        H:      (3, 3) float64 — 单应矩阵
        error:  float — 平均重投影误差（像素）
    """
    if len(src_pins) < 4:
        raise ValueError(
            f'单应变换至少需要 4 个图钉，当前只有 {len(src_pins)} 个')

    H, _ = cv2.findHomography(src_pins, dst_pins, method=0)

    # 重投影误差（用 dst -> src 再投影回 dst，或直接正向投影）
    # 把 src 投影到 dst 空间比较
    src = np.hstack([src_pins, np.ones((len(src_pins), 1))]).T  # (3, N)
    proj = H @ src
    proj = proj[:2] / proj[2]
    error = float(np.mean(np.linalg.norm(proj.T - dst_pins, axis=1)))
    return H, error


def apply_homography_to_image(src_img, H, canvas_size, border_value=(0, 0, 0)):
    """
    将图片应用单应（透视）变换到画布上。

    参数:
        src_img:      PIL Image (RGBA)
        H:            (3, 3) 单应矩阵
        canvas_size:  (W, H) 输出画布大小
        border_value: 边界填充色 (B, G, R)，默认黑色

    返回:
        numpy array (H, W, 4) uint8
    """
    w, h = canvas_size
    arr = np.array(src_img)

    bgr = arr[:, :, :3]
    alpha = arr[:, :, 3]

    warped_bgr = cv2.warpPerspective(
        bgr, H, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )
    warped_alpha = cv2.warpPerspective(
        alpha, H, (w, h),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    result = np.zeros((h, w, 4), dtype=np.uint8)
    result[:, :, :3] = warped_bgr
    result[:, :, 3] = warped_alpha
    return result


# ================================================================
#  主入口：图钉对齐映射
# ================================================================

def map_with_pins(seg_img, uv_template_path, user_pins, uv_pins,
                  dominant_color=None, verbose=True):
    """
    通过图钉对齐将分割图映射到 UV 模板。

    参数:
        seg_img:         分割后的服装图片 (PIL Image, RGBA)
        uv_template_path: UV 模板图片路径
        user_pins:       分割图上的图钉列表 [{x, y}, ...]
        uv_pins:         UV 模板上的图钉列表 [{x, y}, ...]
        dominant_color:  可选的主色调 (R, G, B)，None 则自动提取
        verbose:         是否打印进度

    返回:
        PIL Image (RGBA) — 映射后的 UV 纹理
    """
    # 加载 UV 模板
    uv_img = Image.open(uv_template_path).convert('RGBA')
    uv_arr = np.array(uv_img)
    uv_h, uv_w = uv_arr.shape[:2]

    # UV 岛检测
    from ai.apply_texture import load_uv_template, detect_uv_islands, extract_dominant_color

    _, island_mask, _ = load_uv_template(uv_template_path)
    islands = detect_uv_islands(island_mask)
    if len(islands) < 2:
        raise ValueError(f'UV 模板岛数量不足（需要 >= 2，实际 {len(islands)}）')

    # 最大岛 = 主岛（正面身体）
    main_island_idx = 0  # detect_uv_islands 已按面积降序排列
    main_island = islands[main_island_idx]

    if verbose:
        print(f'  UV: {uv_w}x{uv_h}, {len(islands)} islands, main=[{main_island_idx}]')

    # 转换图钉坐标（统一为像素坐标）
    # 前端保存的用户图钉是归一化坐标 (0~1)，需要乘以分割图尺寸还原为像素；
    # UV 图钉（tailor.py）本身就是绝对像素坐标。
    seg_w, seg_h = seg_img.size
    src_pts = pin_list_to_array(user_pins)
    src_pts[:, 0] *= seg_w
    src_pts[:, 1] *= seg_h
    dst_pts = pin_list_to_array(uv_pins)

    # 计算变换：默认单应（透视），图钉不足 4 个时回退到仿射
    use_homography = len(src_pts) >= 4

    # ── 提前提取主色调（作为映射边框颜色，避免产生黑色暗边）──
    seg_arr = np.array(seg_img)
    if dominant_color is None:
        theme = extract_dominant_color(seg_arr)
    else:
        theme = (*dominant_color, 255)
    if verbose:
        print(f'  主色调: RGB({theme[0]},{theme[1]},{theme[2]})')

    if use_homography:
        H, error = compute_homography_transform(src_pts, dst_pts)
        if verbose:
            print(f'  单应变换: 误差={error:.2f}px')
        # 应用变换到分割图（边框用主色调，避免黑色溢出）
        warped = apply_homography_to_image(seg_img, H, (uv_w, uv_h), border_value=theme[:3])
    else:
        M, error = compute_alignment_transform(src_pts, dst_pts)
        if verbose:
            print(f'  仿射变换(回退): 误差={error:.2f}px')
        # 应用变换到分割图
        warped = apply_transform_to_image(seg_img, M, (uv_w, uv_h), border_value=theme[:3])
    if verbose:
        fg_warped = (warped[:, :, 3] > 10).sum()
        print(f'  变换后前景像素: {fg_warped}')

    # 结果画布
    result = np.zeros((uv_h, uv_w, 4), dtype=np.uint8)

    # 先拷贝 UV 模板的背景
    result[:] = uv_arr

    # ── 所有 UV 岛均填充主色调（含主岛）──
    for idx, isl in enumerate(islands):
        if verbose:
            print(f'  岛 [{idx}] (area={isl["area"]:>8}): 填充主色调')
        result[isl['mask']] = theme

    # ── 将服装映射到主岛上 ──
    main_mask = main_island['mask']
    # 只在 warped 有内容（不透明）的地方覆盖服装纹理，其余保留主题色，
    # 避免透明区域把已填好的主岛颜色覆盖成透明黑。
    content = (warped[:, :, 3] > 10) & main_mask
    result[content] = warped[content]

    # ── 微调边界 ──
    # 对服装内容边缘进行羽化混合，避免硬边界；
    # 因 warp 边框已用主色调填充，边缘过渡自然且不会产生黑色暗边。
    result = _feather_island_boundary(result, warped, content, feather_px=3)

    return Image.fromarray(result)


def _feather_island_boundary(result, warped, content_mask, feather_px=3):
    """
    对主岛上的服装内容边缘进行羽化混合，让变换后的图像边缘更自然。
    content_mask: 服装内容（不透明）像素所在位置。
    边缘 (dist=0) 保留主题色，内部 (dist>=feather_px) 使用服装纹理。
    """
    # 创建距离场（基于服装内容区域，而非整个主岛）
    mask_u8 = content_mask.astype(np.uint8) * 255
    dist = cv2.distanceTransform(mask_u8, cv2.DIST_L2, 5)

    # 羽化区域：距离 <= feather_px 的像素进行 alpha 混合
    feather_mask = np.clip(dist / max(feather_px, 1), 0, 1).astype(np.float32)

    result_float = result.astype(np.float32)
    warped_float = warped.astype(np.float32)

    for c in range(4):
        result_float[:, :, c] = (
            result_float[:, :, c] * (1 - feather_mask) +
            warped_float[:, :, c] * feather_mask
        )

    return result_float.astype(np.uint8)


# ================================================================
#  独立运行入口（调试用）
# ================================================================

if __name__ == '__main__':
    import json

    print('=== pin_mapping.py 独立测试 ===')
    print('用法: 此模块作为库被 backend/server.py 和 tailor.py 导入')
    print('直接运行仅用于测试裁剪函数')

    # 测试裁剪
    test_img_path = os.path.join(_PROJECT_ROOT, 'assets', 'seg-pic')
    pics = [f for f in os.listdir(test_img_path) if f.endswith('.png')]
    if pics:
        p = os.path.join(test_img_path, pics[0])
        print(f'\n测试裁剪: {p}')
        img = Image.open(p)
        print(f'  原始尺寸: {img.size}')
        cropped = crop_transparent_margin(img, margin=10)
        print(f'  裁剪后尺寸: {cropped.size}')

        out_path = os.path.join(test_img_path, 'test_cropped.png')
        cropped.save(out_path)
        print(f'  已保存: {out_path}')
    else:
        print('  无 seg-pic 可测试')
