"""
config.py — 全局配置（开发者预先设置）
==========================================
所有可配置的路径、模型参数、服务参数集中在此。
移植到移动端时只需修改本文件。

目录结构约定:
    PROJECT_ROOT = 本文件所在目录
    assets/      — 静态资源（模型、UV模板、纹理、服装图片）
    ai/          — AI 推理模块（分割、纹理映射）
    backend/     — Flask 后端服务
    frontend/    — 前端（index.html 位于根目录供 Live Server 使用）
    mobile/      — 移动端适配相关
"""

import os

# ═══════════════════════════════════════════════════════════════
#  路径配置
# ═══════════════════════════════════════════════════════════════

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# AI 模型权重路径（当前放在项目外的绝对路径，移植时需改为对应设备路径）
BIREFNET_MODEL_DIR = r'D:\BiRefNet'
SEGFORMER_MODEL_DIR = r'D:\segformer_b2_clothes\model_weights'

# BiRefNet 模型文件名
BIREFNET_WEIGHTS_FILENAME = 'model.safetensors'

# 静态资源目录
ASSETS_DIR = os.path.join(PROJECT_ROOT, 'assets')
MODELS_DIR = os.path.join(ASSETS_DIR, 'models')
UV_DIR = os.path.join(ASSETS_DIR, 'UV')
TEXTURE_DIR = os.path.join(ASSETS_DIR, 'Texture')
CLOTHING_DIR = os.path.join(ASSETS_DIR, 'clothing')
BIREFNET_ASSETS_DIR = os.path.join(ASSETS_DIR, 'BiRefNet_model')

# 本地 BiRefNet 代码目录（项目内副本）
BIREFNET_LOCAL_DIR = os.path.join(ASSETS_DIR, 'BiRefNet_model')
# BiRefNet 代码所在包的父目录（用于 from BiRefNet_model.birefnet import BiRefNet）
BIREFNET_PACKAGE_DIR = ASSETS_DIR


# ═══════════════════════════════════════════════════════════════
#  服务器配置
# ═══════════════════════════════════════════════════════════════

SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5000
SERVER_DEBUG = False
FRONTEND_LIVE_SERVER_PORT = 5500


# ═══════════════════════════════════════════════════════════════
#  AI 推理配置
# ═══════════════════════════════════════════════════════════════

# BiRefNet 默认推理参数
BIREFNET_INFER_SIZE = 768
BIREFNET_QUANTIZE = True  # CPU INT8 量化加速

# SegFormer B2 推理参数
SEGFORMER_INFERENCE_SIZE = 1024

# 图像归一化参数（ImageNet 标准）
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


# ═══════════════════════════════════════════════════════════════
#  SegFormer 18 类语义标签
# ═══════════════════════════════════════════════════════════════

SEGFORMER_CLASSES = {
    0: '背景',
    1: '帽子',
    2: '头发',
    3: '太阳镜',
    4: '上衣',
    5: '裙子',
    6: '裤子',
    7: '连衣裙',
    8: '腰带',
    9: '左鞋',
    10: '右鞋',
    11: '脸',
    12: '左腿',
    13: '右腿',
    14: '左臂',
    15: '右臂',
    16: '包',
    17: '围巾',
}


# ═══════════════════════════════════════════════════════════════
#  服装类型映射
# ═══════════════════════════════════════════════════════════════

# 用户可选服装类型 -> SegFormer class IDs
CLOTHING_TYPE_MAP = {
    'upper':      (4,),              # 上衣
    'skirt':      (5,),              # 裙子
    'pants':      (6,),              # 裤子
    'dress':      (7,),              # 连衣裙
    'upper+vest': (4,),              # 背心（也用上衣类）
}

# 服装类型 -> 推荐 UV 模板（相对于 assets/）
CLOTHING_TO_UV = {
    'upper':      'models/Woman-T-Shirt.png',
    'skirt':      'models/Skirt.png',
    'pants':      None,  # 暂无 UV 模板
    'dress':      None,  # 暂无 UV 模板
    'upper+vest': 'models/WomanVest.png',
}

# 服装类型 -> 推荐 3D 模型（相对于 assets/）
CLOTHING_TO_MODEL = {
    'upper':      'models/Woman-T-Shirt.obj',
    'skirt':      'models/Skirt.obj',
    'pants':      'models/WomanTrouser.obj',
    'dress':      None,
    'upper+vest': 'models/WomanVest.obj',
}

# 3D 模型配置（前端用）
CLOTHING_3D_CONFIG = {
    'upper':      {'obj': 'models/Woman-T-Shirt.obj', 'label': '上衣'},
    'upper+vest': {'obj': 'models/WomanVest.obj',     'label': '背心'},
    'skirt':      {'obj': 'models/Skirt.obj',         'label': '裙子'},
    'pants':      {'obj': 'models/WomanTrouser.obj',  'label': '裤子'},
    'dress':      {'obj': None,                       'label': '连衣裙'},
}

# 人台模型
MANNEQUIN_OBJ = 'models/womannequin.obj'
MANNEQUIN_MTL = 'models/womannequin.mtl'