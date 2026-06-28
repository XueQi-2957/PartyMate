"""
PartyMate Agent — 党务智能助手核心 (ReAct Stream 升级版)

支持：
- SessionMemory (多轮对话, 记忆层)
- AgentToolRegistry (业务工具)
- SSE 流式输出 (思考过程、工具调用、打字机内容)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, AsyncGenerator

import httpx

from partymate.db.repository import Repository
from partymate.services.agent_trace_service import AgentTraceService
from partymate.tools.agent_tools import AgentToolRegistry
from partymate.chat_memory import SessionMemory

logger = logging.getLogger(__name__)

# ---------- 配置 ---------- #
API_BASE = os.getenv("PARTYMATE_API_BASE") or os.getenv("OPENAI_BASE_URL") or "http://127.0.0.1:11434/v1"
API_KEY = os.getenv("PARTYMATE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
MODEL = os.getenv("PARTYMATE_MODEL") or os.getenv("HERMES_MODEL") or "gemma4:latest"

SYSTEM_PROMPT_TEMPLATE = """你是一名经验丰富的高校党务工作助手，名叫 PartyMate。

## 你的角色
你是高校学生党支部的党务智能助手，帮助党务负责人完成日常工作。
你的回答要专业、准确、务实，使用中文。

## 当前时间
{current_datetime}

## 你的能力
你可以通过调用工具来查询成员状态、管理提醒、检查材料、生成方案以及在党务知识库中检索规程。
遇到不懂或不确定的规范时，请先调用 search_knowledge 工具检索知识库。
如需要获取实时信息（如天气、新闻、最新动态），请调用 web_search 工具联网搜索。
对于天气查询，请优先使用 get_weather 工具（比 web_search 更可靠，支持中文城市名）。
需要获取当前准确时间时，可调用 get_current_time 工具。
如果需要进行复杂的数据处理、计算或测试，可以调用 run_python_code 工具执行Python代码。

## 回答风格
- 专业但不生硬，用自然的中文回答
- 检查材料时：逐项列出问题，标注严重程度（❌错误/⚠️警告/✅通过），给出具体修改建议
- 生成内容时：给出完整方案，标注来源和建议

## 来源引用规范 (非常重要)
- 当你调用了 `search_knowledge` 工具或 `web_search` 工具找到相关信息时，**必须且只能**在回答的末尾或者相应的段落，使用数字角标格式标出引用来源。
- 检索知识库的标号格式是 `[1]`, `[2]` 等，联网搜索的标号格式是 `[W1]`, `[W2]` 等。这取决于工具返回的 JSON 数据中的 `id` 字段。
- 格式示例："根据工作规程，入党申请人必须具备特定条件[1]。" 或 "根据最新的新闻报道，该事件已经平息[W1]。"
- 绝对不要编造标号，必须严格使用工具返回 JSON 里的 `id`。
- 绝对不要输出书名号《xxx》作为引用，必须只输出括号加 ID，例如 `[1]`。

## ReAct 多轮推理：逐步思考，规划行动
你可以逐步解决问题——每次调用一个工具前，**先在脑海中明确你的计划**：当前用户需要什么？我具备哪些信息？还需要获取什么？

每次行动的流程是：
1. **思考**：写下你对当前情况的推理（用户真正想要什么，当前已知和未知分别是什么）
2. **行动**：调用 1 个工具
3. **观察**：接收工具返回的观测结果
4. **再思考**：根据结果重新评估——信息够了吗？不够就再行动，够了就给出最终答案

每一步都先写思考再行动，不要跳过推理直接跳到结论。系统的最大轮次为 10 轮，请合理安排工具调用顺序。

每次观测结果结束后，请主动判断：信息是否足够回答用户问题？不够就继续调用，够了就输出最终回答。

## 工具调用规范
**重要**: 在决定调用任何工具之前，你必须先用一两句简短的自然语言告诉用户你接下来打算做什么，例如："我来为您查询一下当前的成员状态。"，然后再输出 `tool_calls`。

## 严禁编造实时信息 (极其重要)
- 对于天气、新闻、实时数据等时效性信息，你**绝对不能**凭记忆回答，**必须**先调用 `web_search` 工具获取实时数据，等待工具返回结果后再据此回答。
- 遇到与时间相关的请求（如"今天是几号"）时，如果系统提供的当前时间不够，请使用 `get_current_time` 工具验证，**绝对不要编造日期**。
- 如果工具调用失败或返回空结果，你必须如实告知用户"搜索失败，暂时无法获取该信息"，**绝对不要编造任何数据**。
- 对于你不确定的党务规定，**必须**先调用 `search_knowledge` 检索知识库，不要凭记忆回答。

## 完成任务的核心规则 (极其重要)
- **说到做到**：当你说"我来查一下"或"我来看看"时，**这个回合内就必须同时发出对应的工具调用**，不能只停留在口头承诺。
- **禁止只说不做**：绝不能只输出思考过程或计划就结束一个回合。每个回复要么包含至少一个工具调用（表示你正在执行），要么就是最终的完整答案。
- **失败也要诚实**：如果工具调用失败或返回空结果，如实告知用户"搜索失败"或"未找到相关信息"，**绝对不能编造数据**来填补空缺。
- **持续直到完成**：不要写一个计划、一条命令就停止。持续工作，直到你真正执行了代码、查询到了数据、产生了所请求的结果，然后报告真实执行返回了什么。

## 回复格式规范
- **还在处理中**：如果你已经调用了工具、收到了结果，但还需要继续处理（比如再查一个工具或综合分析），请在回复开头加上 `[进度]` 标记。
- **任务完成**：只有当任务**真正完成**、你不再需要调用任何工具时，才给出最终回答（不加任何标记）。
- **禁止空承诺**：不要以"我将要查一下"或"下一步我准备"来结束回合。要么给出最终答案，要么继续工具调用。
- **高效并行**：当需要多个互不依赖的信息时（如同时查天气和查新闻），**一次性并行调用所有独立工具**，而不是逐个串行调用。只有前一个工具的结果确实影响后一个工具时，才串行执行。
"""


async def run_agent_stream(
    user_input: str,
    session_id: str,
    repo: Repository,
    member_context: str = "",
    trace_service: AgentTraceService | None = None,
    member_id: int | None = None,
    mcp_session: Any = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """异步流式运行 Agent，产出 SSE 事件。"""
    
    # 动态读取配置（支持 .env 修改后不重启生效）
    from datetime import datetime
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass
    api_base = os.getenv("PARTYMATE_API_BASE") or os.getenv("OPENAI_BASE_URL") or API_BASE
    api_key  = os.getenv("PARTYMATE_API_KEY")  or os.getenv("OPENAI_API_KEY")  or API_KEY
    model    = os.getenv("PARTYMATE_MODEL")    or os.getenv("HERMES_MODEL")    or MODEL

    if not api_key and "127.0.0.1" not in api_base and "localhost" not in api_base:
        yield {"event": "error", "data": "⚠️ 未设置 API Key。本地 Ollama 不需要 Key，如需使用外部 API 请设置 PARTYMATE_API_KEY。"}
        return

    # 注入当前日期时间
    _weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    now = datetime.now()
    weekday_cn = _weekdays[now.weekday()]
    current_datetime = now.strftime(f"%Y年%m月%d日 %H:%M (星期{weekday_cn})")
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(current_datetime=current_datetime)

    # 1. 准备上下文与记忆
    memory = SessionMemory(session_id, repo)
    await memory.add_message("user", user_input)
    
    context_msgs = await memory.get_context_messages(user_input)
    
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    if member_context.strip():
        messages.append({"role": "system", "content": member_context.strip()})
        
    messages.extend(context_msgs)


    # 2. 准备工具
    registry = AgentToolRegistry(repo, mcp_session=mcp_session)
    tools = registry.get_schemas()

    # 3. ReAct 循环
    run_id: str | None = None
    start_time: float | None = None
    if trace_service:
        run_id, start_time = trace_service.start_run(
            user_input=user_input,
            member_id=member_id,
            model_used=model,
        )

    call_order = 0
    final_content = ""
    tool_calls_history = []

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
            # ── P3: 上下文压缩状态 ──
            compression_turn_threshold = 7  # 第7轮起考虑压缩
            compressed = False

            for turn in range(10):  # 最多10轮
                # ── P3: 接近轮次上限时，压缩早期对话 ──
                if turn >= compression_turn_threshold and not compressed:
                    compressed = True
                    # 找到第一个 system 消息，压缩其后的对话历史
                    compressed_msgs = [messages[0]]  # 保留 system prompt
                    user_msg = None
                    # 只压缩 user + assistant 间的工具调用历史
                    for i, m in enumerate(messages):
                        if i == 0:
                            continue
                        if m["role"] == "user" and user_msg is None:
                            user_msg = m  # 保留最近一条用户消息
                        elif m["role"] == "tool":
                            continue  # 跳过工具结果
                        elif m["role"] == "assistant":
                            # 只保留有最终文本的 assistant 消息，跳过纯工具调用
                            if m.get("content", "").strip():
                                compressed_msgs.append(m)
                    if user_msg:
                        compressed_msgs.append(user_msg)
                    if len(compressed_msgs) < len(messages):
                        messages = compressed_msgs
                        logger.info("Context compressed: %d -> %d messages", len(messages), len(compressed_msgs))
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                    
                body = {
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "stream": True,
                }
                
                content_acc = ""
                tool_calls_acc: dict[int, dict] = {}
                # 本轮 content 先缓冲，不立即发送
                content_buffer: list[str] = []
                
                async with client.stream("POST", f"{api_base}/chat/completions", headers=headers, json=body) as resp:
                    if resp.status_code != 200:
                        text = await resp.aread()
                        err = f"API 错误: HTTP {resp.status_code} - {text.decode('utf-8')[:200]}"
                        yield {"event": "error", "data": err}
                        if trace_service and run_id and start_time:
                            trace_service.finish_run(run_id, start_time, err, status="error")
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                            
                        data = json.loads(line[6:])
                        delta = data["choices"][0].get("delta", {})
                        
                        # 思考过程 (如 DeepSeek 的 reason_content)
                        if "reasoning_content" in delta and delta["reasoning_content"]:
                            yield {"event": "thinking", "data": delta["reasoning_content"]}
                            
                        # 内容累加 —— 先缓冲，不立即发给前端
                        if "content" in delta and delta["content"]:
                            content_chunk = delta["content"]
                            content_acc += content_chunk
                            content_buffer.append(content_chunk)
                            
                        # 工具调用累加
                        if "tool_calls" in delta:
                            for tc in delta["tool_calls"]:
                                index = tc["index"]
                                if index not in tool_calls_acc:
                                    tool_calls_acc[index] = {"id": tc.get("id", ""), "type": "function", "function": {"name": "", "arguments": ""}}
                                if "id" in tc and tc["id"]:
                                    tool_calls_acc[index]["id"] = tc["id"]
                                if "function" in tc:
                                    if "name" in tc["function"] and tc["function"]["name"]:
                                        tool_calls_acc[index]["function"]["name"] += tc["function"]["name"]
                                    if "arguments" in tc["function"] and tc["function"]["arguments"]:
                                        tool_calls_acc[index]["function"]["arguments"] += tc["function"]["arguments"]

                # ── 本轮流式结束，决定如何处理缓冲的 content ──
                if tool_calls_acc:
                    # 有工具调用 → content 只是中间思考/过渡话术，不作为正式回答
                    if content_acc.strip():
                        yield {"event": "thinking", "data": content_acc}
                    else:
                        # 某些模型不输出 content 文本就直接跳 tool_calls（如 gemma4）
                        # 自动生成通用思考描述，让前端有东西显示
                        tool_names = []
                        for tc in tool_calls_acc.values():
                            n = tc["function"]["name"]
                            tool_names.append(n)
                        if tool_names:
                            desc = "、".join(tool_names[:3])
                            desc_more = "等" if len(tool_names) > 3 else ""
                            yield {"event": "thinking", "data": f"我准备调用 {desc}{desc_more} 来获取信息。"}
                    # 无工具调用 → 这是最终回答，将缓冲内容作为正式 content 发送
                else:
                    for chunk in content_buffer:
                        yield {"event": "content", "data": chunk}

                # 追加到消息上下文
                msg_to_append = {"role": "assistant", "content": content_acc}
                if tool_calls_acc:
                    msg_to_append["tool_calls"] = list(tool_calls_acc.values())
                    tool_calls_history.extend(msg_to_append["tool_calls"])
                    
                messages.append(msg_to_append)
                final_content += content_acc
                
                if not tool_calls_acc:
                    # 没有工具调用，循环结束
                    break
                    
                # 执行工具调用
                for tc in tool_calls_acc.values():
                    func_name = tc["function"]["name"]
                    func_args_str = tc["function"]["arguments"]
                    yield {"event": "tool_call", "data": {"name": func_name, "args": func_args_str}}
                    
                    try:
                        func_args = json.loads(func_args_str)
                    except json.JSONDecodeError:
                        func_args = {}
                        
                    t1 = time.time()
                    result = await registry.execute(func_name, func_args)
                    tool_ms = int((time.time() - t1) * 1000)
                    call_order += 1
                    
                    yield {"event": "tool_result", "data": {"name": func_name, "result": result}}
                    
                    if trace_service and run_id:
                        trace_service.record_tool_call(
                            run_id=run_id,
                            tool_name=func_name,
                            arguments=func_args,
                            result=result,
                            call_order=call_order,
                            duration_ms=tool_ms,
                        )
                        
                    # 将工具结果包裹为结构化观测格式，让 LLM 清晰感知执行结果
                    observation = (
                        f"━━━ 工具执行结果 ━━━\n"
                        f"工具：{func_name}\n"
                        f"参数：{json.dumps(func_args, ensure_ascii=False)}\n"
                        f"结果：\n{result}\n"
                        f"━━━━━━━━━━━━━━━━━"
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": observation,
                    })

            # ReAct 循环结束，追加助手消息到记忆库
            await memory.add_message("assistant", final_content, tool_calls_history if tool_calls_history else None)
            yield {"event": "done", "data": ""}
            
            if trace_service and run_id and start_time is not None:
                trace_service.finish_run(run_id, start_time, final_content)
                
    except Exception as e:
        err = f"Agent 运行异常: {str(e)}"
        yield {"event": "error", "data": err}
        if trace_service and run_id and start_time is not None:
            trace_service.finish_run(run_id, start_time, err, status="error")


async def run_agent(*args, **kwargs) -> str:
    """兼容旧版的非流式调用"""
    # 简单的向下兼容包装
    raise NotImplementedError("run_agent is deprecated. Use run_agent_stream via SSE instead.")