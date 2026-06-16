from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP
from partymate.tools.rag import VectorRAG, get_rag_status, rebuild_command, search_with_fallback, format_citations

# Create FastMCP server
mcp = FastMCP("PartyMate-RAG", dependencies=["fastmcp", "partymate"])

# Global RAG instance (lazily initialized by tools)
_rag_instance: VectorRAG | None = None

def _get_rag() -> VectorRAG:
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = VectorRAG()
    return _rag_instance


@mcp.tool()
def search_party_rules(query: str) -> str:
    """在党务知识库中检索规程、文件、常见问题等。当你对党务规定不确定时调用。"""
    rag = _get_rag()
    return rag.enhanced_system_context(query)


@mcp.tool()
def rag_search_with_fallback(query: str) -> str:
    """供非 Agent 的外部 API 调用，搜索知识库并返回格式化后的引用字符串。"""
    # Use the existing wrapper functions from rag.py to maintain exact behavior
    results = search_with_fallback(query)
    return format_citations(results)


@mcp.tool()
def rag_status() -> str:
    """获取 RAG 知识库状态，返回 JSON 字符串。"""
    status = get_rag_status()
    return json.dumps(status, ensure_ascii=False)


@mcp.tool()
def rag_rebuild() -> str:
    """重建 RAG 知识库，返回状态 JSON 字符串。"""
    try:
        rebuild_command()
        status = get_rag_status()
        return json.dumps(status, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ready": False, "chunks": 0, "message": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
