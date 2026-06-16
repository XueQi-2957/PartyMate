"""
PartyMate 混合检索 RAG 引擎
============================
基于 Ollama bge-m3（稠密向量）+ BM25（稀疏关键词）+ LLM Rerank 的三阶段混合检索。

特性:
  - Ollama bge-m3 做向量嵌入（GPU 加速，支持中文/多语言 8192 tokens）
  - rank-bm25 做稀疏检索，弥补纯语义检索的关键词精度
  - LLM Rerank 对初检结果做二次精排
  - LLM 驱动的语义分块（大文档自动拆分重叠窗口分批处理）
  - 知识库自动构建（DOCX → 清洗 → 分块 → 索引）
  - 针对《贵州省发展党员工作规程（试行）》25步流程做了专项检索优化
  - 纯开源免费方案（Ollama + ChromaDB + BM25），无需 GPU 训练，无需 API Key

用法:
    from partymate.tools.rag import VectorRAG
    rag = VectorRAG()
    results = rag.search("入党申请书需要什么条件")
    print(rag.format_citations(results))
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import chromadb
import httpx
from rank_bm25 import BM25Okapi

# ── 路径 ──────────────────────────────────────────────

HERE = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = HERE / "knowledge"
CHROMA_DIR = KNOWLEDGE_DIR / "chroma_db"
CHUNK_INDEX_FILE = KNOWLEDGE_DIR / "chunks_index.json"

# ── LLM 配置（复用 agent.py 的配置） ──────────────────

API_BASE = os.getenv("PARTYMATE_API_BASE") or os.getenv("OPENAI_BASE_URL") or "http://127.0.0.1:11434/v1"
API_KEY = os.getenv("PARTYMATE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
MODEL = os.getenv("PARTYMATE_MODEL") or os.getenv("HERMES_MODEL") or "qwen3.5:4b"

# ── 检索参数 ──────────────────────────────────────────

DEFAULT_TOP_K = 5
HYBRID_ALPHA = 0.6      # 稠密检索权重 (0.6) vs 稀疏检索权重 (0.4)
HYBRID_TOP_K = 15       # 混合检索初选候选数（rerank 前）
DEFAULT_RERANK = True   # 默认启用重排
RERANK_MODE = "cross-encoder"  # "cross-encoder" | "llm" | "none"
RERANK_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
CHUNK_MIN_CHARS = 150   # chunk 最少字数
CHUNK_MAX_CHARS = 1500  # chunk 最大字数
REINDEX_THRESHOLD = 0.3  # 知识库变化超过 30% 时自动重建

# ── 嵌入模型（Ollama bge-m3，GPU 加速） ─────────────

EMBED_MODEL = "bge-m3"
OLLAMA_BASE = os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434"


def _ollama_embed(texts: list[str]) -> list[list[float]]:
    """通过 Ollama API 获取 bge-m3 向量嵌入（GPU 加速）

    Args:
        texts: 文本列表（批量最多 50 条）

    Returns:
        向量列表，每项为 1024 维 embedding
    """
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{OLLAMA_BASE}/api/embed",
                json={"model": EMBED_MODEL, "input": texts},
            )
        if resp.status_code == 200:
            return resp.json()["embeddings"]
        return []
    except Exception:
        return []


class _OllamaEmbeddingFunction:
    """ChromaDB 兼容的嵌入函数 — 通过 Ollama bge-m3 生成向量"""

    def __init__(self) -> None:
        pass

    def __call__(self, input: list[str]) -> list[list[float]]:
        return _ollama_embed(input)

    def name(self) -> str:
        return f"ollama_{EMBED_MODEL}"


# ══════════════════════════════════════════════════════
#  1. 文档清洗
# ══════════════════════════════════════════════════════

def _clean_text(text: str) -> str:
    """清洗文本：去多余空格/空行/控制字符"""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [l.strip() for l in text.split("\n")]
    return "\n".join(lines)


def extract_docx_text(docx_path: str | Path) -> str:
    """从 DOCX 提取并清洗文本"""
    from docx import Document

    doc = Document(str(docx_path))
    parts: list[str] = []
    table_count = 0

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = para.style.name if para.style else ""
        is_heading = "heading" in style_name.lower() if style_name else False

        has_chapter = bool(re.match(r"^第[一二三四五六七八九十\d]+[章节条]", text))
        is_stage = bool(re.match(r"^第[一二三四五六七八九十\d]+阶段", text))
        is_article = bool(re.match(r"^第[一二三四五六七八九十\d]+条", text))
        is_section = bool(re.match(r"^[一二三四五六七八九十\d]+[、．.]", text)) and len(text) < 50

        if is_heading or has_chapter or is_stage:
            parts.append(f"\n## {text}\n")
        elif is_article:
            parts.append(f"\n### {text}\n")
        elif is_section and len(text) < 50:
            parts.append(f"\n### {text}\n")
        else:
            parts.append(text)

    # 表格
    for table in doc.tables:
        table_count += 1
        parts.append(f"\n--- 表格{table_count} ---")
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            parts.append(" | ".join(cells))

    raw = "\n".join(parts)
    return _clean_text(raw)


# ══════════════════════════════════════════════════════
#  2. LLM 语义分块
# ══════════════════════════════════════════════════════

def _call_llm(system: str, prompt: str, max_tokens: int = 4096) -> str:
    """调用配置的 LLM API（OpenAI-compatible）"""
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{API_BASE}/chat/completions",
                headers=headers,
                json=body,
            )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        return ""
    except Exception:
        return ""


_CHUNKING_SYSTEM_PROMPT = """你是高校党务文档处理专家。你的任务是将一段党务工作手册文本按**语义边界**分割成独立的、语义完整的知识块。

## 文档类型
这是《贵州师范大学组织发展工作专项培训工作手册》，包含以下内容：
1. **中国共产党支部工作条例（试行）** — 党支部设置、基本任务、工作机制、组织生活、委员会建设
2. **中国共产党党员教育管理工作条例** — 党员教育基本任务、日常管理、党籍管理、监督处置
3. **中国共产党普通高等学校基层组织工作条例** — 高校党委/院系党组织设置与职责
4. **党费管理** — 党费缴纳、使用、管理
5. **中国共产党发展党员工作细则** — 发展党员各环节要求
6. **贵州省发展党员工作规程（试行）** — 25步具体流程（最关键部分）
7. **贵州师范大学发展党员工作规范** — 公示制度、入党志愿书管理、预审登记
8. **工作模板/表格** — 会议记录模板、考察登记表、预审表等

## 分块规则
1. 每个知识块必须是**完整的语义单元**（一个完整的条款、步骤、定义或模板说明）。
2. **必须尊重文档结构边界**：不同法规/文件的内容分开；不同章节分开；法规正文与附件模板分开。
3. 以 `[CHUNK]` 标记每个块的开始，后面跟块标题（`## 标题`），然后换行写内容。
4. **不要在句子中间切分**——在句号、段落结束处切分。
5. 每个块长度控制在 **150~1500 字**之间。
6. 标题格式建议：
   - 法规类：`支部工作条例·第一章 总则`
   - 流程类：`发展党员规程·第1步 递交申请书`
   - 制度类：`贵州师范大学·公示制度`
   - 模板类：`工作模板·支委会会议记录`

输出格式示例：
[CHUNK]
## 发展党员规程·第1步 递交入党申请书
年满十八岁的中国工人、农民、军人、知识分子和其他社会阶层的先进分子，承认党的纲领和章程，愿意参加党的一个组织并在其中积极工作、执行党的决议和按期交纳党费的，可以申请加入中国共产党。入党申请人应当向工作、学习所在单位党组织提出入党申请……

[CHUNK]
## 发展党员规程·第7步 确定发展对象
对经过一年以上培养教育和考察、基本具备党员条件的入党积极分子，在听取党小组、培养联系人、党员和群众意见的基础上，支部委员会讨论同意并报上级党委备案后，可列为发展对象。
"""


def _llm_chunk(text: str) -> list[dict]:
    """使用 LLM 进行语义分块

    Returns:
        [{"title": "...", "content": "..."}, ...]
    """
    # 如果 LLM 不可用（本地无模型），回退到基于规则的分块
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{API_BASE}/models")
            if resp.status_code != 200:
                return _rule_chunk(text)
    except Exception:
        return _rule_chunk(text)

    # 将长文本分批送入 LLM（每批约 4000 字的重叠窗口）
    all_chunks: list[dict] = []
    batch_size = 4000
    overlap = 500

    idx = 0
    while idx < len(text):
        batch = text[idx : idx + batch_size]
        if len(batch) < 200:
            # 最后一个小片段，追加到上一个块
            if all_chunks:
                all_chunks[-1]["content"] += "\n" + batch
            break

        result = _call_llm(_CHUNKING_SYSTEM_PROMPT, batch, max_tokens=2048)
        if not result:
            # LLM 失败，回退规则分块
            all_chunks = _rule_chunk(text)
            break

        # 解析 [CHUNK] 标记
        batch_chunks: list[dict] = []
        for block in re.split(r"\[CHUNK\]\s*", result):
            block = block.strip()
            if not block:
                continue
            # 提取标题
            title_match = re.match(r"^##\s+(.+?)(?:\n|$)", block)
            title = title_match.group(1).strip() if title_match else f"党务规程·第{len(all_chunks)+len(batch_chunks)+1}段"
            content = block
            if title_match:
                content = block[title_match.end():].strip()
            if len(content) >= CHUNK_MIN_CHARS:
                batch_chunks.append({"title": title, "content": content})

        # 去重：如果上一批的最后一个块和当前批的第一个块内容相似，合并
        if all_chunks and batch_chunks:
            last_title = all_chunks[-1]["title"]
            first_title = batch_chunks[0]["title"]
            if last_title == first_title:
                all_chunks[-1]["content"] += "\n" + batch_chunks[0]["content"]
                batch_chunks = batch_chunks[1:]

        all_chunks.extend(batch_chunks)
        idx += batch_size - overlap

    # 如果没有解析出任何块，回退规则分块
    if not all_chunks:
        all_chunks = _rule_chunk(text)

    return all_chunks


def _rule_chunk(text: str) -> list[dict]:
    """基于规则的标题分块（LLM 不可用时的回退方案）"""
    lines = text.split("\n")
    chunks: list[dict] = []
    current_title = "文档开头"
    current_content: list[str] = []

    def flush():
        if current_content:
            body = "\n".join(current_content).strip()
            if len(body) >= CHUNK_MIN_CHARS:
                chunks.append({"title": current_title, "content": body})
            elif chunks and len(body) > 30:
                chunks[-1]["content"] += "\n" + body

    for line in lines:
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            flush()
            current_title = heading_match.group(1).strip()
            current_content = []
        else:
            current_content.append(line)
    flush()

    # 对过大的 chunk 做二次分割（按双换行）
    final_chunks: list[dict] = []
    for c in chunks:
        if len(c["content"]) > CHUNK_MAX_CHARS:
            sub_parts = re.split(r"\n\n+", c["content"])
            buffer = ""
            for part in sub_parts:
                if len(buffer) + len(part) > CHUNK_MAX_CHARS and buffer:
                    final_chunks.append({"title": c["title"], "content": buffer.strip()})
                    buffer = part
                else:
                    buffer += "\n\n" + part if buffer else part
            if buffer.strip():
                final_chunks.append({"title": c["title"], "content": buffer.strip()})
        else:
            final_chunks.append(c)

    return final_chunks


# ══════════════════════════════════════════════════════
#  3. LLM Re-ranker
# ══════════════════════════════════════════════════════

_RERANK_SYSTEM_PROMPT = """你是党务知识检索的精确排序专家。你的任务是评估给定文档段落对用户查询的相关性。

要求：
1. 对每个段落，仅基于**内容相关性**给出 0-10 分：
   - 0-2: 完全不相关
   - 3-4: 弱相关（提到相关术语但不是用户要的信息）
   - 5-6: 中等相关（部分回答了问题但有偏差）
   - 7-8: 强相关（直接回答用户问题）
   - 9-10: 完全匹配（精确回答了用户查询的核心需求）
2. 考虑党务工作的专业性：术语匹配、流程对应关系、政策法规的准确性。
3. 输出格式严格为每行一个：`段落ID: 分数`
4. 只输出评分结果，不要额外说明。"""


def _llm_rerank(chunks: list[dict], query: str, top_k: int = 5) -> list[dict]:
    """使用 LLM 对检索结果进行二次精排

    Args:
        chunks: 候选列表，每项含 title, content, score 等
        query: 用户查询
        top_k: 返回 top-k 条

    Returns:
        重排序后的列表，每项新增 rerank_score 字段
    """
    if not chunks:
        return []

    # 构建评分输入：截断过长的 content
    candidates_text = ""
    for i, c in enumerate(chunks):
        content_preview = c["content"][:200].strip()
        if len(c["content"]) > 200:
            content_preview += "…"
        candidates_text += f"[{i}] 标题: {c['title']}\n    内容: {content_preview}\n\n"

    prompt = f"""用户查询：{query}

候选段落：
{candidates_text}

请为每个段落评分（0-10），每行一个：段落ID: 分数"""

    result = _call_llm(_RERANK_SYSTEM_PROMPT, prompt, max_tokens=1024)
    if not result:
        # LLM 失败，保持原顺序
        for c in chunks:
            c["rerank_score"] = c.get("score", 0.0)
        return chunks[:top_k]

    # 解析评分
    score_map: dict[int, float] = {}
    for line in result.strip().split("\n"):
        line = line.strip()
        m = re.match(r"^\[?(\d+)\]?\s*[:：]\s*(\d+(?:\.\d+)?)", line)
        if m:
            idx = int(m.group(1))
            score = float(m.group(2))
            if 0 <= idx < len(chunks):
                score_map[idx] = score

    # 应用评分
    for i, c in enumerate(chunks):
        c["rerank_score"] = score_map.get(i, c.get("score", 0.0))

    # 按 rerank_score 降序排列
    ranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)

    # 更新 score 为 rerank_score
    for c in ranked:
        c["score"] = round(c["rerank_score"], 4)
        c["source"] = "hybrid+rerank"

    return ranked[:top_k]


# ══════════════════════════════════════════════════════
#  3B. Cross-Encoder 精排
# ══════════════════════════════════════════════════════

_CE_MODEL = None


def _get_ce_model():
    """延迟加载 CrossEncoder 模型（BAAI/bge-reranker-v2-m3）"""
    global _CE_MODEL
    if _CE_MODEL is None:
        from sentence_transformers import CrossEncoder
        print(f"[RAG] 加载 CrossEncoder 模型: {RERANK_MODEL_NAME} ...", file=sys.stderr)
        _CE_MODEL = CrossEncoder(RERANK_MODEL_NAME, device="cuda", max_length=512)
        print("[RAG] CrossEncoder 加载完成", file=sys.stderr)
    return _CE_MODEL


def _ce_rerank(chunks: list[dict], query: str, top_k: int = 5) -> list[dict]:
    """使用 Cross-Encoder 模型进行二次精排

    bge-reranker-v2-m3 直接将 (query, passage) 对输入，输出相关性分数。
    比 LLM 精排快 10-50 倍，比分词匹配更精准。

    Args:
        chunks: 候选列表
        query: 用户查询
        top_k: 返回 top-k 条

    Returns:
        重排序后的列表
    """
    if not chunks:
        return []

    try:
        model = _get_ce_model()
        # 构建 (query, passage) 对（截断 content 到 500 字以加速）
        pairs = [(query, f"{c['title']}\n{c['content'][:500]}") for c in chunks]
        # 批量评分（自动 batch）
        scores = model.predict(pairs)

        for i, c in enumerate(chunks):
            score = float(scores[i])
            c["rerank_score"] = score
            c["score"] = round(score, 4)
            c["source"] = "hybrid+rerank(ce)"

        ranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
        return ranked[:top_k]
    except Exception as e:
        # Cross-Encoder 失败，回退到 LLM 精排
        print(f"[WARN] Cross-Encoder 精排失败 ({e})，回退到 LLM 精排", file=sys.stderr)
        return _llm_rerank(chunks, query, top_k=top_k)


# ══════════════════════════════════════════════════════
#  4. 知识库构建（DOCX → 分块 → 索引）
# ══════════════════════════════════════════════════════

def _tokenize(text: str) -> list[str]:
    """中文分词 + 英文小写 + 标点清理"""
    text = re.sub(r"[^\u4e00-\u9fff\w]", " ", text)
    tokens = text.lower().split()
    return [t for t in tokens if len(t) > 1]


def build_knowledge_base(docx_path: str | Path | None = None) -> dict:
    """构建知识库：DOCX → 清洗 → 语义分块 → ChromaDB + BM25 索引

    Args:
        docx_path: DOCX 文件路径。None 则使用默认路径。

    Returns:
        {"status": "ok"|"skipped"|"error", "chunks": N, "message": "..."}
    """
    if docx_path is None:
        docx_path = HERE.parent / "知识库" / "（7.21）贵州师范大学组织发展工作专项培训工作手册.docx"
    docx_path = Path(docx_path)

    if not docx_path.exists():
        return {"status": "error", "chunks": 0, "message": f"DOCX 文件不存在: {docx_path}"}

    # 检查是否需要重建
    if CHROMA_DIR.exists():
        try:
            client = chromadb.PersistentClient(str(CHROMA_DIR))
            collection = client.get_collection("party_rules")
            count = collection.count()
            if count > 0:
                return {"status": "skipped", "chunks": count, "message": "知识库已存在，无需重建"}
        except Exception:
            pass

    # 1. 提取并清洗
    print("[RAG] 提取 DOCX 文本...", file=sys.stderr)
    raw_text = extract_docx_text(docx_path)
    if not raw_text.strip():
        return {"status": "error", "chunks": 0, "message": "DOCX 提取为空"}
    print(f"[RAG] 提取完成：{len(raw_text)} 字符", file=sys.stderr)

    # 2. 语义分块
    print("[RAG] 开始 LLM 语义分块（大文档自动分批处理）...", file=sys.stderr)
    chunks = _llm_chunk(raw_text)
    print(f"[RAG] 分块完成：{len(chunks)} 个语义块", file=sys.stderr)

    # 3. 构建 ChromaDB 索引（使用 Ollama bge-m3 嵌入，GPU 加速）
    print("[RAG] 构建 ChromaDB 向量索引（Ollama bge-m3 > GPU）...", file=sys.stderr)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(str(CHROMA_DIR))
    # 删除旧 collection 重新创建
    try:
        client.delete_collection("party_rules")
    except Exception:
        pass
    collection = client.create_collection("party_rules")

    documents = [c["content"] for c in chunks]
    metadatas = [{"title": c["title"], "idx": str(i)} for i, c in enumerate(chunks)]
    ids = [str(uuid.uuid4())[:12] for _ in chunks]

    # 批量添加（每次 10 条，Ollama 嵌入）
    batch_size = 10
    for i in range(0, len(documents), batch_size):
        end = min(i + batch_size, len(documents))
        batch_docs = documents[i:end]
        batch_metadatas = metadatas[i:end]
        batch_ids = ids[i:end]

        # 用 Ollama bge-m3 预计算嵌入向量
        embeddings = _ollama_embed(batch_docs)
        if not embeddings:
            # Ollama 不可用时，回退到 ChromaDB 默认 ONNX
            print(f"  [WARN] Ollama 嵌入失败，批次 {i//batch_size + 1} 使用默认 ONNX 回退", file=sys.stderr)
            collection.add(
                documents=batch_docs,
                metadatas=batch_metadatas,
                ids=batch_ids,
            )
        else:
            collection.add(
                documents=batch_docs,
                embeddings=embeddings,
                metadatas=batch_metadatas,
                ids=batch_ids,
            )

        progress = min(100, int((end / len(documents)) * 100))
        print(f"  [RAG] 向量化进度: {progress}% ({end}/{len(documents)})", file=sys.stderr)

    # 4. 构建 BM25 索引
    print("[RAG] 构建 BM25 关键词索引...", file=sys.stderr)
    bm25_data = {
        "documents": documents,
        "metadatas": metadatas,
        "ids": ids,
    }
    CHUNK_INDEX_FILE.write_text(
        json.dumps(bm25_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[RAG] 构建完成：{len(chunks)} 个语义块", file=sys.stderr)
    return {
        "status": "ok",
        "chunks": len(chunks),
        "message": f"知识库构建完成，共 {len(chunks)} 个语义块",
    }


# ══════════════════════════════════════════════════════
#  5. VectorRAG — 混合检索引擎
# ══════════════════════════════════════════════════════

class VectorRAG:
    """混合检索引擎：ChromaDB（稠密）+ BM25（稀疏）+ LLM Rerank（精排）"""

    def __init__(self) -> None:
        self._chroma_collection = None
        self._bm25: BM25Okapi | None = None
        self._bm25_docs: list[dict] = []
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """延迟初始化：加载 ChromaDB 和 BM25"""
        if self._initialized:
            return True

        if not CHROMA_DIR.exists():
            return False

        try:
            client = chromadb.PersistentClient(str(CHROMA_DIR))
            self._chroma_collection = client.get_collection("party_rules")

            if CHUNK_INDEX_FILE.exists():
                data = json.loads(CHUNK_INDEX_FILE.read_text(encoding="utf-8"))
                tokenized = [_tokenize(d) for d in data["documents"]]
                self._bm25 = BM25Okapi(tokenized)
                self._bm25_docs = [
                    {"content": d, "metadata": m, "id": i}
                    for d, m, i in zip(
                        data["documents"], data["metadatas"], data["ids"]
                    )
                ]

            self._initialized = True
            return True
        except Exception:
            return False

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        alpha: float = HYBRID_ALPHA,
        rerank: bool = DEFAULT_RERANK,
    ) -> list[dict]:
        """三阶段混合检索：稠密 → 稀疏 → 融合 → 精排

        Args:
            query: 查询文本
            top_k: 返回结果数
            alpha: 稠密检索权重 [0,1]，1=纯向量，0=纯BM25
            rerank: 是否启用 LLM 重排

        Returns:
            [{"title": "...", "content": "...", "score": 0.85,
              "source": "hybrid|hybrid+rerank"}, ...]
        """
        if not self._ensure_initialized():
            return []

        candidate_k = HYBRID_TOP_K if rerank else top_k

        # ── 稠密检索（Ollama bge-m3 预计算查询向量） ──
        dense_results: dict[str, dict] = {}
        try:
            query_embedding = _ollama_embed([query])
            if not query_embedding:
                # Ollama 不可用时，回退到文本查询（使用默认 ONNX）
                resp = self._chroma_collection.query(
                    query_texts=[query],
                    n_results=candidate_k + 5,
                    include=["documents", "metadatas", "distances"],
                )
            else:
                resp = self._chroma_collection.query(
                    query_embeddings=query_embedding,
                    n_results=candidate_k + 5,
                    include=["documents", "metadatas", "distances"],
                )
            if resp["ids"] and resp["ids"][0]:
                for i, doc_id in enumerate(resp["ids"][0]):
                    dist = resp["distances"][0][i] if resp.get("distances") else 1.0
                    sim = max(0.0, 1.0 - dist / 2.0)
                    dense_results[doc_id] = {
                        "id": doc_id,
                        "title": resp["metadatas"][0][i].get("title", "未知"),
                        "content": resp["documents"][0][i],
                        "dense_score": round(sim, 4),
                    }
        except Exception:
            pass

        # ── 稀疏检索（BM25） ──
        sparse_results: dict[str, dict] = {}
        if self._bm25 and self._bm25_docs:
            tokenized_query = _tokenize(query)
            if tokenized_query:
                scores = self._bm25.get_scores(tokenized_query)
                max_score = max(scores) if max(scores) > 0 else 1.0
                for i, score in enumerate(scores):
                    if score > 0:
                        doc = self._bm25_docs[i]
                        doc_id = doc["id"]
                        sparse_results[doc_id] = {
                            "id": doc_id,
                            "title": doc["metadata"]["title"],
                            "content": doc["content"],
                            "sparse_score": round(score / max_score, 4),
                        }

        # ── 融合 ──
        all_ids = set(dense_results.keys()) | set(sparse_results.keys())
        fused: list[dict] = []
        for doc_id in all_ids:
            d = dense_results.get(doc_id, {})
            s = sparse_results.get(doc_id, {})
            dense_score = d.get("dense_score", 0.0)
            sparse_score = s.get("sparse_score", 0.0)
            hybrid_score = alpha * dense_score + (1 - alpha) * sparse_score

            fused.append({
                "id": doc_id,
                "title": d.get("title") or s.get("title", "未知"),
                "content": d.get("content") or s.get("content", ""),
                "score": round(hybrid_score, 4),
                "dense_score": dense_score,
                "sparse_score": sparse_score,
                "source": "hybrid",
            })

        fused.sort(key=lambda x: x["score"], reverse=True)

        # ── 重排（Cross-Encoder / LLM / 跳过） ──
        if rerank and fused:
            mode = RERANK_MODE
            candidates = fused[:HYBRID_TOP_K]
            if mode == "cross-encoder":
                return _ce_rerank(candidates, query, top_k=top_k)
            elif mode == "llm":
                return _llm_rerank(candidates, query, top_k=top_k)
            # mode == "none": fall through to return fused

        return fused[:top_k]

    def get_relevant_procedure(self, step_name: str, top_k: int = 2) -> list[dict]:
        """专项检索：从《贵州省发展党员工作规程（试行）》中检索指定步骤

        Args:
            step_name: 步骤名称（如 "递交入党申请书"、"确定发展对象"、"政治审查"）
            top_k: 返回结果数

        Returns:
            匹配的规程段落列表
        """
        # 构建专有查询，在标题中精确匹配
        query = f"贵州省发展党员工作规程 {step_name}"
        results = self.search(query, top_k=top_k, rerank=True)

        # 如果结果不够，放宽匹配
        if len(results) < top_k:
            broader = self.search(step_name, top_k=top_k * 2, rerank=True)
            seen_ids = {r["id"] for r in results}
            for r in broader:
                if r["id"] not in seen_ids and step_name in r["title"]:
                    results.append(r)
                    seen_ids.add(r["id"])

        return results[:top_k]

    def format_citations(
        self,
        results: list[dict],
        min_score: float = 0.15,
    ) -> str:
        """将检索结果格式化为可读引用文本"""
        valid = [r for r in results if r["score"] >= min_score]
        if not valid:
            return ""

        lines = ["📖 知识库引用："]
        for i, r in enumerate(valid, 1):
            lines.append(f"\n{i}. **{r['title']}** (相关度: {r['score']:.0%})")
            content = r["content"][:150].strip()
            if len(r["content"]) > 150:
                content += "……"
            lines.append(f"   > {content}")
        lines.append(f"\n--- 共检索 {len(valid)} 条相关规程 ---")
        return "\n".join(lines)

    def enhanced_system_context(self, query: str, top_k: int = 3) -> str:
        """根据查询，生成增强的系统上下文（用于注入 agent prompt）

        输出结构化的知识参考信息 JSON，包含 id 方便前端渲染气泡。
        """
        results = self.search(query, top_k=top_k, rerank=True)
        if not results:
            return json.dumps({"knowledge": []}, ensure_ascii=False)
            
        valid = [r for r in results if r["score"] >= 0.15]
        if not valid:
            return json.dumps({"knowledge": []}, ensure_ascii=False)

        knowledge_list = []
        for i, r in enumerate(valid, 1):
            knowledge_list.append({
                "id": str(i),
                "title": r["title"],
                "content": r["content"][:300].strip() + ("..." if len(r["content"]) > 300 else "")
            })

        return json.dumps({"knowledge": knowledge_list}, ensure_ascii=False)


# ══════════════════════════════════════════════════════
#  6. 插件：知识库管理 CLI
# ══════════════════════════════════════════════════════

def rebuild_command() -> None:
    """CLI 入口：重建知识库"""
    # 清理旧索引
    if CHROMA_DIR.exists():
        import shutil
        shutil.rmtree(CHROMA_DIR)
    if CHUNK_INDEX_FILE.exists():
        CHUNK_INDEX_FILE.unlink()

    result = build_knowledge_base()
    print(f"[RAG] {result['message']}", file=sys.stderr)


def status_command() -> dict:
    """返回知识库状态"""
    rag = VectorRAG()
    if not rag._ensure_initialized():
        return {"ready": False, "chunks": 0, "message": "知识库未构建，请先运行 uv run python -m partymate.tools.rag --rebuild"}
    try:
        chunk_count = rag._chroma_collection.count()
        return {"ready": True, "chunks": chunk_count, "message": f"知识库就绪，{chunk_count} 个语义块"}
    except Exception as e:
        return {"ready": False, "chunks": 0, "message": str(e)}


# ══════════════════════════════════════════════════════
#  7. 兼容旧接口（保持向后兼容）
# ══════════════════════════════════════════════════════

_rag_instance: VectorRAG | None = None


def _get_rag() -> VectorRAG:
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = VectorRAG()
    return _rag_instance


def search(query: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """兼容旧接口：搜索知识库"""
    return _get_rag().search(query, top_k=top_k)


def format_citations(results: list[dict], min_score: float = 0.15) -> str:
    """兼容旧接口：格式化引用"""
    return _get_rag().format_citations(results, min_score=min_score)


def search_with_fallback(query: str, top_k: int = 3) -> list[dict]:
    """兼容旧接口：搜索 + 保底"""
    return _get_rag().search(query, top_k=top_k)


def get_rag_status() -> dict:
    """获取 RAG 状态"""
    return status_command()


# ══════════════════════════════════════════════════════
#  8. CLI 入口
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--rebuild":
        rebuild_command()
    elif len(sys.argv) > 2 and sys.argv[1] == "--search":
        query = sys.argv[2]
        rag = _get_rag()
        results = rag.search(query)
        print(rag.format_citations(results), file=sys.stderr)
    elif len(sys.argv) > 2 and sys.argv[1] == "--procedure":
        step = sys.argv[2]
        rag = _get_rag()
        results = rag.get_relevant_procedure(step)
        print(rag.format_citations(results), file=sys.stderr)
    else:
        print("用法:\n  uv run python -m partymate.tools.rag --rebuild        # 重建知识库\n  uv run python -m partymate.tools.rag --search <query>  # 搜索知识库\n  uv run python -m partymate.tools.rag --procedure <step> # 检索规程步骤")
