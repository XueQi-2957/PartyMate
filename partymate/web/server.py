"""
PartyMate Web 服务器 — 党务智能助手 Web 界面后端

启动:
  uv run python -m partymate.web.server

访问:
  http://localhost:8567
"""

from __future__ import annotations

import sys
from pathlib import Path

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
    MaterialCheckService,
    MaterialImportService,
    MemberViewService,
    OCRReviewService,
)
from partymate.tools.content_gen import format_content_plan, generate_meeting_content
from partymate.tools.doc_check import check_document, detect_doc_type
from partymate.tools.file_parser import SUPPORTED_EXTS, parse_file, preview_from_bytes
from partymate.tools.meeting_summary import format_meeting_summary, parse_meeting_notes
from partymate.tools.rag import format_citations, search_with_fallback

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


def create_app(
    repository: Repository | None = None,
    data_root: Path | None = None,
) -> Starlette:
    repo = repository or Repository()
    base_data_root = data_root or (HERE / "data")
    member_views = MemberViewService(repo)
    import_service = MaterialImportService(repo=repo, data_root=base_data_root)
    check_service = MaterialCheckService(repo)
    ocr_reviews = OCRReviewService(repo=repo, data_root=base_data_root)

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
        rag_results = search_with_fallback(raw_text)
        citations = format_citations(rag_results)

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
        rag_results = search_with_fallback(topic)
        citations = format_citations(rag_results)
        pptx_path = export_content_pptx(raw_json) if body.get("export_pptx") else None
        return JSONResponse(
            {
                "result": result,
                "citations": citations,
                "pptx_path": str(pptx_path) if pptx_path else None,
            }
        )

    async def api_chat(request):
        body = await request.json()
        message = body.get("message", "")
        if not message:
            return JSONResponse({"error": "请输入消息"}, status_code=400)

        try:
            from partymate.agent import run_agent

            result = await run_agent(message)
            return JSONResponse({"result": result})
        except Exception as e:  # pragma: no cover - external model/runtime
            err = str(e).lower()
            if "connection" in err or "refused" in err or "connect" in err:
                return JSONResponse(
                    {
                        "result": (
                            "⚠️ 无法连接到本地 AI 模型。请确保 Ollama 已启动。\n\n"
                            "也可使用左侧的独立工具模式。"
                        )
                    }
                )
            return JSONResponse({"result": f"❌ 出错: {e}"})

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

        return JSONResponse(
            {
                "status": "ok",
                "ollama": ollama_ok,
                "ocr": ocr_ok,
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

    routes = [
        Route("/api/check-doc", api_check_doc, methods=["POST"]),
        Route("/api/upload", api_upload, methods=["POST"]),
        Route("/api/meeting", api_meeting, methods=["POST"]),
        Route("/api/content", api_content, methods=["POST"]),
        Route("/api/chat", api_chat, methods=["POST"]),
        Route("/api/status", api_status),
        Route("/api/download", api_download),
        Route("/api/members", api_members),
        Route("/api/members", api_add_member, methods=["POST"]),
        Route("/api/members/{member_id}", api_get_member),
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
        Route("/api/members/import", api_import_members, methods=["POST"]),
        Mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static"),
    ]

    return Starlette(debug=False, routes=routes)


app = create_app()


if __name__ == "__main__":  # pragma: no cover - manual run path
    import uvicorn

    _emit_startup_banner()
    uvicorn.run(app, host="0.0.0.0", port=8567, log_level="info")
