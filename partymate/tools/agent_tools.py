from __future__ import annotations

import json
from typing import Any

from partymate.db.repository import Repository
from partymate.tools.doc_check import check_document
from partymate.tools.meeting_summary import parse_meeting_notes, format_meeting_summary
from partymate.tools.content_gen import generate_meeting_content, format_content_plan
from partymate.tools.weather import get_weather


class AgentToolRegistry:
    def __init__(self, repo: Repository | None = None, mcp_session: Any = None):
        self.repo = repo
        self.mcp_session = mcp_session

    def get_schemas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "check_doc",
                    "description": "检查发展党员材料的格式规范、内容完整度、时间线合理性。输入是材料全文文本。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "材料全文文本"}
                        },
                        "required": ["text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "meeting_summary",
                    "description": "整理会议原始记录为结构化会议纪要。输入是原始文本。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "会议原始记录文本"}
                        },
                        "required": ["text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "content_gen",
                    "description": "生成三会一课内容方案（学习材料+PPT大纲+讨论题）。输入是主题名称。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "学习主题或党课主题"}
                        },
                        "required": ["topic"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_member",
                    "description": "按姓名或阶段查询成员信息，获取成员ID、当前状态等。如果不带参数则获取最新添加的成员列表。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "成员姓名（可选）"},
                            "stage": {"type": "string", "description": "阶段，如 applicant, activist, candidate, probationary, full_member（可选）"}
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_materials",
                    "description": "查询指定成员的材料列表和完整度情况。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "member_id": {"type": "integer", "description": "成员ID"}
                        },
                        "required": ["member_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_reminders",
                    "description": "查询待办提醒。可以指定member_id查询特定成员的提醒，或不传查询全局即将到期的提醒。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "member_id": {"type": "integer", "description": "成员ID（可选）"}
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_dashboard_summary",
                    "description": "获取工作台全局统计数据，包括待办数量、各阶段成员人数等。",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge",
                    "description": "在党务知识库中检索规程、文件、常见问题等。当你对党务规定不确定时调用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "检索关键词或问题"}
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "【联网检索】通过互联网搜索引擎获取实时的全网公开资料和新闻。当本地知识库查不到相关信息，或者需要获取最新动态时调用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "搜索关键词"}
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_reminder",
                    "description": "【写入操作】为成员创建一条待办提醒。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "member_id": {"type": "integer", "description": "关联的成员ID"},
                            "title": {"type": "string", "description": "提醒标题"},
                            "description": {"type": "string", "description": "提醒详细描述（可选）"},
                            "due_date": {"type": "string", "description": "截止日期 (YYYY-MM-DD)（可选）"}
                        },
                        "required": ["member_id", "title"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_member_memory",
                    "description": "【写入操作】为成员添加一条长效记忆/笔记/标签。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "member_id": {"type": "integer", "description": "关联的成员ID"},
                            "kind": {"type": "string", "description": "类型，可选: summary, risk, instruction, correction, note"},
                            "content": {"type": "string", "description": "记忆内容"}
                        },
                        "required": ["member_id", "kind", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "获取当前真实的服务器时间与日期。",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_python_code",
                    "description": "【高危操作】执行任意Python代码。可用于复杂的数据处理或系统操作。必须用户手动批准后才会在实际后端执行。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "要执行的Python代码"}
                        },
                        "required": ["code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "【天气查询】查询任意城市的实时天气、温度和未来预报。支持中文城市名（如贵阳、北京、上海等）。使用此工具替代 web_search 来查询天气。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "城市名，中文或英文均可（如 贵阳、Guiyang、上海）"},
                            "days": {"type": "integer", "description": "预报天数（可选，默认 3 天）"}
                        },
                        "required": ["city"],
                    },
                },
            },
        ]

    async def execute(self, name: str, args: dict) -> str:
        try:
            if name == "check_doc":
                return str(check_document(args.get("text", "")))
            elif name == "meeting_summary":
                raw = parse_meeting_notes(args.get("text", ""))
                return format_meeting_summary(raw)
            elif name == "content_gen":
                raw = generate_meeting_content(args.get("topic", ""))
                return format_content_plan(raw)
            elif name == "search_knowledge":
                if self.mcp_session:
                    response = await self.mcp_session.call_tool("search_party_rules", args)
                    return response.content[0].text
                return "知识库检索服务未连接"
            elif name == "get_weather":
                city = args.get("city", "")
                days = args.get("days", 3)
                return await get_weather(city, days)
            elif name == "web_search":
                try:
                    import asyncio
                    query = args.get("query", "")
                    if not query:
                        return json.dumps({"error": "搜索关键词为空"}, ensure_ascii=False)

                    # 方案 A：DuckDuckGo（海外网络下较快）
                    try:
                        from duckduckgo_search import DDGS
                        def _do_ddg():
                            with DDGS(timeout=8) as ddgs:
                                return list(ddgs.text(query, max_results=5))
                        ddg_results = await asyncio.wait_for(
                            asyncio.to_thread(_do_ddg),
                            timeout=12.0
                        )
                        ddg_web_list = []
                        for i, r in enumerate(ddg_results, 1):
                            ddg_web_list.append({
                                "id": f"W{i}",
                                "title": r.get("title", ""),
                                "content": r.get("body", ""),
                                "href": r.get("href", "")
                            })
                        if ddg_web_list:
                            return json.dumps({"web_results": ddg_web_list}, ensure_ascii=False)
                    except Exception:
                        pass  # DuckDuckGo 失败

                    # 方案 B：360搜索（国内可访问，无需 API Key）
                    try:
                        import re
                        from html import unescape
                        so_url = "https://www.so.com/s"
                        so_headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                        }
                        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                            resp = await client.get(so_url, params={"q": query}, headers=so_headers)
                            resp.raise_for_status()
                            html = resp.text

                        # 解析 360 搜索结果
                        so_results = []
                        # 方式 A: 按 <li class="res-list"> 切分结果块
                        res_blocks = re.findall(
                            r'<li[^>]*class="[^"]*res-list[^"]*"[^>]*>(.*?)</li>',
                            html, re.DOTALL
                        )
                        if not res_blocks:
                            # 方式 B: 按 <h3> 提取（兜底）
                            h3_links = re.findall(
                                r'<h3[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                                html, re.DOTALL
                            )
                            for href, title_html in h3_links:
                                title = re.sub(r'<[^>]+>', '', title_html).strip()
                                if title:
                                    so_results.append({
                                        "id": f"W{len(so_results) + 1}",
                                        "title": unescape(title),
                                        "content": "",
                                        "href": href,
                                    })
                                    if len(so_results) >= 5:
                                        break

                        for block in res_blocks:
                            # 提取标题和链接
                            link_match = re.search(
                                r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                                block, re.DOTALL
                            )
                            if not link_match:
                                continue
                            href = link_match.group(1)
                            title = re.sub(r'<[^>]+>', '', link_match.group(2)).strip()
                            if not title:
                                continue
                            # 提取摘要 (360 使用 span.res-list-summary)
                            snippet = ""
                            for snip_pat in [
                                r'<span[^>]*class="[^"]*res-list-summary[^"]*"[^>]*>(.*?)</span>',
                                r'<p[^>]*class="[^"]*res-desc[^"]*"[^>]*>(.*?)</p>',
                            ]:
                                snip_match = re.search(snip_pat, block, re.DOTALL)
                                if snip_match:
                                    snippet = re.sub(r'<[^>]+>', '', snip_match.group(1)).strip()
                                    if snippet:
                                        break
                            so_results.append({
                                "id": f"W{len(so_results) + 1}",
                                "title": unescape(title),
                                "content": unescape(snippet) if snippet else "",
                                "href": href,
                            })
                            if len(so_results) >= 5:
                                break

                        if so_results:
                            return json.dumps({"web_results": so_results}, ensure_ascii=False)
                    except Exception:
                        pass  # 360 也失败

                    # 全部失败，返回清晰的结果说明
                    return json.dumps({
                        "web_results": [],
                        "note": "本次搜索未返回结果，可能是因为网络限制导致搜索引擎不可用。"
                    }, ensure_ascii=False)
                except Exception as e:
                    return json.dumps({"error": f"网络搜索失败: {str(e)}"}, ensure_ascii=False)

            if not self.repo:
                return f"数据库未连接，无法执行工具: {name}"

            if name == "query_member":
                name_filter = args.get("name")
                stage_filter = args.get("stage")
                members = self.repo.get_members(stage=stage_filter)
                if name_filter:
                    members = [m for m in members if name_filter in m.get("name", "")]
                if not members:
                    return "未找到匹配的成员"
                return json.dumps(members[:5], ensure_ascii=False)  # 限制前5条

            elif name == "query_materials":
                member_id = args.get("member_id")
                if not member_id:
                    return "缺少 member_id"
                materials = self.repo.get_materials(member_id)
                return json.dumps(materials, ensure_ascii=False)

            elif name == "query_reminders":
                member_id = args.get("member_id")
                reminders = self.repo.get_reminders(member_id=member_id)
                return json.dumps(reminders, ensure_ascii=False)

            elif name == "get_dashboard_summary":
                # 简单聚合
                members = self.repo.get_members()
                reminders = self.repo.get_reminders()
                summary = {
                    "total_members": len(members),
                    "pending_reminders": len([r for r in reminders if not r.get("is_sent")]),
                }
                return json.dumps(summary, ensure_ascii=False)

            elif name == "create_reminder":
                # 返回特定的标识，让 agent 知道这是个需要确认的操作
                # 在此阶段我们不直接写入，要求前端提供确认
                title = args.get("title")
                return f"⏳ 待确认：已向前端发出创建待办提醒卡片（{title}），请等待用户确认后才算真正生效。"

            elif name == "add_member_memory":
                content = args.get("content", "")
                return f"⏳ 待确认：已向前端发出添加成员记忆卡片（{content[:20]}...），请等待用户确认后才算真正生效。"

            elif name == "get_current_time":
                from datetime import datetime
                _weekdays = ["一", "二", "三", "四", "五", "六", "日"]
                now = datetime.now()
                return now.strftime(f"%Y年%m月%d日 %H:%M:%S (星期{_weekdays[now.weekday()]})")

            elif name == "run_python_code":
                code = args.get("code", "")
                return f"⏳ 待确认：已向前端发出Python代码执行请求，请等待用户批准。代码预览:\n{code[:50]}..."

            return f"未知工具: {name}"
        except Exception as e:
            return f"工具执行出错: {str(e)}"