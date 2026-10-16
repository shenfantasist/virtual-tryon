from PIL import Image
import numpy as np
import os

def crop_to_content(image_path, output_path, margin=10):
    img = Image.open(image_path).convert('RGBA')
    arr = np.array(img)
    alpha = arr[:, :, 3]
    nonzero = np.argwhere(alpha > 0)
    if len(nonzero) == 0:
        img.save(output_path)
        return
    y0, x0 = nonzero.min(axis=0)
    y1, x1 = nonzero.max(axis=0)
    y0 = max(0, y0 - margin)
    x0 = max(0, x0 - margin)
    y1 = min(img.height - 1, y1 + margin)
    x1 = min(img.width - 1, x1 + margin)
    cropped = img.crop((x0, y0, x1 + 1, y1 + 1))
    cropped.save(output_path)
    print(f'Cropped {image_path} -> {output_path}, bbox=({x0},{y0},{x1},{y1}), margin={margin}')
