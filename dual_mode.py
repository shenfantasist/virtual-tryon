"""
dual_mode.py — 双模式开发辅助工具
====================================
自动检测当前运行环境，支持:
  1. PC 开发模式: Live Server (port 5500) → Flask API (port 5000)
  2. 移动端预览模式: 在手机浏览器访问 PC 的 IP:5500，效果等同 App
  3. 打包模式: 将前端+资源打包进 App

用法:
  python dual_mode.py           # 启动服务并显示访问地址
  python dual_mode.py --lan     # 显示局域网访问地址（手机预览用）
"""

import os
import sys
import socket
import argparse
import threading
import webbrowser

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

import config


def get_lan_ip():
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def start_flask_server():
    """启动 Flask 后端"""
    from backend.server import app
    app.run(
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        debug=False,  # 双模式下关闭 debug 避免重复加载
    )


def start_live_server(port=5500):
    """启动静态文件服务器"""
    import http.server
    import functools

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=PROJECT_ROOT,
    )
    server = http.server.HTTPServer(('0.0.0.0', port), handler)
    print(f'  Live Server: http://localhost:{port}')
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description='双模式开发工具')
    parser.add_argument('--lan', action='store_true',
                        help='显示局域网地址（手机预览用）')
    parser.add_argument('--flask-port', type=int, default=config.SERVER_PORT)
    parser.add_argument('--live-port', type=int, default=config.FRONTEND_LIVE_SERVER_PORT)
    args = parser.parse_args()

    lan_ip = get_lan_ip()

    print('=' * 60)
    print('  3D 穿搭软件 — 双模式开发')
    print('=' * 60)
    print()
    print('  [PC 开发模式]')
    print(f'    Live Server:  http://localhost:{args.live_port}')
    print(f'    Flask API:    http://localhost:{args.flask_port}')
    print()

    if args.lan:
        print('  [手机预览模式] (同一 WiFi 下)')
        print(f'    手机浏览器:   http://{lan_ip}:{args.live_port}')
        print(f'    后端 API:     http://{lan_ip}:{args.flask_port}')
        print()
        print('  提示: index.html 已自动检测并切换 API 地址')
        print(f'  如需手动配置，打开 http://{lan_ip}:{args.live_port}')
        print('  然后在浏览器控制台执行:')
        print(f'    localStorage.setItem("api_url", "http://{lan_ip}:{args.flask_port}")')
    else:
        print('  [移动端打包] (7天内完成)')
        print('    参考 mobile/README.md 的打包指南')

    print()
    print('  Ctrl+C 停止所有服务')
    print('=' * 60)
    print()

    # 启动 Flask 后端（后台线程）
    flask_thread = threading.Thread(target=start_flask_server, daemon=True)
    flask_thread.start()

    # 短暂等待 Flask 启动
    import time
    time.sleep(1)

    # 启动 Live Server（主线程）
    try:
        start_live_server(args.live_port)
    except KeyboardInterrupt:
        print('\n已停止')


if __name__ == '__main__':
    main()
