# 案台与图钉映射功能说明

已开发部分：
1. crop_margin.py — 对 seg-pic 图片做 10px 边缘裁剪，避免大量透明区域
2. tailor.py — 开发者案台（7个图钉，红点/绿点、保存到 assets/positioning/）
3. 前端导航栏已预留“案台”选项位置（pho-index.html / com-index.html 需手动添加按钮）

待继续完善：
- 前端案台页面（自动弹出）与图钉交互（点击放红点、变绿、保存）
- assets/seg-pic/positioning 的图片读取与显示
- 对齐算法（缩放、移动、旋转 + 边界微调 + 其他岛纯色填涂）需要在 Python 中实现
- 用户案台与开发者案台的文件分离已完成（tailor.py 独立运行）
