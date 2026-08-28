"""
pipeline_segment.py -- 向后兼容入口
===================================
实际模块已迁移至 ai/pipeline_segment.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.pipeline_segment import (
    segment_clothing_from_photo,
    segformer_full_labels,
    segformer_mask,
    birefnet_alpha,
    _get_birefnet,
    _get_segformer,
)

# 重新导出常量（供旧代码引用）
from config import SEGFORMER_CLASSES, CLOTHING_TYPE_MAP, CLOTHING_TO_UV, CLOTHING_TO_MODEL

# 所有实际实现已迁移至 ai/pipeline_segment.py
# 本文件仅作为向后兼容入口，不要在此文件中添加新代码。