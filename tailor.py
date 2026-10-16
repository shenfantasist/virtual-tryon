"""
tailor.py — Developer UV Pin Tool (案台 - 开发者版)
====================================================
Standalone tool for placing定位图钉 on UV template images.

Usage:
    python tailor.py [--uv T-Shirt] [--type upper]

Opens a window showing the UV template where you can:
  - Click to place red pin markers (up to 7)
  - Right-click to remove last pin
  - Press 's' to save pins
  - Press 'c' to clear all pins
  - Press 'q' or ESC to quit without saving

Saves pin data to assets/positioning/{clothing_type}_pins.json
"""

import os
import sys
import json
import argparse
import time

# Project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

import cv2
import numpy as np
from PIL import Image

import config

# Directories
POSITIONING_DIR = os.path.join(config.ASSETS_DIR, 'positioning')
os.makedirs(POSITIONING_DIR, exist_ok=True)

# Constants
MAX_PINS = 7
PIN_RADIUS = 8
PIN_RADIUS = 10
PIN_COLOR = (0, 0, 255)       # Red (BGR) - OpenCV uses BGR
TEXT_COLOR = (255, 255, 255)
BG_COLOR = (40, 40, 40)


class TailorApp:
    """Interactive UV pin placement tool."""

    def __init__(self, uv_template_path, clothing_type='upper'):
        self.uv_path = uv_template_path
        self.clothing_type = clothing_type
        self.pins = []
        self.saved = False
        self.window_name = f'Tailor - {clothing_type} UV Pin Tool'

        # Load UV template
        self.uv_img = Image.open(uv_template_path).convert('RGBA')
        self.uv_arr = np.array(self.uv_img)
        self.display_h, self.display_w = self.uv_arr.shape[:2]

        # Scale to fit screen (max 900px)
        max_dim = 900
        scale = min(max_dim / self.display_w, max_dim / self.display_h, 1.0)
        self.scale = scale
        self.disp_w = int(self.display_w * scale)
        self.disp_h = int(self.display_h * scale)

        # Try to load existing pins
        self._load_existing_pins()

    def _load_existing_pins(self):
        """Load previously saved pins if they exist."""
        pin_file = os.path.join(POSITIONING_DIR, f'{self.clothing_type}_pins.json')
        if os.path.exists(pin_file):
            try:
                with open(pin_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.pins = data.get('pins', [])
                print(f'  Loaded {len(self.pins)} existing pins from {pin_file}')
            except Exception:
                pass

    def _render(self):
        """Render the display with pins."""
        # Create display image
        display = self.uv_arr.copy()

        # Draw placed pins (red filled circle with white border) on original image
        for pin in self.pins:
            x, y = int(pin['x']), int(pin['y'])
            # Red filled circle (BGR: 0,0,255)
            cv2.circle(display, (x, y), PIN_RADIUS, PIN_COLOR, -1)
            # White border for visibility
            cv2.circle(display, (x, y), PIN_RADIUS, (255, 255, 255), 2)

        # HUD text
        hud_y = 30
        info_lines = [
            f'UV Pin Tool - {self.clothing_type}',
            f'Pins: {len(self.pins)}/{MAX_PINS}',
            f'Image: {self.display_w}x{self.display_h}',
            '',
            'Left-click: place pin',
            'Right-click: remove last pin',
            'S: save | C: clear | Q/ESC: quit',
        ]
        for line in info_lines:
            cv2.putText(display, line, (10, hud_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, BG_COLOR, 3)
            cv2.putText(display, line, (10, hud_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, TEXT_COLOR, 1)
            hud_y += 22

        # Resize for display
        display_bgr = cv2.cvtColor(display, cv2.COLOR_RGBA2BGR)
        if self.scale < 1.0:
            display_bgr = cv2.resize(display_bgr, (self.disp_w, self.disp_h))

        return display_bgr

    def _save(self):
        """Save pins to JSON."""
        pin_file = os.path.join(POSITIONING_DIR, f'{self.clothing_type}_pins.json')
        data = {
            'clothing_type': self.clothing_type,
            'uv_template': self.uv_path,
            'pins': self.pins,
            'image_size': {'w': self.display_w, 'h': self.display_h},
            'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        with open(pin_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.saved = True
        print(f'  Pins saved: {pin_file} ({len(self.pins)} pins)')

    def run(self):
        """Main event loop."""
        print(f'\n  UV Pin Tool: {self.clothing_type}')
        print(f'  Template: {self.uv_path}')
        print(f'  Image size: {self.display_w}x{self.display_h}')
        print(f'  Max pins: {MAX_PINS}')
        print(f'  Output: {POSITIONING_DIR}/{self.clothing_type}_pins.json')
        print(f'\n  Controls: left-click=place, right-click=remove, s=save, c=clear, q=quit\n')

        cv2.namedWindow(self.window_name, cv2.WINDOW_AUTOSIZE)

        while True:
            display = self._render()
            cv2.imshow(self.window_name, display)

            key = cv2.waitKey(30) & 0xFF

            if key == ord('q') or key == 27:  # q or ESC
                if not self.saved and self.pins:
                    print('  Warning: quit without saving!')
                break
            elif key == ord('s'):
                if self.pins:
                    self._save()
                else:
                    print('  No pins to save!')
            elif key == ord('c'):
                self.pins.clear()
                self.saved = False
                print('  Pins cleared')

        cv2.destroyAllWindows()


def click_callback(event, x, y, flags, param):
    """Mouse callback for pin placement."""
    app = param
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(app.pins) >= MAX_PINS:
            print(f'  Max {MAX_PINS} pins reached!')
            return
        # Convert display coords back to original coords precisely
        scale = app.scale if app.scale > 0 else 1.0
        orig_x = x / scale if scale > 0 else x
        orig_y = y / scale if scale > 0 else y
        # Clamp
        orig_x = max(0, min(app.display_w, orig_x))
        orig_y = max(0, min(app.display_h, orig_y))
        app.pins.append({'x': round(orig_x, 1), 'y': round(orig_y, 1)})
        app.saved = False
        print(f'  Pin {len(app.pins)}: ({orig_x:.1f}, {orig_y:.1f})')
    elif event == cv2.EVENT_RBUTTONDOWN:
        if app.pins:
            removed = app.pins.pop()
            app.saved = False
            print(f'  Removed pin: ({removed["x"]:.1f}, {removed["y"]:.1f})')


def main():
    parser = argparse.ArgumentParser(description='UV Pin Placement Tool')
    parser.add_argument('--uv', default='T-Shirt',
                        help='UV template name (without extension, e.g. T-Shirt)')
    parser.add_argument('--type', default='upper',
                        help='Clothing type (upper, skirt, etc.)')
    args = parser.parse_args()

    # Find UV template
    uv_name = args.uv
    template_path = os.path.join(config.ASSETS_DIR, 'models', f'{uv_name}.png')
    if not os.path.exists(template_path):
        # Try other locations
        template_path = os.path.join(config.UV_DIR, f'{uv_name}.png')
    if not os.path.exists(template_path):
        print(f'Error: UV template not found for "{uv_name}"')
        print(f'  Searched in: {config.ASSETS_DIR}/models/, {config.UV_DIR}/')
        sys.exit(1)

    print(f'UV Template found: {template_path}')

    app = TailorApp(template_path, clothing_type=args.type)

    # Set mouse callback
    window_name = app.window_name
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(window_name, click_callback, app)

    app.run()


if __name__ == '__main__':
    main()
