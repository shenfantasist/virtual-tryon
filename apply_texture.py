"""
apply_texture.py -- 向后兼容入口
===================================
实际模块已迁移至 ai/apply_texture.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.apply_texture import (
    load_uv_template,
    detect_uv_islands,
    identify_front_body_island,
    extract_dominant_color,
    warp_fabric_to_island,
    fill_island_on_template,
    fill_island_color,
    get_fabric_bbox,
    order_points,
)

# 所有实际实现已迁移至 ai/apply_texture.py
# 本文件仅作为向后兼容入口，不要在此文件中添加新代码。
