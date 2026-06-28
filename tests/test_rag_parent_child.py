from __future__ import annotations

import json
from pathlib import Path

import pytest

from partymate.tools import rag


def test_txt_loader_and_parent_child_rule_split(tmp_path: Path) -> None:
    source = tmp_path / "中国共产党发展党员工作细则.txt"
    source.write_text(
        "\n".join(
            [
                "中国共产党发展党员工作细则",
                "第一章 总则",
                "第一条 发展党员工作应当贯彻党的基本理论、基本路线、基本方略。",
                "第二条 党组织应当把政治标准放在首位，严格程序、严肃纪律。",
            ]
        ),
        encoding="utf-8",
    )

    elements = rag._load_txt_elements(source)
    parents = rag._elements_to_parents(elements)
    children = []
    for parent in parents:
        children.extend(rag._children_from_parent(parent, use_llm=False))

    assert parents
    assert children
    assert all(child.parent_id for child in children)
    assert children[0].doc_name == source.stem
    assert "第一条" in children[0].content


def test_quality_first_uses_cross_encoder_by_default() -> None:
    assert rag.RERANK_MODE == "cross-encoder"


def test_docx_tables_become_table_children(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")

    source = tmp_path / "入党积极分子备案表.docx"
    doc = docx.Document()
    doc.add_paragraph("入党积极分子备案表")
    table = doc.add_table(rows=2, cols=3)
    table.rows[0].cells[0].text = "姓名"
    table.rows[0].cells[1].text = "性别"
    table.rows[0].cells[2].text = "确定时间"
    table.rows[1].cells[0].text = "张三"
    table.rows[1].cells[1].text = "男"
    table.rows[1].cells[2].text = "2025年3月"
    doc.save(source)

    elements = rag._load_docx_elements(source)
    parents = rag._elements_to_parents(elements)
    children = []
    for parent in parents:
        children.extend(rag._children_from_parent(parent, use_llm=False))

    table_children = [child for child in children if child.chunk_type == "table"]
    assert table_children
    assert "姓名: 张三" in table_children[0].content
    assert table_children[0].metadata["row_range"] == "1-1"


def test_enhanced_context_includes_evidence_context_and_citation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = rag.ParentChunk(
        parent_id="parent-1",
        doc_name="发展党员工作细则",
        source_path="rules.txt",
        title="发展党员工作细则 > 第一章 总则",
        heading_path="发展党员工作细则 > 第一章 总则",
        content="第一条 发展党员工作应当贯彻党的基本理论。第二条 党组织应当把政治标准放在首位。",
        chunk_type="text",
    )
    child_meta = {
        "title": "发展党员工作细则 > 第一条",
        "idx": "0",
        "parent_id": "parent-1",
        "doc_name": "发展党员工作细则",
        "heading_path": "发展党员工作细则 > 第一章 总则",
        "article_no": "第一条",
        "chunk_type": "text",
        "citation": "发展党员工作细则 > 第一章 总则 > 第一条",
    }

    class FakeCollection:
        def query(self, **kwargs):
            return {
                "ids": [["child-1"]],
                "documents": [["第一条 发展党员工作应当贯彻党的基本理论。"]],
                "metadatas": [[child_meta]],
                "distances": [[0.1]],
            }

    monkeypatch.setattr(rag, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(rag, "CHUNK_INDEX_FILE", tmp_path / "chunks_index.json")
    monkeypatch.setattr(rag, "PARENT_INDEX_FILE", tmp_path / "parents_index.json")
    monkeypatch.setattr(rag, "_ollama_embed", lambda texts: [[0.1, 0.2, 0.3] for _ in texts])
    monkeypatch.setattr(rag, "_ce_rerank", lambda chunks, query, top_k=5: chunks[:top_k])

    rag.CHROMA_DIR.mkdir()
    rag.CHUNK_INDEX_FILE.write_text(
        json.dumps(
            {
                "documents": ["第一条 发展党员工作应当贯彻党的基本理论。"],
                "metadatas": [child_meta],
                "ids": ["child-1"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rag.PARENT_INDEX_FILE.write_text(
        json.dumps({"parents": [parent.to_dict()]}, ensure_ascii=False),
        encoding="utf-8",
    )

    instance = rag.VectorRAG()
    instance._chroma_collection = FakeCollection()
    instance._initialized = True
    instance._load_bm25()
    instance._load_parents()

    payload = json.loads(instance.enhanced_system_context("发展党员", top_k=1))

    assert payload["knowledge"]
    item = payload["knowledge"][0]
    assert item["evidence"] == "第一条 发展党员工作应当贯彻党的基本理论。"
    assert "第二条" in item["context"]
    assert item["citation"] == "发展党员工作细则 > 第一章 总则 > 第一条"
