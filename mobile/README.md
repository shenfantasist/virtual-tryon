# mobile/ — 移动端适配指南

## 当前架构适配说明

本项目采用前后端分离架构，天然支持移动端适配：

### 后端（不变）
- `backend/server.py` 提供 RESTful API，移动端直接调用即可
- AI 推理模块（`ai/`）保持不变，部署在服务器端
- 移动端只需配置正确的 API 地址（`config.py` 中的 `SERVER_HOST`/`SERVER_PORT`）

### 前端（需适配）
当前前端 `index.html` 基于 Three.js + Web，移动端适配方案：

1. **WebView 方案（最快）**
   - 将 `index.html` + `assets/` 打包进 App
   - 使用 Capacitor/Cordova 包装为原生 App
   - `config.py` 中配置服务器地址即可

2. **React Native + Three.js 方案**
   - 使用 `expo-three` 或 `react-native-three`
   - 将 Three.js 渲染逻辑迁移到 React Native 组件

3. **Flutter + flutter_gl 方案**
   - 使用 Flutter 的 3D 渲染能力
   - 重新实现 Three.js 等价的渲染逻辑

### 关键配置（移植时需修改）
- `config.py`：修改 `SERVER_HOST` 为部署服务器地址
- `index.html`：`API` 变量已支持通过 `localStorage` 自定义
- `config.py`：修改模型路径为移动端资源路径

### 移动端注意事项
- AI 推理必须在服务端执行（模型太大，不适合端侧）
- 3D 模型文件需要压缩（glTF 格式比 OBJ 更高效）
- 触摸交互需要适配（OrbitControls 已支持触摸）
- 图片上传需要压缩（减少网络传输）
