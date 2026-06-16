"""
PartyMate Web 服务器 — 党务智能助手 Web 界面后端

启动:
  uv run python -m partymate.web.server

访问:
  http://localhost:8567
"""

from __future__ import annotations

import os
import re
import sys
import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

HERE = Path(__file__).parent.parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from partymate.db.repository import Repository
from partymate.exporters import export_content_pptx, export_meeting_docx
from partymate.services import (
    AgentTraceService,
    MaterialCheckService,
    MaterialImportService,
    MeetingWorkflowService,
    MemberMemoryService,
    MemberViewService,
    OCRReviewService,
)
from partymate.tools.content_gen import format_content_plan, generate_meeting_content
from partymate.tools.doc_check import check_document, detect_doc_type
from partymate.tools.file_parser import SUPPORTED_EXTS, parse_file, preview_from_bytes
from partymate.tools.meeting_summary import format_meeting_summary, parse_meeting_notes


OUTPUT_DIR = HERE / "output"
STATIC_DIR = HERE / "partymate" / "web" / "static"
UPLOAD_DIR = HERE / ".uploads"


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _emit_startup_banner(stream=None) -> None:
    target = stream or sys.stdout
    encoding = getattr(target, "encoding", None) or "utf-8"
    lines = [
        "PartyMate Web 界面启动: http://localhost:8567",
        f"支持文件格式: {', '.join(SUPPORTED_EXTS)}",
        f"导出目录: {OUTPUT_DIR}",
        f"上传目录: {UPLOAD_DIR}",
    ]
    for line in lines:
        try:
            target.write(f"{line}\n")
        except UnicodeEncodeError:
            safe_line = line.encode(encoding, errors="replace").decode(
                encoding,
                errors="replace",
            )
            target.write(f"{safe_line}\n")
    flush = getattr(target, "flush", None)
    if callable(flush):
        flush()


@asynccontextmanager
async def lifespan(app: Starlette):
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "partymate.mcp_server"],
        env=None
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            app.state.mcp_session = session
            yield

def create_app(
    repository: Repository | None = None,
    data_root: Path | None = None,
) -> Starlette:
    repo = repository or Repository()
    base_data_root = data_root or (HERE / "data")
    member_views = MemberViewService(repo)
    import_service = MaterialImportService(repo=repo, data_root=base_data_root)
    check_service = MaterialCheckService(repo)
    memory_service = MemberMemoryService(repo)
    ocr_reviews = OCRReviewService(repo=repo, data_root=base_data_root)
    trace_service = AgentTraceService(repo)
    meeting_workflow = MeetingWorkflowService(repo)

    async def api_check_doc(request):
        body = await request.json()
        raw_text = body.get("raw", "")
        file_path = body.get("file_path", "")

        if file_path:
            parsed = parse_file(file_path)
            if parsed.get("error"):
                return JSONResponse({"error": parsed["error"]}, status_code=400)
            raw_text = parsed["text"]

        if not raw_text:
            return JSONResponse({"error": "请提供材料内容或上传文件"}, status_code=400)

        result = check_document(raw_text)
        doc_type = detect_doc_type(raw_text) or "未知"
        try:
            mcp_res = await request.app.state.mcp_session.call_tool("rag_search_with_fallback", {"query": raw_text})
            citations = mcp_res.content[0].text
        except Exception as e:
            citations = f"引用获取失败: {e}"

        return JSONResponse(
            {
                "result": result,
                "citations": citations,
                "doc_type": doc_type,
                "word_count": len(raw_text),
            }
        )

    async def api_upload(request):
        _ensure_upload_dir()
        form = await request.form()
        file: UploadFile | None = form.get("file")
        if not file:
            return JSONResponse({"error": "未上传文件"}, status_code=400)
        try:
            filename = file.filename or "unknown"
            ext = Path(filename).suffix.lower()
            if ext not in SUPPORTED_EXTS:
                return JSONResponse(
                    {
                        "error": f"不支持的文件格式: {ext}。支持: {', '.join(SUPPORTED_EXTS)}"
                    },
                    status_code=400,
                )

            data = await file.read()
            save_path = UPLOAD_DIR / filename
            save_path.write_bytes(data)

            parsed = preview_from_bytes(filename, data)
            if parsed.get("error"):
                return JSONResponse({"error": parsed["error"]}, status_code=400)

            return JSONResponse(
                {
                    "filename": filename,
                    "type": parsed["type"],
                    "text": parsed["text"],
                    "preview": parsed["preview"],
                    "pages": parsed["pages"],
                    "file_path": str(save_path),
                    "saved": True,
                }
            )
        finally:
            await file.close()

    async def api_meeting(request):
        body = await request.json()
        raw_text = body.get("raw", "")
        file_path = body.get("file_path", "")

        if file_path:
            parsed = parse_file(file_path)
            if parsed.get("error"):
                return JSONResponse({"error": parsed["error"]}, status_code=400)
            raw_text = parsed["text"]

        if not raw_text:
            return JSONResponse({"error": "请提供会议记录"}, status_code=400)

        raw_json = parse_meeting_notes(raw_text)
        result = format_meeting_summary(raw_json)
        docx_path = export_meeting_docx(raw_json) if body.get("export_docx") else None
        return JSONResponse(
            {
                "result": result,
                "docx_path": str(docx_path) if docx_path else None,
            }
        )

    async def api_content(request):
        body = await request.json()
        topic = body.get("topic", "")
        if not topic:
            return JSONResponse({"error": "请提供学习主题"}, status_code=400)

        raw_json = generate_meeting_content(topic)
        result = format_content_plan(raw_json)
        try:
            mcp_res = await request.app.state.mcp_session.call_tool("rag_search_with_fallback", {"query": topic})
            citations = mcp_res.content[0].text
        except Exception as e:
            citations = f"引用获取失败: {e}"
        pptx_path = export_content_pptx(raw_json) if body.get("export_pptx") else None
        return JSONResponse(
            {
                "result": result,
                "citations": citations,
                "pptx_path": str(pptx_path) if pptx_path else None,
            }
        )

    async def api_chat_stream(request):
        from starlette.responses import StreamingResponse
        import json
        body = await request.json()
        message = body.get("message", "")
        session_id = body.get("session_id")
        member_id = body.get("member_id")

        if not message:
            return JSONResponse({"error": "请输入消息"}, status_code=400)
        if not session_id:
            return JSONResponse({"error": "缺少 session_id"}, status_code=400)

        try:
            from partymate.agent import run_agent_stream
            
            member_context = ""
            if member_id is not None:
                member = repo.get_member(int(member_id))
                if not member:
                    return JSONResponse({"error": "成员未找到"}, status_code=404)
                member_context = memory_service.build_agent_context(int(member_id))
            
            async def event_generator():
                try:
                    async for event in run_agent_stream(
                        message,
                        session_id=session_id,
                        repo=repo,
                        member_context=member_context,
                        trace_service=trace_service,
                        member_id=int(member_id) if member_id else None,
                        mcp_session=request.app.state.mcp_session,
                    ):
                        data_str = json.dumps(event["data"], ensure_ascii=False)
                        yield f"event: {event['event']}\ndata: {data_str}\n\n"
                except Exception as e:
                    yield f"event: error\ndata: {json.dumps(str(e), ensure_ascii=False)}\n\n"
            
            return StreamingResponse(event_generator(), media_type="text/event-stream")
        except Exception as e:
            return JSONResponse({"error": f"❌ 出错: {e}"}, status_code=500)

    async def api_chat_sessions(request):
        if request.method == "POST":
            import uuid
            try:
                body = await request.json()
            except Exception:
                body = {}
            title = body.get("title", "新对话")
            member_id = body.get("member_id")
            session_id = str(uuid.uuid4())
            session = repo.create_chat_session(session_id, title=title, member_id=member_id)
            return JSONResponse(session)
        else:
            sessions = repo.list_chat_sessions()
            return JSONResponse({"sessions": sessions})

    async def api_chat_session_rename(request):
        """PATCH /api/chat/sessions/{session_id} — 更新会话标题"""
        session_id = request.path_params.get("session_id")
        try:
            body = await request.json()
        except Exception:
            body = {}
        title = body.get("title", "").strip()
        if not title:
            return JSONResponse({"error": "标题不能为空"}, status_code=400)
        repo.update_chat_session(session_id, title=title)
        return JSONResponse({"ok": True, "title": title})

    async def api_chat_session_generate_title(request):
        """POST /api/chat/sessions/{session_id}/rename-title — LLM 生成会话标题"""
        session_id = request.path_params.get("session_id")
        try:
            body = await request.json()
        except Exception:
            body = {}
        question = body.get("question", "").strip()
        if not question:
            return JSONResponse({"error": "缺少 question"}, status_code=400)

        # 使用和 agent 相同的 LLM 配置
        api_base = os.getenv("PARTYMATE_API_BASE") or os.getenv("OPENAI_BASE_URL") or "http://127.0.0.1:11434/v1"
        api_key = os.getenv("PARTYMATE_API_KEY") or os.getenv("OPENAI_API_KEY") or "ollama"
        model = os.getenv("PARTYMATE_MODEL") or os.getenv("HERMES_MODEL") or "qwen3.5:4b"

        try:
            prompt = f"请将以下问题概括为一个简洁的话题标题（不超过12个字，不含标点和引号），只输出标题本身，不要任何解释：\n\n{question[:200]}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{api_base.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 30,
                        "temperature": 0.3,
                        "stream": False,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw = data["choices"][0]["message"]["content"].strip()
                    # 清理：去掉引号、书名号、换行
                    import re
                    title = re.sub(r'[《》「」【】""\'"\n\r]', '', raw).strip()[:20] or question[:12]
                else:
                    title = question[:12]
        except Exception:
            title = question[:12]

        # 更新数据库
        repo.update_chat_session(session_id, title=title)
        return JSONResponse({"ok": True, "title": title})

    async def api_chat_session_delete(request):
        session_id = request.path_params.get("session_id")
        repo.delete_chat_session(session_id)
        return JSONResponse({"success": True})

    async def api_chat_session_messages(request):
        session_id = request.path_params.get("session_id")
        messages = repo.get_chat_messages(session_id)
        return JSONResponse({"messages": messages})

    async def api_status(request):  # pragma: no cover - runtime/environment probe
        import httpx

        ollama_ok = False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get("http://127.0.0.1:11434/api/tags")
                ollama_ok = response.status_code == 200
        except Exception:
            pass

        ocr_ok = False
        try:
            import easyocr  # noqa: F401

            ocr_ok = True
        except ImportError:
            pass

        try:
            mcp_res = await request.app.state.mcp_session.call_tool("rag_status", {})
            rag_status = json.loads(mcp_res.content[0].text)
        except Exception:
            rag_status = {"ready": False, "chunks": 0, "message": "MCP Server Not Connected"}

        return JSONResponse(
            {
                "status": "ok",
                "ollama": ollama_ok,
                "ocr": ocr_ok,
                "rag": rag_status,
                "version": "1.3.0",
                "supported_formats": list(SUPPORTED_EXTS),
                "tools": ["check-doc", "meeting", "content", "chat"],
            }
        )

    async def api_download(request):
        path = request.query_params.get("path", "")
        if not path or ".." in path:
            return PlainTextResponse("Invalid path", status_code=400)
        file_path = Path(path)
        if not file_path.exists() or not file_path.is_file():
            return PlainTextResponse("File not found", status_code=404)
        return FileResponse(str(file_path))

    async def api_members(request):
        stage = request.query_params.get("stage", "")
        members = repo.get_members(stage=stage if stage else None)
        return JSONResponse({"members": members})

    async def api_add_member(request):
        data = await request.json()
        stage = data.pop("stage", "applicant")
        member = repo.add_member(**data)
        valid_stages = [
            "applicant",
            "activist",
            "candidate",
            "probationary",
            "full_member",
        ]
        if stage in valid_stages and stage != "applicant":
            target_idx = valid_stages.index(stage)
            current_member = member
            for _ in range(target_idx):
                try:
                    current_member = repo.advance_stage(
                        current_member["id"],
                        event_date=data.get("apply_date", ""),
                    )
                except ValueError:
                    break
            member = current_member
        return JSONResponse({"member": member_views.build_member_detail(member["id"])})

    async def api_get_member(request):
        member = member_views.build_member_detail(int(request.path_params["member_id"]))
        if not member:
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        return JSONResponse({"member": member})

    async def api_list_member_memories(request):
        member_id = int(request.path_params["member_id"])
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        memories = memory_service.list_memories(member_id, include_merged=False, limit=50)
        return JSONResponse({"memories": memories})

    async def api_create_member_memory(request):
        member_id = int(request.path_params["member_id"])
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        body = await request.json()
        try:
            memory = memory_service.create_memory(
                member_id=member_id,
                kind=body.get("kind", ""),
                title=body.get("title", ""),
                content=body.get("content", ""),
                importance=body.get("importance", 2),
                pinned=bool(body.get("pinned", False)),
                source=body.get("source", "manual"),
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"memory": memory})

    async def api_merge_member_memories(request):
        member_id = int(request.path_params["member_id"])
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        body = await request.json()
        try:
            memory = memory_service.merge_memories(
                member_id=member_id,
                memory_ids=[int(item) for item in body.get("memory_ids", [])],
                kind=body.get("kind", ""),
                title=body.get("title", ""),
                content=body.get("content", ""),
                importance=body.get("importance", 2),
                pinned=bool(body.get("pinned", False)),
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"memory": memory})

    async def api_update_member_memory(request):
        member_id = int(request.path_params["member_id"])
        memory_id = int(request.path_params["memory_id"])
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        current = repo.get_member_memory(memory_id)
        if not current or int(current.get("member_id", 0)) != member_id:
            return JSONResponse({"error": "记忆未找到"}, status_code=404)
        body = await request.json()
        try:
            memory = memory_service.update_memory(
                memory_id,
                title=body.get("title", current.get("title", "")),
                content=body.get("content", current.get("content", "")),
                importance=body.get("importance", current.get("importance", 2)),
                pinned=body.get("pinned", bool(current.get("pinned"))),
            )
        except ValueError as exc:
            status_code = 404 if "not found" in str(exc) else 400
            return JSONResponse({"error": str(exc)}, status_code=status_code)
        return JSONResponse({"memory": memory})

    async def api_delete_member_memory(request):
        member_id = int(request.path_params["member_id"])
        memory_id = int(request.path_params["memory_id"])
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        current = repo.get_member_memory(memory_id)
        if not current or int(current.get("member_id", 0)) != member_id:
            return JSONResponse({"error": "记忆未找到"}, status_code=404)
        ok = memory_service.delete_memory(memory_id)
        return JSONResponse({"ok": ok})

    async def api_update_member(request):
        member_id = int(request.path_params["member_id"])
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        data = await request.json()
        member = repo.update_member(member_id, **data)
        return JSONResponse({"member": member_views.build_member_detail(member["id"])})

    async def api_advance(request):
        member_id = int(request.path_params["member_id"])
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        data = await request.json() or {}
        member = repo.advance_stage(member_id, event_date=data.get("event_date", ""))
        return JSONResponse({"member": member_views.build_member_detail(member["id"])})

    async def api_submit_material(request):
        member_id = int(request.path_params["member_id"])
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        data = await request.json()
        material = repo.submit_material(
            int(data["material_id"]),
            file_path=data.get("file_path", ""),
        )
        if not material:
            return JSONResponse({"error": "材料未找到"}, status_code=404)
        return JSONResponse({"material": material})

    async def api_member_material_check(request):
        member_id = int(request.path_params["member_id"])
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        body = await request.json()
        result = check_service.run_for_member(member_id, body.get("batch_id"))
        return JSONResponse(result)

    async def api_get_ocr_task(request):
        task_id = int(request.path_params["task_id"])
        detail = ocr_reviews.build_task_detail(task_id)
        if not detail:
            return JSONResponse({"error": "OCR 任务未找到"}, status_code=404)
        return JSONResponse(detail)

    async def api_confirm_ocr_task(request):
        body = await request.json()
        task_id = int(body.get("task_id", 0))
        try:
            task = ocr_reviews.confirm_task(
                task_id=task_id,
                confirmed_text=body.get("confirmed_text", ""),
                review_notes=body.get("review_notes", ""),
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "not found" in message else 400
            return JSONResponse({"error": message}, status_code=status_code)
        return JSONResponse({"task": task})

    async def api_add_event(request):
        member_id = int(request.path_params["member_id"])
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        data = await request.json()
        event = repo.add_event(member_id, **data)
        return JSONResponse({"event": event})

    async def api_dashboard(request):
        return JSONResponse(member_views.build_dashboard())

    async def api_reminders(request):
        return JSONResponse({"reminders": member_views.build_reminders()})

    async def api_delete_member(request):
        repo.delete_member(int(request.path_params["member_id"]))
        return JSONResponse({"ok": True})

    async def api_import_members(request):
        form = await request.form()
        file = form.get("file")
        if not file:
            return JSONResponse({"error": "未上传文件"}, status_code=400)
        try:
            content = (await file.read()).decode("utf-8-sig")
            from partymate.scripts.import_members import import_from_csv

            result = import_from_csv(content)
            return JSONResponse(result)
        finally:
            await file.close()

    async def api_material_archive_import(request):
        form = await request.form()
        file: UploadFile | None = form.get("file")
        member_id = int(form.get("member_id", "0"))
        if not file or not file.filename:
            return JSONResponse({"error": "未上传文件"}, status_code=400)
        try:
            if Path(file.filename).suffix.lower() != ".zip":
                return JSONResponse({"error": "仅支持 zip 材料包"}, status_code=400)
            if not repo.get_member(member_id):
                return JSONResponse({"error": "成员未找到"}, status_code=404)

            result = import_service.import_archive(
                member_id=member_id,
                archive_name=file.filename,
                archive_bytes=await file.read(),
            )
            return JSONResponse(result)
        finally:
            await file.close()

    # ── Meeting Action Workflow Endpoints ─────────────────────

    async def api_meeting_parse_actions(request):
        """Parse meeting summary JSON and auto-write actions as reminders."""
        body = await request.json()
        raw_text = body.get("raw", "")
        meeting_title = body.get("meeting_title", "")
        member_id = body.get("member_id")
        if not raw_text:
            return JSONResponse({"error": "请提供会议记录文本"}, status_code=400)

        raw_json = parse_meeting_notes(raw_text)
        result = format_meeting_summary(raw_json)

        # Parse and write actions
        workflow_result = meeting_workflow.parse_and_write_actions(
            raw_json,
            meeting_title=meeting_title,
            member_id=int(member_id) if member_id else None,
        )

        return JSONResponse({
            "result": result,
            "workflow": workflow_result,
        })

    async def api_meeting_actions_list(request):
        status_filter = request.query_params.get("status", "pending")
        actions = meeting_workflow.list_pending_actions(limit=100)
        if status_filter:
            actions = [a for a in actions if a.get("status") == status_filter]
        return JSONResponse({"actions": actions})

    async def api_meeting_action_confirm(request):
        action_id = int(request.path_params["action_id"])
        action = meeting_workflow.confirm_action(action_id)
        return JSONResponse({"action": action})

    async def api_meeting_action_complete(request):
        action_id = int(request.path_params["action_id"])
        action = meeting_workflow.complete_action(action_id)
        return JSONResponse({"action": action})

    async def api_meeting_action_delete(request):
        action_id = int(request.path_params["action_id"])
        ok = repo.delete_meeting_action(action_id)
        return JSONResponse({"ok": ok})

    # ── Agent Run Trace Endpoints ────────────────────────────

    async def api_agent_runs(request):
        member_id = request.query_params.get("member_id")
        runs = trace_service.list_runs(
            limit=30,
            member_id=int(member_id) if member_id else None,
        )
        return JSONResponse({"runs": runs})

    async def api_agent_run_detail(request):
        run_id = request.path_params["run_id"]
        detail = trace_service.get_run_detail(run_id)
        if not detail:
            return JSONResponse({"error": "运行记录未找到"}, status_code=404)
        return JSONResponse({"run": detail})

    async def api_create_reminder(request):
        body = await request.json()
        member_id = body.get("member_id")
        title = body.get("title", "")
        description = body.get("description", "")
        due_date = body.get("due_date", "")
        if not member_id or not title:
            return JSONResponse({"error": "缺少 member_id 或 title"}, status_code=400)
        repo.add_reminder(member_id=int(member_id), title=title, description=description, due_date=due_date)
        return JSONResponse({"success": True})

    # ── Settings Endpoints ───────────────────────────────────

    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    SETTINGS_VARS = {
        "api_base": ("PARTYMATE_API_BASE", "http://127.0.0.1:11434/v1"),
        "api_key": ("PARTYMATE_API_KEY", ""),
        "model": ("PARTYMATE_MODEL", "qwen3.5:4b"),
    }

    def _read_env_file() -> dict[str, str]:
        env_path = PROJECT_ROOT / ".env"
        result: dict[str, str] = {}
        if not env_path.exists():
            return result
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                result[k.strip()] = v.strip().strip("\"'")
        return result

    def _write_env_file(updates: dict[str, str]) -> None:
        env_path = PROJECT_ROOT / ".env"
        lines: list[str] = []
        written_keys: set[str] = set()

        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                key = stripped.split("=", 1)[0].strip() if "=" in stripped else None
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                    written_keys.add(key)
                else:
                    lines.append(line)
        else:
            lines.append("# PartyMate 配置")

        for key, val in updates.items():
            if key not in written_keys:
                lines.append(f"{key}={val}")

        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    async def api_get_settings(request):
        env = _read_env_file()
        settings = {}
        for field, (env_key, default) in SETTINGS_VARS.items():
            settings[field] = env.get(env_key, default)
            settings[f"{field}_default"] = default
        return JSONResponse(settings)

    async def api_save_settings(request):
        data = await request.json()
        updates: dict[str, str] = {}
        for field, (env_key, default) in SETTINGS_VARS.items():
            if field in data:
                val = data[field]
                if val == "" or val is None:
                    val = default
                updates[env_key] = val.strip() if isinstance(val, str) else str(val)
        _write_env_file(updates)
        return JSONResponse({"ok": True, "message": "设置已保存，重启后生效"})

    async def api_rag_status(request):
        """返回 RAG 知识库状态"""
        try:
            response = await request.app.state.mcp_session.call_tool("rag_status", {})
            return JSONResponse(json.loads(response.content[0].text))
        except Exception as e:
            return JSONResponse({"ready": False, "chunks": 0, "message": str(e)})

    async def api_rag_rebuild(request):
        """重建 RAG 知识库"""
        try:
            response = await request.app.state.mcp_session.call_tool("rag_rebuild", {})
            return JSONResponse(json.loads(response.content[0].text))
        except Exception as e:
            return JSONResponse({"ready": False, "chunks": 0, "message": str(e)})

    async def api_ollama_models(request):
        """Detect locally installed ollama models."""
        import subprocess
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return JSONResponse({"models": [], "error": "ollama 未运行"})
            lines = result.stdout.strip().split("\n")
            models = []
            for line in lines[1:]:  # skip header
                parts = line.strip().split()
                if parts:
                    models.append(parts[0])
            return JSONResponse({"models": models, "current_api": _read_env_file().get("PARTYMATE_API_BASE", "")})
        except FileNotFoundError:
            return JSONResponse({"models": [], "error": "未安装 ollama"})
        except subprocess.TimeoutExpired:
            return JSONResponse({"models": [], "error": "ollama 响应超时"})

    async def api_run_python(request):
        import sys
        import io
        import traceback
        body = await request.json()
        code = body.get("code", "")
        
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirected_output = io.StringIO()
        redirected_error = io.StringIO()
        sys.stdout = redirected_output
        sys.stderr = redirected_error
        
        try:
            exec(code, {"__builtins__": __builtins__}, {})
            output = redirected_output.getvalue() + redirected_error.getvalue()
            if not output.strip():
                output = "[执行成功，无输出]"
            return JSONResponse({"output": output})
        except Exception as e:
            return JSONResponse({"output": f"执行失败:\n{traceback.format_exc()}"})
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    routes = [
        Route("/api/check-doc", api_check_doc, methods=["POST"]),
        Route("/api/upload", api_upload, methods=["POST"]),
        Route("/api/meeting", api_meeting, methods=["POST"]),
        Route("/api/content", api_content, methods=["POST"]),
        Route("/api/tools/run-python", api_run_python, methods=["POST"]),
        Route("/api/chat/stream", api_chat_stream, methods=["POST"]),
        Route("/api/chat/sessions", api_chat_sessions, methods=["GET", "POST"]),
        Route("/api/chat/sessions/{session_id}", api_chat_session_rename, methods=["PATCH"]),
        Route("/api/chat/sessions/{session_id}", api_chat_session_delete, methods=["DELETE"]),
        Route("/api/chat/sessions/{session_id}/rename-title", api_chat_session_generate_title, methods=["POST"]),
        Route("/api/chat/sessions/{session_id}/messages", api_chat_session_messages),
        Route("/api/status", api_status),
        Route("/api/download", api_download),
        Route("/api/members", api_members),
        Route("/api/members", api_add_member, methods=["POST"]),
        Route("/api/members/{member_id}", api_get_member),
        Route("/api/members/{member_id}/memories", api_list_member_memories),
        Route("/api/members/{member_id}/memories", api_create_member_memory, methods=["POST"]),
        Route("/api/members/{member_id}/memories/merge", api_merge_member_memories, methods=["POST"]),
        Route("/api/members/{member_id}/memories/{memory_id}", api_update_member_memory, methods=["PATCH"]),
        Route("/api/members/{member_id}/memories/{memory_id}", api_delete_member_memory, methods=["DELETE"]),
        Route("/api/members/{member_id}", api_update_member, methods=["PATCH"]),
        Route("/api/members/{member_id}", api_delete_member, methods=["DELETE"]),
        Route("/api/members/{member_id}/advance", api_advance, methods=["POST"]),
        Route("/api/members/{member_id}/materials", api_submit_material, methods=["POST"]),
        Route("/api/members/{member_id}/materials/check", api_member_material_check, methods=["POST"]),
        Route("/api/members/{member_id}/events", api_add_event, methods=["POST"]),
        Route("/api/materials/archive/import", api_material_archive_import, methods=["POST"]),
        Route("/api/ocr/tasks/{task_id}", api_get_ocr_task),
        Route("/api/ocr/confirm", api_confirm_ocr_task, methods=["POST"]),
        Route("/api/dashboard", api_dashboard),
        Route("/api/reminders", api_reminders),
        Route("/api/reminders", api_create_reminder, methods=["POST"]),
        Route("/api/members/import", api_import_members, methods=["POST"]),
        # Meeting action workflow
        Route("/api/meeting/parse-actions", api_meeting_parse_actions, methods=["POST"]),
        Route("/api/meeting/actions", api_meeting_actions_list),
        Route("/api/meeting/actions/{action_id}/confirm", api_meeting_action_confirm, methods=["POST"]),
        Route("/api/meeting/actions/{action_id}/complete", api_meeting_action_complete, methods=["POST"]),
        Route("/api/meeting/actions/{action_id}", api_meeting_action_delete, methods=["DELETE"]),
        # Agent run trace
        Route("/api/agent/runs", api_agent_runs),
        Route("/api/agent/runs/{run_id}", api_agent_run_detail),
        # Settings
        Route("/api/settings", api_get_settings),
        Route("/api/settings", api_save_settings, methods=["POST"]),
        Route("/api/settings/ollama-models", api_ollama_models),
        # RAG
        Route("/api/rag/status", api_rag_status),
        Route("/api/rag/rebuild", api_rag_rebuild, methods=["POST"]),
        Mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static"),
    ]

    return Starlette(debug=False, routes=routes, lifespan=lifespan)


app = create_app()


if __name__ == "__main__":  # pragma: no cover - manual run path
    import uvicorn

    _emit_startup_banner()
    uvicorn.run(app, host="0.0.0.0", port=8567, log_level="info")
