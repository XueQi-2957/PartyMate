"""
PartyMate — 党务智能助手 统一入口

用法:
  partymate             启动 Web UI（默认，http://localhost:8567）
  partymate check-doc   材料合规检查（CLI 模式）
  partymate meeting     会议记录整理
  partymate content     三会一课内容生成
  partymate interact    交互对话模式
  partymate help        显示帮助
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path


def _print_banner():
    print()
    print("  ╔═══════════════════════════════════╗")
    print("  ║      ★ PartyMate                 ║")
    print("  ║      党务智能助手                  ║")
    print("  ╚═══════════════════════════════════╝")
    print()


def _show_help():
    _print_banner()
    print("  用法:")
    print("    partymate              启动 Web 界面（默认）")
    print("    partymate check-doc    材料合规检查")
    print("    partymate meeting      会议记录整理")
    print("    partymate content      三会一课内容生成")
    print("    partymate interact     交互对话（AI）")
    print("    partymate help         显示本帮助")
    print()
    print("  独立模式（无需 AI）:")
    print("    partymate check-doc --raw \"材料全文\"")
    print("    partymate meeting --raw \"会议记录\"")
    print("    partymate content \"主题\"")
    print()
    print("  AI 增强模式（需 Ollama 运行中）:")
    print("    partymate check-doc --raw \"材料\" --ai")
    print("    partymate content \"主题\" --ai")
    print()


def _start_webui():
    """启动 Web 服务器"""
    _print_banner()
    print("  🌐 正在启动 Web 界面...")
    print()

    # 自动打开浏览器
    url = "http://localhost:8567"
    try:
        webbrowser.open(url)
    except Exception:
        pass

    # 导入并启动 uvicorn
    import uvicorn
    from partymate.web.server import app

    print(f"  访问地址: {url}")
    print(f"  按 Ctrl+C 停止服务")
    print()
    uvicorn.run(app, host="0.0.0.0", port=8567, log_level="info")


def main():
    """统一入口"""
    args = sys.argv[1:]

    if not args:
        _start_webui()
        return

    cmd = args[0]

    if cmd in ("help", "--help", "-h"):
        _show_help()
        return

    # 剩余参数传递给原有的 main 函数
    if cmd in ("check-doc", "meeting", "content", "interactive", "interact"):
        from partymate.main import main as cli_main
        # 替换 sys.argv 让原 argparse 处理
        sys.argv = ["partymate", *args]
        cli_main()
        return

    # 未知命令，显示帮助
    print(f"❌ 未知命令: {cmd}")
    _show_help()
    sys.exit(1)


if __name__ == "__main__":
    main()