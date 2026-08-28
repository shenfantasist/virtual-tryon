"""
ai/remove_sleeves.py — 袖子移除工具
======================================
用 SegFormer B2 去除已分割服装中的袖子区域。

思路：在原图上跑 SegFormer，取 class 4 (上衣) 并排除 class 14/15 (左/右臂)，
再与 BiRefNet 分割结果做交集。
"""

import os
import sys
import numpy as np
from PIL import Image

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ai.pipeline_segment import _get_segformer, SEGFORMER_CLASSES
import torch
import torch.nn.functional as F


def remove_sleeves(original_path, segmented_path, output_path):
    """
    去除已分割服装中的袖子区域。

    参数:
        original_path: 原始照片路径
        segmented_path: 已分割的服装 RGBA 图片路径
        output_path: 输出路径
    """
    original = Image.open(original_path).convert('RGB')
    segmented = Image.open(segmented_path).convert('RGBA')
    w, h = original.size

    model, processor, device = _get_segformer()
    print(f'SegFormer 已加载，设备: {device}')

    inputs = processor(images=original, return_tensors='pt')
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        logits = model(**inputs).logits
    upsampled = F.interpolate(logits, size=(h, w), mode='bilinear', align_corners=False)
    pred = upsampled.argmax(dim=1)[0].cpu().numpy()

    mask_upper = (pred == 4)
    mask_left_arm = (pred == 14)
    mask_right_arm = (pred == 15)
    mask_arms = mask_left_arm | mask_right_arm

    from cv2 import dilate, getStructuringElement, MORPH_ELLIPSE
    kernel = getStructuringElement(MORPH_ELLIPSE, (15, 15))
    mask_arms_dilated = dilate(mask_arms.astype(np.uint8), kernel) > 0

    mask_body = mask_upper & (~mask_arms_dilated)

    for name, mask in [('上衣 (class 4)', mask_upper), ('左臂 (class 14)', mask_left_arm),
                         ('右臂 (class 15)', mask_right_arm), ('身体 (上衣-手臂)', mask_body)]:
        print(f'  {name}: {mask.sum()} px ({mask.sum()/mask.size*100:.1f}%)')

    seg_arr = np.array(segmented)
    seg_alpha = seg_arr[:, :, 3] > 30

    if mask_body.shape != seg_alpha.shape:
        from cv2 import resize as cv2_resize
        mask_body = cv2_resize(mask_body.astype(np.uint8), (seg_alpha.shape[1], seg_alpha.shape[0])).astype(bool)

    final_mask = mask_body & seg_alpha
    print(f'  最终保留: {final_mask.sum()} px ({final_mask.sum()/final_mask.size*100:.1f}%)')

    out = np.array(segmented)
    out[~final_mask] = 0
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    Image.fromarray(out).save(output_path)
    print(f'\n输出: {output_path}')


if __name__ == '__main__':
    # 默认调试路径
    remove_sleeves(
        original_path=r'C:\Users\shenf\Desktop\virtual_tryon\clothing\Blue-T-Shirt.jpg',
        segmented_path=r'C:\Users\shenf\Desktop\virtual_tryon\clothing\Blue-T-Shirt_segmented.png',
        output_path=r'C:\Users\shenf\Desktop\virtual_tryon\clothing\Blue-T-Shirt_no_sleeves.png',
    )
