# Virtual Try-On Android App

This is an Android APK that wraps the Flask + Three.js web frontend in a Capacitor WebView.

## Architecture

```
[Android APK / WebView]  ──HTTP──▶  [Flask Backend on Server]  ──PyTorch──▶  [AI Models]
   (手机端)                              (服务器端)                    (BiRefNet/SegFormer)
```

**Important**: AI inference (BiRefNet, SegFormer) cannot run on mobile devices. The APK is a WebView client that connects to your Flask backend. You must:

1. Deploy the Flask backend (`backend/server.py`) to a server with a GPU
2. Configure the API URL in the app (see Configuration below)

## Quick Start

### 1. Install dependencies
```bash
cd android_app
npm install
```

### 2. Copy web frontend into `www/`
The `www/` directory should contain the full frontend (index.html + assets/).
See `build_www.ps1` for an automated copy from the parent project.

### 3. Configure API URL
Edit `www/config.js` (or set via app's settings page) — replace `YOUR_SERVER_IP:5000`.

### 4. Build APK

```bash
# Debug APK (signed with debug key, installable via adb)
npm run build:apk
# → android/app/build/outputs/apk/debug/app-debug.apk

# Release APK (unsigned, needs signing)
npm run build:release
# → android/app/build/outputs/apk/release/app-release-unsigned.apk
```

### 5. Install on device
```bash
adb install android/app/build/outputs/apk/debug/app-debug.apk
```

## Requirements
- Android SDK installed (set `ANDROID_HOME` env var or already at `%LOCALAPPDATA%\Android\Sdk`)
- Java 17
- Node.js 18+

## Configuration

### API endpoint
The app reads API URL from `localStorage.api_url`. On first launch, it tries to auto-detect
from the same hostname:port-5000 pattern. To set a custom server:

1. Open the app
2. Tap the settings gear icon
3. Enter the full API URL (e.g., `http://192.168.1.100:5000`)

### Cleartext HTTP
The app is configured with `cleartext: true` and `allowMixedContent: true` so it can
connect to plain-HTTP backends. For production, use HTTPS.

## Flask Backend Deployment
The original `backend/server.py` should be deployed separately. Example with gunicorn:
```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5000 backend.server:app
```

Make sure the server is reachable from the device's network.
