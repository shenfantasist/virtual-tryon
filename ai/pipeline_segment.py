"""
ai/pipeline_segment.py — 服装分割管线
=======================================
统一的 AI 分割管线，将人物照片中的目标服装提取出来：

  Stage 1: BiRefNet 高精度前景分割 -> 人物 alpha 通道
  Stage 2: SegFormer B2 语义分割 -> 目标服装类别 mask
  融合 + 裁剪 -> 仅保留目标服装的 RGBA 图片

用法:
    from ai.pipeline_segment import segment_clothing_from_photo
    result = segment_clothing_from_photo('person.jpg', clothing_type='upper')
"""

import os
import sys

# 将项目根目录加入 path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import numpy as np
from PIL import Image

import config

# BiRefNet 代码目录加入 path
sys.path.insert(0, config.BIREFNET_LOCAL_DIR)

import torch
import torch.nn.functional as F
from torchvision import transforms
from safetensors.torch import load_file

_birefnet_transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(config.IMAGENET_MEAN, config.IMAGENET_STD),
])

# --- 全局模型缓存 ---
_birefnet_model = _birefnet_device = None
_segformer_model = _segformer_processor = _segformer_device = None


# ================================================================
#  BiRefNet -- 高精度前景分割
# ================================================================

def _get_birefnet(quantize=True, infer_size=1024):
    """懒加载 BiRefNet 模型"""
    global _birefnet_model, _birefnet_device
    if _birefnet_model is not None:
        return _birefnet_model, _birefnet_device

    from models.birefnet import BiRefNet

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    weights_dir = os.path.join(config.BIREFNET_MODEL_DIR, 'weights')
    sf_path = os.path.join(weights_dir, config.BIREFNET_WEIGHTS_FILENAME)
    if not os.path.exists(sf_path):
        sf_path = os.path.join(config.BIREFNET_MODEL_DIR, config.BIREFNET_WEIGHTS_FILENAME)

    state_dict = load_file(sf_path)
    model = BiRefNet(bb_pretrained=False)
    model.load_state_dict(state_dict, strict=True)

    if quantize and device.type == 'cpu':
        model = torch.quantization.quantize_dynamic(
            model, {torch.nn.Linear, torch.nn.Conv2d}, dtype=torch.qint8)

    model = model.to(device)
    model.eval()
    _birefnet_model = model
    _birefnet_device = device
    return model, device


def birefnet_alpha(image_rgb, quantize=True, infer_size=1024):
    """
    BiRefNet 高精度前景分割。
    输入: PIL Image (RGB)
    输出: (H, W) float32 numpy 数组 (0.0~1.0)
    """
    model, device = _get_birefnet(quantize, infer_size)
    img_np = np.array(image_rgb)
    src_h, src_w = img_np.shape[:2]

    from cv2 import resize as cv2_resize
    img_resized = cv2_resize(img_np, (infer_size, infer_size))
    img_tensor = _birefnet_transform(img_resized).unsqueeze(0).to(device)

    with torch.no_grad():
        mask = model(img_tensor)[-1].sigmoid().cpu()

    mask_np = mask[0, 0].numpy()
    mask_np = cv2_resize(mask_np, (src_w, src_h))
    return mask_np.astype(np.float32)


# ================================================================
#  SegFormer B2 -- 服装语义分割
# ================================================================

def _get_segformer():
    """懒加载 SegFormer B2 模型"""
    global _segformer_model, _segformer_processor, _segformer_device
    if _segformer_model is not None:
        return _segformer_model, _segformer_processor, _segformer_device

    from transformers import SegformerImageProcessor, SegformerForSemanticSegmentation

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    _segformer_processor = SegformerImageProcessor.from_pretrained(config.SEGFORMER_MODEL_DIR)
    _segformer_model = SegformerForSemanticSegmentation.from_pretrained(config.SEGFORMER_MODEL_DIR)
    _segformer_model = _segformer_model.to(device)
    _segformer_model.eval()
    _segformer_device = device
    return _segformer_model, _segformer_processor, _segformer_device


def segformer_mask(image_rgb, target_classes=(4,)):
    """
    SegFormer B2 语义分割 -- 返回目标服装类别的二值 mask。
    输入: PIL Image (RGB)
    输出: (H, W) bool numpy 数组
    """
    model, processor, device = _get_segformer()
    orig_w, orig_h = image_rgb.size

    inputs = processor(images=image_rgb, return_tensors='pt')
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        logits = model(**inputs).logits

    upsampled = F.interpolate(logits, size=(orig_h, orig_w),
                              mode='bilinear', align_corners=False)
    pred_labels = upsampled.argmax(dim=1)[0].cpu().numpy()
    return np.isin(pred_labels, target_classes)


def segformer_full_labels(image_rgb):
    """SegFormer B2 全类别推理，返回每个类别的像素统计"""
    model, processor, device = _get_segformer()
    orig_w, orig_h = image_rgb.size

    inputs = processor(images=image_rgb, return_tensors='pt')
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        logits = model(**inputs).logits

    upsampled = F.interpolate(logits, size=(orig_h, orig_w),
                              mode='bilinear', align_corners=False)
    pred_labels = upsampled.argmax(dim=1)[0].cpu().numpy()

    stats = {}
    for cls_id in range(18):
        cnt = int((pred_labels == cls_id).sum())
        if cnt > 0:
            stats[cls_id] = cnt
    return stats


# ================================================================
#  主入口 -- 服装分割
# ================================================================

def segment_clothing_from_photo(photo_path, clothing_type='upper',
                                quantize=True, infer_size=1024,
                                verbose=True):
    """
    从人物照片中分割出目标服装。

    参数:
        photo_path:    人物照片路径 (str) 或 PIL Image
        clothing_type: 目标服装类型
        quantize:      BiRefNet INT8 量化
        infer_size:    BiRefNet 推理分辨率
        verbose:       是否打印进度

    返回:
        dict: image, alpha, birefnet_alpha, segformer_mask, clothing_type
    """
    if clothing_type not in config.CLOTHING_TYPE_MAP:
        raise ValueError(
            f'不支持的服装类型: {clothing_type}，'
            f'可选: {list(config.CLOTHING_TYPE_MAP.keys())}'
        )
    target_classes = config.CLOTHING_TYPE_MAP[clothing_type]

    if isinstance(photo_path, str):
        original = Image.open(photo_path).convert('RGB')
    else:
        original = photo_path.convert('RGB')

    # Stage 1: BiRefNet 前景分割
    if verbose:
        print(f'[Stage 1/2] BiRefNet 前景分割 (infer_size={infer_size})...')
    alpha_biref = birefnet_alpha(original, quantize, infer_size)
    fg_pct = (alpha_biref > 0.5).sum() / alpha_biref.size * 100
    if verbose:
        print(f'          前景像素: {fg_pct:.1f}%')

    # Stage 2: SegFormer 服装分割
    if verbose:
        class_names = [config.SEGFORMER_CLASSES.get(c, str(c)) for c in target_classes]
        print(f'[Stage 2/2] SegFormer B2 分割: {", ".join(class_names)}...')
    mask_seg = segformer_mask(original, target_classes)
    seg_pct = mask_seg.sum() / mask_seg.size * 100
    if verbose:
        print(f'          目标服装像素: {mask_seg.sum()} ({seg_pct:.1f}%)')

    if mask_seg.sum() < 500:
        if verbose:
            print('          WARNING: 目标服装像素极少，SegFormer 可能未正确检测')

    alpha_final = alpha_biref * mask_seg.astype(np.float32)

    original_np = np.array(original)
    h, w = original_np.shape[:2]
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[:, :, :3] = original_np
    rgba[:, :, :3] = original_np
    rgba[:, :, 3] = (np.clip(alpha_final, 0, 1) * 255).astype(np.uint8)

    if verbose:
        out_pct = (alpha_final > 0.3).sum() / alpha_final.size * 100
        print(f'          最终非零像素: {out_pct:.1f}%')
        print('          Done')

    return {
        'image': Image.fromarray(rgba),
        'alpha': alpha_final,
        'birefnet_alpha': alpha_biref,
        'segformer_mask': mask_seg,
        'clothing_type': clothing_type,
    }
