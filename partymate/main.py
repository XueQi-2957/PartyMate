"""
PartyMate — 党务智能助手 CLI

用法:
  uv run python -m partymate.main check-doc --raw "材料全文"
  uv run python -m partymate.main meeting --raw "会议原始记录"
  uv run python -m partymate.main content "党纪学习教育"
  uv run python -m partymate.main interactive   # 交互模式（AI 驱动）
  uv run python -m partymate.main help
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .tools.doc_check import check_document, detect_doc_type
from .tools.meeting_summary import parse_meeting_notes, format_meeting_summary
from .tools.content_gen import generate_meeting_content, format_content_plan
from .exporters import export_content_pptx, export_meeting_docx

# 所有可用工具的说明
TOOL_DESCRIPTIONS = {
    "check-doc": {
        "title": "📋 发展党员材料合规检查",
        "desc": "检查入党申请书、思想汇报、转正申请等材料的格式和内容规范",
        "usage": 'uv run python -m partymate.main check-doc --raw "思想汇报正文..."',
    },
    "meeting": {
        "title": "📝 会议记录整理",
        "desc": "将原始会议记录整理为结构化的会议纪要",
        "usage": 'uv run python -m partymate.main meeting --raw "时间：2024年... 主持人：..."',
        "extra": "  --export-docx  导出为正式 Word 文档",
    },
    "content": {
        "title": "📚 三会一课内容生成",
        "desc": "根据主题生成学习材料、PPT大纲和讨论题目",
        "usage": 'uv run python -m partymate.main content "党纪学习教育"',
        "extra": "  --export-pptx  导出为正式 PPT 演示文稿",
    },
    "interactive": {
        "title": "💬 交互模式（AI 驱动）",
        "desc": "用自然语言与 PartyMate AI 对话，自动调用工具",
        "usage": "uv run python -m partymate.main interactive",
    },
}


def cmd_help():
    print("=" * 50)
    print("  PartyMate — 党务智能助手")
    print("=" * 50)
    print()
    for key, info in TOOL_DESCRIPTIONS.items():
        print(f"  {info['title']}")
        print(f"    用途: {info['desc']}")
        print(f"    用法: {info['usage']}")
        extra = info.get("extra")
        if extra:
            print(f"    {extra}")
        print()
    print("=" * 50)


async def cmd_check_doc(args: argparse.Namespace):
    if not args.raw:
        print("请提供材料全文：--raw \"材料正文...\"")
        return
    result = check_document(args.raw)
    print(result)

    # 如果提供了 --ai，调用 LLM 做增强分析
    if args.ai:
        print()
        print("=" * 40)
        print("🤖 AI 增强分析:")
        print("=" * 40)
        from .agent import run_agent
        prompt = f"请帮我分析这份{detect_doc_type(args.raw) or '材料'}：\n\n{args.raw}"
        result = await run_agent(prompt)
        print(result)


async def cmd_meeting(args: argparse.Namespace):
    if not args.raw:
        print("请提供会议记录全文：--raw \"记录正文...\"")
        return
    raw_result = parse_meeting_notes(args.raw)
    result = format_meeting_summary(raw_result)
    print(result)

    # Word 文档导出
    if args.export_docx:
        print()
        print("=" * 40)
        print("📝 正在生成 Word 文档...")
        print("=" * 40)
        path = export_meeting_docx(raw_result, args.export_path)
        print(f"✅ Word 文档已导出: {path}")

    if args.ai:
        print()
        print("=" * 40)
        print("🤖 AI 增强总结:")
        print("=" * 40)
        from .agent import run_agent
        prompt = f"请帮我整理这份会议记录：\n\n{args.raw}"
        result = await run_agent(prompt)
        print(result)


async def cmd_content(args: argparse.Namespace):
    if not args.topic:
        print("请提供主题：uv run python -m partymate.main content \"党纪学习教育\"")
        return
    raw = generate_meeting_content(args.topic)
    result = format_content_plan(raw)
    print(result)

    # PPT 导出
    if args.export_pptx:
        print()
        print("=" * 40)
        print("📊 正在生成 PPT...")
        print("=" * 40)
        path = export_content_pptx(raw, args.export_path)
        print(f"✅ PPT 已导出: {path}")

    if args.ai:
        print()
        print("=" * 40)
        print("🤖 AI 增强方案:")
        print("=" * 40)
        from .agent import run_agent
        prompt = f"帮我准备一次关于「{args.topic}」的党课/学习活动的内容方案"
        result = await run_agent(prompt)
        print(result)


async def cmd_interactive():
    print("=" * 50)
    print("  PartyMate 交互模式 (输入 /quit 退出)")
    print("  支持：检查材料、整理会议、生成内容方案")
    print("=" * 50)
    print()

    # 检查 LLM 连接
    from .agent import run_agent as original_run_agent

    async def safe_run_agent(text: str) -> str:
        try:
            return await original_run_agent(text)
        except Exception as e:
            err = str(e).lower()
            if "connection" in err or "refused" in err or "connect" in err:
                return ("⚠️ 无法连接到本地 AI 模型。\n\n"
                        "请确保 Ollama 已启动并在运行：\n"
                        "  ollama serve\n\n"
                        "或者使用独立模式直接调用工具：\n"
                        "  uv run python -m partymate.main check-doc --raw \"材料内容\"\n"
                        "  uv run python -m partymate.main meeting --raw \"会议记录\"\n"
                        "  uv run python -m partymate.main content \"主题\"")
            return f"❌ 出错: {e}"

    while True:
        try:
            user_input = input("🧑 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("再见！")
            break
        if user_input.lower() == "/help":
            cmd_help()
            continue

        print("🤖 思考中...")
        try:
            result = await safe_run_agent(user_input)
            print()
            print(result)
        except Exception as e:
            print(f"❌ 出错: {e}")
        print()


def main():
    parser = argparse.ArgumentParser(description="PartyMate 党务智能助手")
    parser.add_argument("action", choices=["check-doc", "meeting", "content", "interactive", "help"],
                        help="要执行的操作")
    parser.add_argument("--raw", type=str, help="输入文本（材料全文或会议记录）")
    parser.add_argument("--ai", action="store_true", help="调用 AI 做增强分析（需本地 Ollama 运行中）")
    parser.add_argument("--export-pptx", action="store_true", help="导出为 PPT 演示文稿（仅 content 命令）")
    parser.add_argument("--export-docx", action="store_true", help="导出为 Word 文档（仅 meeting 命令）")
    parser.add_argument("--export-path", type=str, help="导出文件路径（可选，默认自动生成）")
    parser.add_argument("topic", type=str, nargs="?", help="内容生成的主题")

    args = parser.parse_args()

    if args.action == "help":
        cmd_help()
        return

    if args.action == "interactive":
        asyncio.run(cmd_interactive())
        return

    if args.action == "check-doc":
        asyncio.run(cmd_check_doc(args))
    elif args.action == "meeting":
        asyncio.run(cmd_meeting(args))
    elif args.action == "content":
        asyncio.run(cmd_content(args))


if __name__ == "__main__":
    main()