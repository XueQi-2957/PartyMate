#!/usr/bin/env python3
"""Apply 4 targeted edits to partymate/tools/rag.py"""

import re

with open('partymate/tools/rag.py', 'r', encoding='utf-8') as f:
    content = f.read()

# =====================================================
# EDIT 1: Replace _CHUNKING_SYSTEM_PROMPT
# =====================================================
old_prompt = '''_CHUNKING_SYSTEM_PROMPT = """你是一名党务文档处理专家。你的任务是将一段党务工作手册文本按照语义边界分割成独立的、语义完整的知识块。

规则：
1. 每个知识块必须是一个**完整的语义单元**（一个完整的条款、一个完整的工作步骤、一个完整的定义）。
2. 必须尊重原始文档的结构边界：同一法规/文件的内容放在一起，不同文件的内容分开。
3. 以 `[CHUNK]` 标记每个块的开始，后面跟块标题（用 `##` 格式），然后换行，再写块内容。
4. 不要截断句子——在句号、段落结束处切分。
5. 每个块长度控制在 150~1500 字之间。
6. 标题应反映该块的实际内容，例如："申请入党\xb7递交申请书"、"政治审查\xb7审查内容"。

输出格式示例：
[CHUNK]
## 入党申请\xb7谈话要求
党组织收到入党申请书后，应当在一个月内派人同入党申请人谈话\x85\x85

[CHUNK]
## 积极分子确定\xb7推荐程序
采取党员推荐、群团组织推优等方式产生人选\x85\x85
"""'''

new_prompt = '''_CHUNKING_SYSTEM_PROMPT = """你是一名党务文档处理专家。你的任务是将贵州师范大学组织发展工作专项培训手册的文本按照语义边界分割成独立、语义完整的知识块。

本手册包含以下核心文件（请严格按文件来源分块）：
1. **党支部工作条例** \u2014 党支部组织设置、基本任务、工作机制、组织生活等
2. **发展党员工作细则** \u2014 发展党员的总要求、原则和全流程规定
3. **贵州省发展党员规程（25步流程）** \u2014 从递交申请书到建档归档的完整25个步骤，每步必须独立成块
4. **贵州师范大学制度文件** \u2014 本校的发展党员规范、公示制度、预审制度等
5. **模板表格** \u2014 会议记录模板、审查表、志愿书、公示模板等

规则：
1. 每个知识块必须是一个**完整的语义单元**（一个完整的条款、一个完整的工作步骤、一个完整的表格模板）。
2. **严格尊重原始文档的结构边界**：同一法规/文件的相邻内容放在同一块内；不同文件、不同章节的内容必须分块。
3. **25步流程的每一步必须独立成块**，块标题格式为：\u300c第N步\xb7步骤名称\u300d，例如\u300c第1步\xb7递交入党申请书\u300d。
4. 以 `[CHUNK]` 标记每个块的开始，后面跟块标题（用 `##` 格式），然后换行，再写块内容。
5. 不要截断句子\u2014\u2014在句号、段落结束处切分。条款编号（第X条）应保留在块内。
6. 每个块长度控制在 150~1500 字之间。若一个条款超出1500字，按自然段落拆分。
7. 标题应准确反映文件来源和内容，格式为：\u300c文件简称\xb7具体内容\u300d。

输出格式示例：
[CHUNK]
## 党支部工作条例\xb7组织设置
第三条 党支部设置一般以单位、区域为主\x85\x85支部党员人数一般不超过50人。

[CHUNK]
## 第1步\xb7递交入党申请书
条件：年满十八岁的中国工人、农民、军人、知识分子和其他社会阶层的先进分子\x85\x85向工作、学习所在单位党组织提出书面申请。

[CHUNK]
## 贵州省发展党员规程\xb7政治审查
凡确定为发展对象的，必须进行政治审查。政审内容包括：对党的理论和路线方针政策的态度\x85\x85

[CHUNK]
## 贵州师范大学\xb7发展党员公示制度
为加强我校发展党员工作的民主监督\x85\x85公示时间一般为5-7个工作日。

[CHUNK]
## 模板表格\xb7预备党员转正支部大会记录
会议时间：____年__月__日  会议地点：____  参会人员：____
"""'''

if old_prompt not in content:
    print('EDIT 1: ERROR - old prompt not found')
    print(repr(old_prompt[:100]))
else:
    content = content.replace(old_prompt, new_prompt, 1)
    print('EDIT 1: OK')

# =====================================================
# EDIT 2: Add _llm_rerank function after _rule_chunk
# =====================================================
if 'def _llm_rerank' in content:
    print('EDIT 2: SKIP - already exists')
else:
    insertion_point = '# ══════════════════════════════════════════════════════\n#  3. 知识库构建（DOCX → 分块 → 索引）\n# ══════════════════════════════════════════════════════'
    if insertion_point not in content:
        print('EDIT 2: ERROR - insertion point not found')
    else:
        rerank_func = '''

def _llm_rerank(chunks: list[dict], query: str, top_k: int = 5) -> list[dict]:
    """使用 LLM 对检索候选块进行相关性重排序

    Args:
        chunks: [{"title": "...", "content": "...", "score": 0.xx}, ...]
        query: 原始查询
        top_k: 返回前 K 条

    Returns:
        重排序后的 top_k 条，每项增加 "llm_score" 字段
    """
    if not chunks or not query:
        return chunks[:top_k] if chunks else []

    # 构建评分 prompt
    items_text = []
    for i, c in enumerate(chunks, 1):
        title = c.get("title", "未知")
        content_preview = c.get("content", "")[:300]
        items_text.append(f"[{i}] 标题: {title}\\n内容: {content_preview}")

    items_str = "\\n---\\n".join(items_text)

    system_prompt = "你是一名党务知识检索专家。你的任务是对检索到的文档片段进行相关性评分。"
    user_prompt = f"""查询: {query}

以下是从知识库中检索到的文档片段，请逐一评估每个片段与查询的相关性，给出 0-10 的整数评分（0=完全不相关，10=完全匹配）。

{items_str}

请按以下 JSON 格式输出（不要加其他内容）：
{{"scores": [{{"idx": 1, "score": 8}}, {{"idx": 2, "score": 3}}]}}
"""

    result = _call_llm(system_prompt, user_prompt, max_tokens=1024)
    if not result:
        return chunks[:top_k]

    # 解析 JSON 评分
    try:
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            scores_map = {}
            for entry in data.get("scores", []):
                idx = entry.get("idx", 0)
                score = entry.get("score", 0)
                if 1 <= idx <= len(chunks):
                    scores_map[idx - 1] = min(10, max(0, int(score)))

            for i, c in enumerate(chunks):
                llm_score = scores_map.get(i, 5)
                c["llm_score"] = llm_score
                orig = c.get("score", 0.5)
                c["rerank_score"] = round(0.5 * orig + 0.5 * (llm_score / 10), 4)

            chunks.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    except Exception:
        pass

    return chunks[:top_k]

'''
        content = content.replace(insertion_point, rerank_func + insertion_point, 1)
        print('EDIT 2: OK')

# =====================================================
# EDIT 3: Update search() - add rerank param, HYBRID_TOP_K
# =====================================================

# 3a: Add HYBRID_TOP_K constant
old_consts = '# \u2500\u2500 \u691c\u7d22\u53c2\u6570 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\nDEFAULT_TOP_K = 5\nHYBRID_ALPHA = 0.6  # \u7a20\u5bc6\u691c\u7d22\u6743\u91cd (0.6) vs \u7a00\u758f\u691c\u7d22\u6743\u91cd (0.4)'
# Simpler: just match the line with HYBRID_ALPHA
old_hybrid_line = 'HYBRID_ALPHA = 0.6  # \u7a20\u5bc6\u691c\u7d22\u6743\u91cd (0.6) vs \u7a00\u758f\u691c\u7d22\u6743\u91cd (0.4)'
new_hybrid_lines = 'HYBRID_TOP_K = 15    # \u6df7\u5408\u691c\u7d22\u5019\u9009\u6c60\u5927\u5c0f\uff08\u7528\u4e8e rerank \u524d\u7684\u5019\u9009\u6c60\uff09\nHYBRID_ALPHA = 0.6  # \u7a20\u5bc6\u691c\u7d22\u6743\u91cd (0.6) vs \u7a00\u758f\u691c\u7d22\u6743\u91cd (0.4)'
if old_hybrid_line not in content:
    print('EDIT 3a: ERROR - HYBRID_ALPHA line not found')
else:
    content = content.replace(old_hybrid_line, new_hybrid_lines, 1)
    print('EDIT 3a: OK')

# 3b: Update search() signature and dense query n_results
old_search_sig = '''    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        alpha: float = HYBRID_ALPHA,
    ) -> list[dict]:
        """\u6df7\u5408\u691c\u7d22

        Args:
            query: \u67e5\u8be2\u6587\u672c
            top_k: \u8fd4\u56de\u7ed3\u679c\u6570
            alpha: \u7a20\u5bc6\u691c\u7d22\u6743\u91cd [0,1]\uff0c1=\u7eaf\u5411\u91cf\uff0c0=\u7eafBM25

        Returns:
            [{"title": "...", "content": "...", "score": 0.85, "source": "dense|sparse|hybrid"}, ...]
        """
        if not self._ensure_initialized():
            return []

        # \u2500\u2500 \u7a20\u5bc6\u691c\u7d22 \u2500\u2500
        dense_results: dict[str, dict] = {}
        try:
            resp = self._chroma_collection.query(
                query_texts=[query],
                n_results=top_k + 5,
                include=["documents", "metadatas", "distances"],
            )'''

new_search_sig = '''    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        alpha: float = HYBRID_ALPHA,
        rerank: bool = True,
    ) -> list[dict]:
        """\u6df7\u5408\u691c\u7d22\uff08\u652f\u6301 LLM \u91cd\u6392\u5e8f\uff09

        Args:
            query: \u67e5\u8be2\u6587\u672c
            top_k: \u8fd4\u56de\u7ed3\u679c\u6570
            alpha: \u7a20\u5bc6\u691c\u7d22\u6743\u91cd [0,1]\uff0c1=\u7eaf\u5411\u91cf\uff0c0=\u7eafBM25
            rerank: \u662f\u5426\u4f7f\u7528 LLM \u8fdb\u884c\u76f8\u5173\u6027\u91cd\u6392\u5e8f\uff08\u9700\u8981 LLM \u53ef\u7528\uff09

        Returns:
            [{"title": "...", "content": "...", "score": 0.85, "source": "dense|sparse|hybrid", "llm_score": 8}, ...]
        """
        if not self._ensure_initialized():
            return []

        # \u82e5\u542f\u7528 rerank\uff0c\u4f7f\u7528\u66f4\u5927\u7684\u5019\u9009\u6c60
        candidate_k = HYBRID_TOP_K if rerank else top_k + 5

        # \u2500\u2500 \u7a20\u5bc6\u691c\u7d22 \u2500\u2500
        dense_results: dict[str, dict] = {}
        try:
            resp = self._chroma_collection.query(
                query_texts=[query],
                n_results=candidate_k,
                include=["documents", "metadatas", "distances"],
            )'''

if old_search_sig not in content:
    print('EDIT 3b: ERROR - search sig not found')
    # Try to find what's different
    idx = content.find('n_results=top_k + 5')
    if idx >= 0:
        print(f'  Found at idx {idx}, nearby: {repr(content[idx-50:idx+50])}')
else:
    content = content.replace(old_search_sig, new_search_sig, 1)
    print('EDIT 3b: OK')

# 3c: Update fusion return with rerank
old_fusion_return = '''        fused.sort(key=lambda x: x["score"], reverse=True)
        return fused[:top_k]'''

new_fusion_return = '''        fused.sort(key=lambda x: x["score"], reverse=True)

        # \u2500\u2500 LLM \u91cd\u6392\u5e8f\uff08\u53ef\u9009\uff09 \u2500\u2500
        if rerank and fused:
            reranked = _llm_rerank(fused, query, top_k=top_k)
            if reranked:
                return reranked

        return fused[:top_k]'''

if old_fusion_return not in content:
    print('EDIT 3c: ERROR - fusion return not found')
else:
    content = content.replace(old_fusion_return, new_fusion_return, 1)
    print('EDIT 3c: OK')

# =====================================================
# EDIT 4: Update enhanced_system_context()
# =====================================================
old_esc_start = '    def enhanced_system_context(self, query: str, top_k: int = 3) -> str:'
old_esc_content = '''    def enhanced_system_context(self, query: str, top_k: int = 3) -> str:
        """\u6839\u636e\u67e5\u8be2\uff0c\u751f\u6210\u589e\u5f3a\u7684\u7cfb\u7edf\u4e0a\u4e0b\u6587\uff08\u7528\u4e8e\u6ce8\u5165 prompt\uff09"""
        results = self.search(query, top_k=top_k, alpha=0.7)
        if not results:
            return ""
        valid = [r for r in results if r["score"] >= 0.15]
        if not valid:
            return ""

        lines = ["\u3010\u77e5\u8bc6\u5e93\u53c2\u8003\u4fe1\u606f\u3011"]
        for i, r in enumerate(valid, 1):
            lines.append(f"\u53c2\u8003 {i}: \u300c{r['title']}\u300d")
            lines.append(r["content"][:300].strip())
        return "\\n".join(lines)'''

new_esc = '''    def enhanced_system_context(self, query: str, top_k: int = 3) -> str:
        """\u6839\u636e\u67e5\u8be2\uff0c\u751f\u6210\u589e\u5f3a\u7684\u7cfb\u7edf\u4e0a\u4e0b\u6587\uff08\u7528\u4e8e\u6ce8\u5165 prompt\uff09

        \u8f93\u51fa\u683c\u5f0f\u5305\u542b\u6e05\u6670\u7684\u6587\u6863\u6765\u6e90\u3001\u7ae0\u8282\u5f15\u7528\u548c\u5185\u5bb9\u6458\u8981\u3002
        """
        results = self.search(query, top_k=top_k, alpha=0.7, rerank=True)
        if not results:
            return ""
        valid = [r for r in results if r["score"] >= 0.15]
        if not valid:
            return ""

        lines = ["\u3010\u77e5\u8bc6\u5e93\u53c2\u8003\u4fe1\u606f\uff08\u7ed3\u6784\u5316\u5f15\u7528\uff09\u3011"]
        lines.append("=" * 50)
        for i, r in enumerate(valid, 1):
            title = r["title"]
            score = r.get("llm_score", round(r["score"] * 10, 1))
            source_tag = "\U0001f4c4"

            # \u667a\u80fd\u8bc6\u522b\u6587\u6863\u6765\u6e90
            if "\u515a\u652f\u90e8" in title:
                source_tag = "\U0001f4dc \u652f\u90e8\u5de5\u4f5c\u6761\u4f8b"
            elif "\u7b2c" in title and "\u6b65" in title:
                source_tag = "\U0001f4cb \u8d35\u5dde\u770125\u6b65\u89c4\u7a0b"
            elif "\u8d35\u5dde\u5e08\u8303\u5927\u5b66" in title or "\u5e08\u5927" in title:
                source_tag = "\U0001f3eb \u8d35\u5e08\u5927\u5236\u5ea6"
            elif "\u6a21\u677f" in title or "\u8868\u683c" in title or "\u8bb0\u5f55" in title:
                source_tag = "\U0001f4cb \u6a21\u677f\u8868\u683c"
            elif "\u53d1\u5c55\u515a\u5458" in title:
                source_tag = "\U0001f4dc \u53d1\u5c55\u515a\u5458\u7ec6\u5219"

            lines.append(f"\\n\u3010\u53c2\u8003 {i}\u3011{source_tag}")
            lines.append(f"  \u7ae0\u8282\uff1a{title}")
            lines.append(f"  \u76f8\u5173\u5ea6\u8bc4\u5206\uff1a{score}/10")
            # \u5e26\u7f29\u8fdb\u7684\u5185\u5bb9\u6458\u8981
            c = r["content"][:350].strip()
            lines.append(f"  \u5185\u5bb9\u6458\u8981\uff1a{c}")
            if len(r["content"]) > 350:
                lines.append(f"  \u2026\u2026\uff08\u5168\u6587\u5171 {len(r['content'])} \u5b57\uff09")
        lines.append("\\n" + "=" * 50)
        lines.append(f"\u5171\u68c0\u7d22\u5230 {len(valid)} \u6761\u76f8\u5173\u89c4\u7a0b\uff0c\u8bf7\u4f9d\u636e\u4e0a\u8ff0\u53c2\u8003\u4fe1\u606f\u56de\u7b54\u7528\u6237\u95ee\u9898\u3002")
        return "\\n".join(lines)'''

if old_esc_content not in content:
    print('EDIT 4: ERROR - enhanced_system_context not found')
    # Try finding just the start
    if old_esc_start in content:
        print('  Found start line but content mismatch')
else:
    content = content.replace(old_esc_content, new_esc, 1)
    print('EDIT 4: OK')

# Write back
with open('partymate/tools/rag.py', 'w', encoding='utf-8') as f:
    f.write(content)

print()
print('=== All edits applied ===')
