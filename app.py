"""
app.py -- 启动入口
================
实际后端逻辑已迁移至 backend/server.py
AI 推理模块已迁移至 ai/
全局配置已迁移至 config.py

直接运行本文件即可启动服务器（向后兼容）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.server import app, config

if __name__ == '__main__':
    print(f'Virtual Try-On Backend: http://localhost:{config.SERVER_PORT}')
    print(f'  局域网访问: http://<主机IP>:{config.SERVER_PORT}')
    app.run(host=config.SERVER_HOST, port=config.SERVER_PORT, debug=config.SERVER_DEBUG)