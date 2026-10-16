"""Update pho-index.html with workbench features."""
import os

path = r'c:\Users\shenf\Desktop\virtual_tryon\pho-index.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Check current patterns
patterns = ['</style>', 'settings-panel', 'MOBILE_PANELS', '</script>']
for p in patterns:
    count = content.count(p)
    print(f'  "{p}" found {count} times')
print(f'  File length: {len(content)} chars')

# 1) Add workbench CSS before </style>
wb_css = '''
    /* --- Workbench (pin) panel --- */
    #workbench-panel {
      position: fixed;
      bottom: 56px;
      left: 0;
      right: 0;
      width: 100%;
      height: 60vh;
      border: none;
      border-top: 1px solid rgba(255,255,255,0.12);
      border-top-left-radius: 16px;
      border-top-right-radius: 16px;
      transform: translateY(calc(100% + 56px));
      transition: transform 0.3s ease;
      z-index: 20;
      background: rgba(20, 20, 30, 0.95);
      backdrop-filter: blur(12px);
      color: #e0e0e0;
      display: flex;
      flex-direction: column;
      padding: 12px 16px;
      overflow-y: auto;
    }
    #workbench-panel.expanded { transform: translateY(0); }
    .wb-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-shrink: 0; }
    .wb-toolbar .pin-toggle {
      width: 36px; height: 36px; border-radius: 50%; border: 2px solid #888;
      background: #cc3333; cursor: pointer; transition: all 0.2s; flex-shrink: 0;
    }
    .wb-toolbar .pin-toggle.active { background: #33aa33; border-color: #33aa33; }
    .wb-toolbar .wb-label { font-size: 14px; font-weight: 600; color: #ccc; }
    .wb-toolbar .wb-btn {
      padding: 6px 12px; border: none; border-radius: 6px;
      font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s;
    }
    .wb-toolbar .wb-btn-save { background: linear-gradient(135deg, #7c6ff7, #5b4fcf); color: #fff; }
    .wb-toolbar .wb-btn-map { background: linear-gradient(135deg, #ff6b6b, #cc4444); color: #fff; }
    .wb-toolbar .wb-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .wb-canvas-wrap {
      flex: 1; position: relative; overflow: hidden; border-radius: 10px;
      background: rgba(0,0,0,0.3); min-height: 200px;
    }
    .wb-canvas-wrap img {
      width: 100%; height: 100%; object-fit: contain; display: block;
      user-select: none; pointer-events: none;
    }
    .wb-canvas-wrap canvas {
      position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: crosshair;
    }
    .wb-pin-count { font-size: 12px; color: #aaa; margin-top: 6px; flex-shrink: 0; }
    .wb-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: #666; font-size: 14px; }
'''
if 'workbench-panel' not in content:
    content = content.replace('  </style>', wb_css + '  </style>')
    print('Added workbench CSS')

# 2) Add workbench panel HTML before bottom nav
wb_html = '''  <!-- Workbench (pin) panel -->
  <div id="workbench-panel">
    <div class="panel-title">&#128204; 案台</div>
    <div class="wb-toolbar">
      <div class="pin-toggle" id="wb-pin-toggle" title="切换图钉模式"></div>
      <span class="wb-label" id="wb-status">图钉模式: 关</span>
      <button class="wb-btn wb-btn-save" id="wb-save-btn" disabled>&#128190; 保存图钉</button>
      <button class="wb-btn wb-btn-map" id="wb-map-btn" disabled>&#127919; 映射纹理</button>
    </div>
    <div class="wb-canvas-wrap" id="wb-canvas-wrap">
      <div class="wb-empty" id="wb-empty">完成AI处理后，分割图将显示在此处</div>
    </div>
    <div class="wb-pin-count" id="wb-pin-count"></div>
  </div>

'''
nav_marker = '  <!-- \u624b\u673a\u7aef\u5e95\u90e8\u5bfc\u822a\u680f -->'
if '<div id="workbench-panel">' not in content:
    content = content.replace(nav_marker, wb_html + nav_marker)
    print('Added workbench HTML panel')

# 3) Add 案台 nav button (before settings button)
old_nav = '<button class="nav-item" data-panel="settings-panel" onclick="togglePanel(\'settings-panel\')">\u2699 \u8bbe\u7f6e</button>'
new_nav = '<button class="nav-item" data-panel="workbench-panel" onclick="togglePanel(\'workbench-panel\')">&#128204; \u6848\u53f0</button>\n    ' + old_nav
if 'workbench-panel' not in content.split('bottom-nav')[1] if 'bottom-nav' in content else '':
    content = content.replace(old_nav, new_nav)
    print('Added workbench nav button')

# 4) Update MOBILE_PANELS
content = content.replace(
    "const MOBILE_PANELS = ['left-panel', 'right-panel', 'settings-panel'];",
    "const MOBILE_PANELS = ['left-panel', 'right-panel', 'workbench-panel', 'settings-panel'];"
)
print('Updated MOBILE_PANELS')

# 5) Add workbench JS logic before last </script>
wb_js = r"""
    // --- Workbench (pin) logic ---
    const MAX_PINS = 7;
    let wbPins = [];
    let wbPinMode = false;
    let wbSegPicName = '';
    let wbClothingType = 'upper';
    const wbPinToggle = document.getElementById('wb-pin-toggle');
    const wbStatus = document.getElementById('wb-status');
    const wbSaveBtn = document.getElementById('wb-save-btn');
    const wbMapBtn = document.getElementById('wb-map-btn');
    const wbCanvasWrap = document.getElementById('wb-canvas-wrap');
    const wbPinCount = document.getElementById('wb-pin-count');

    wbPinToggle.addEventListener('click', () => {
      wbPinMode = !wbPinMode;
      wbPinToggle.classList.toggle('active', wbPinMode);
      wbStatus.textContent = '图钉模式: ' + (wbPinMode ? '开' : '关');
      const canvas = document.getElementById('wb-pin-canvas');
      if (canvas) canvas.style.cursor = wbPinMode ? 'crosshair' : 'default';
    });

    function setupWbCanvas() {
      const wrap = document.getElementById('wb-canvas-wrap');
      let canvas = document.getElementById('wb-pin-canvas');
      if (!canvas) {
        canvas = document.createElement('canvas');
        canvas.id = 'wb-pin-canvas';
        wrap.appendChild(canvas);
      }
      const img = wrap.querySelector('img');
      if (!img) return;
      const resizeCanvas = () => {
        canvas.width = img.clientWidth;
        canvas.height = img.clientHeight;
        drawWbPins();
      };
      if (img.complete) { setTimeout(resizeCanvas, 50); }
      else { img.onload = resizeCanvas; }
      window.addEventListener('resize', resizeCanvas);

      canvas.onclick = (e) => {
        if (!wbPinMode) return;
        if (wbPins.length >= MAX_PINS) { wbStatus.textContent = '已达上限 ' + MAX_PINS + ' 个图钉'; return; }
        const rect = canvas.getBoundingClientRect();
        const rx = (e.clientX - rect.left) / rect.width;
        const ry = (e.clientY - rect.top) / rect.height;
        wbPins.push({ x: Math.round(rx * 1000) / 1000, y: Math.round(ry * 1000) / 1000 });
        drawWbPins();
        updateWbButtons();
      };

      canvas.oncontextmenu = (e) => {
        e.preventDefault();
        if (wbPins.length > 0) {
          wbPins.pop();
          drawWbPins();
          updateWbButtons();
        }
      };
    }

    function drawWbPins() {
      const canvas = document.getElementById('wb-pin-canvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      wbPins.forEach((pin, i) => {
        const px = pin.x * canvas.width;
        const py = pin.y * canvas.height;
        ctx.beginPath();
        ctx.arc(px, py, 8, 0, Math.PI * 2);
        ctx.fillStyle = '#ff3333';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 11px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(i + 1), px, py);
      });
      wbPinCount.textContent = wbPins.length > 0
        ? '\u5df2\u653e\u7f6e ' + wbPins.length + '/' + MAX_PINS + ' \u4e2a\u56fe\u9489' : '';
    }

    function updateWbButtons() {
      wbSaveBtn.disabled = wbPins.length < 2;
      wbMapBtn.disabled = wbPins.length < 2 || !wbSegPicName;
    }

    wbSaveBtn.addEventListener('click', async () => {
      if (!wbSegPicName || wbPins.length < 2) return;
      try {
        const res = await fetch(API + '/api/save-pins', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ seg_pic_name: wbSegPicName, pins: wbPins, clothing_type: wbClothingType })
        });
        const data = await res.json();
        if (data.ok) { wbStatus.textContent = '\u56fe\u9489\u5df2\u4fdd\u5b58!'; wbStatus.style.color = '#4cff8d'; }
        else { wbStatus.textContent = '\u4fdd\u5b58\u5931\u8d25: ' + (data.error || ''); wbStatus.style.color = '#ff6b6b'; }
      } catch (err) { wbStatus.textContent = '\u4fdd\u5b58\u9519\u8bef: ' + err.message; wbStatus.style.color = '#ff6b6b'; }
    });

    wbMapBtn.addEventListener('click', async () => {
      if (!wbSegPicName || wbPins.length < 2) return;
      wbMapBtn.disabled = true;
      wbStatus.textContent = '\u6620\u5c04\u4e2d...'; wbStatus.style.color = '#7c6ff7';
      try {
        const res = await fetch(API + '/api/map-pins', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ seg_pic_name: wbSegPicName, clothing_type: wbClothingType })
        });
        const data = await res.json();
        if (data.texture_url) {
          wbStatus.textContent = '\u6620\u5c04\u6210\u529f!'; wbStatus.style.color = '#4cff8d';
          const textureUrl = API + '/' + data.texture_url;
          wardrobeTexLoader.load(textureUrl, (tex) => {
            tex.colorSpace = THREE.SRGBColorSpace;
            wardrobeTextures[wbClothingType] = tex;
            refreshTextures();
          });
          const cb = document.querySelector('.outfit-option input[value="' + wbClothingType + '"]');
          if (cb && !cb.checked) { cb.checked = true; updateOutfit(); }
        } else {
          wbStatus.textContent = '\u6620\u5c04\u5931\u8d25: ' + (data.error || ''); wbStatus.style.color = '#ff6b6b';
        }
      } catch (err) { wbStatus.textContent = '\u6620\u5c04\u9519\u8bef: ' + err.message; wbStatus.style.color = '#ff6b6b'; }
      wbMapBtn.disabled = false;
    });

    window.showOnWorkbench = function(segPicUrl, segPicName, clothingType) {
      wbSegPicName = segPicName || '';
      wbClothingType = clothingType || 'upper';
      wbPins = [];
      const wrap = document.getElementById('wb-canvas-wrap');
      wrap.innerHTML = '<img src="' + segPicUrl + '" alt="seg-pic" />';
      setupWbCanvas();
      updateWbButtons();
      wbPinCount.textContent = '';
      wbStatus.textContent = '\u56fe\u9489\u6a21\u5f0f: \u5173';
      togglePanel('workbench-panel');
    };
"""

if 'wbPinMode' not in content:
    # Find the last </script> tag and insert before it
    last_script = content.rfind('  </script>')
    if last_script > 0:
        content = content[:last_script] + wb_js + '\n' + content[last_script:]
        print('Added workbench JS logic')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Done! pho-index.html updated')
