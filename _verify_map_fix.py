"""验证 map_with_pins 修复后的映射效果（主色调边框）。"""
import os
import sys
import json

_PROJECT_ROOT = r"C:\Users\shenf\Desktop\virtual_tryon"
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PIL import Image
from ai.pin_mapping import map_with_pins

SEG_JSON = os.path.join(_PROJECT_ROOT, 'assets', 'seg-pic', 'positioning', '1789281930_03625e.json')
UV_JSON = os.path.join(_PROJECT_ROOT, 'assets', 'positioning', 'upper_pins.json')

with open(SEG_JSON, 'r', encoding='utf-8') as f:
    seg_data = json.load(f)
with open(UV_JSON, 'r', encoding='utf-8') as f:
    uv_data = json.load(f)

seg_path = os.path.join(_PROJECT_ROOT, 'assets', 'seg-pic', seg_data['seg_pic_name'])
seg_img = Image.open(seg_path).convert('RGBA')
template_path = os.path.join(_PROJECT_ROOT, uv_data['uv_template'])
if not os.path.exists(template_path):
    template_path = os.path.join(_PROJECT_ROOT, 'assets', uv_data['uv_template'])

user_pins = seg_data['pins']
uv_pins = uv_data['pins']

result = map_with_pins(seg_img, template_path, user_pins, uv_pins, verbose=True)

out = os.path.join(_PROJECT_ROOT, 'mapping_fix_result.png')
result.save(out)
print(f'\n已保存修复结果: {out}')