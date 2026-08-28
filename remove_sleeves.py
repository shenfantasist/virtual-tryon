"""
remove_sleeves.py -- 向后兼容入口
===================================
实际模块已迁移至 ai/remove_sleeves.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.remove_sleeves import remove_sleeves
import os
import sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Function Test'))
from pipeline_segment import _get_segformer, SEGFORMER_CLASSES
import torch
import torch.nn.functional as F

INPUT_PATH  = r'C:\Users\shenf\Desktop\virtual_tryon\clothing\Blue-T-Shirt.jpg'
SEGMENTED_PATH = r'C:\Users\shenf\Desktop\virtual_tryon\clothing\Blue-T-Shirt_segmented.png'
OUTPUT_PATH = r'C:\Users\shenf\Desktop\virtual_tryon\clothing\Blue-T-Shirt_no_sleeves.png'

def main():
    original = Image.open(INPUT_PATH).convert('RGB')
    segmented = Image.open(SEGMENTED_PATH).convert('RGBA')
    w, h = original.size

    model, processor, device = _get_segformer()
    print(f'SegFormer 已加载，设备: {device}')

    # SegFormer 推理
    inputs = processor(images=original, return_tensors='pt')
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        logits = model(**inputs).logits
    upsampled = F.interpolate(logits, size=(h, w), mode='bilinear', align_corners=False)
    pred = upsampled.argmax(dim=1)[0].cpu().numpy()

    # 上衣 mask（排除手臂区域）
    mask_upper = (pred == 4)   # Upper-clothes
    mask_left_arm  = (pred == 14)  # Left-arm
    mask_right_arm = (pred == 15)  # Right-arm
    mask_arms = mask_left_arm | mask_right_arm

    # 上衣身体部分 = 上衣 - 手臂（膨胀手臂区域做容错）
    from cv2 import dilate, getStructuringElement, MORPH_ELLIPSE
    kernel = getStructuringElement(MORPH_ELLIPSE, (15, 15))
    mask_arms_dilated = dilate(mask_arms.astype(np.uint8), kernel) > 0

    mask_body = mask_upper & (~mask_arms_dilated)

    for name, mask in [('上衣 (class 4)', mask_upper), ('左臂 (class 14)', mask_left_arm),
                         ('右臂 (class 15)', mask_right_arm), ('身体 (上衣-手臂)', mask_body)]:
        print(f'  {name}: {mask.sum()} px ({mask.sum()/mask.size*100:.1f}%)')

    # 与已有分割结果交集
    seg_arr = np.array(segmented)
    seg_alpha = seg_arr[:, :, 3] > 30

    # 调整尺寸
    if mask_body.shape != seg_alpha.shape:
        from cv2 import resize as cv2_resize
        mask_body = cv2_resize(mask_body.astype(np.uint8), (seg_alpha.shape[1], seg_alpha.shape[0])).astype(bool)

    final_mask = mask_body & seg_alpha
    print(f'  最终保留: {final_mask.sum()} px ({final_mask.sum()/final_mask.size*100:.1f}%)')

    # 生成输出
    out = np.array(segmented)
    out[~final_mask] = 0
    Image.fromarray(out).save(OUTPUT_PATH)
    print(f'\n输出: {OUTPUT_PATH}')

if __name__ == '__main__':
    main()
