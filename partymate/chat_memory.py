from __future__ import annotations

import json
import os
from collections import deque
from typing import Any

import httpx

from partymate.db.repository import Repository

# Load config from env or default to same as agent.py
API_BASE = os.getenv("PARTYMATE_API_BASE") or os.getenv("OPENAI_BASE_URL") or "http://127.0.0.1:11434/v1"
API_KEY = os.getenv("PARTYMATE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
MODEL = os.getenv("PARTYMATE_MODEL") or os.getenv("HERMES_MODEL") or "qwen3.5:4b"


async def _call_llm_summarize(existing_summary: str, new_messages: list[dict], max_chars: int = 200) -> str:
    """Async call to LLM to summarize conversation history."""
    if not API_KEY and "127.0.0.1" not in API_BASE and "localhost" not in API_BASE:
        # Fallback if no API key and not local
        return existing_summary

    prompt = (
        f"你是会话摘要助手。请将以下历史会话和新对话压缩成简练的摘要，保留关键事实、提及的成员和得出的结论。\n"
        f"【已有摘要】\n{existing_summary or '无'}\n\n"
        f"【新对话】\n"
    )
    for m in new_messages:
        role = "用户" if m["role"] == "user" else "助手"
        content = m.get("content", "")
        # ignore tool calls in simple summary to save tokens, or just truncate
        prompt += f"[{role}]: {content[:200]}\n"
    
    prompt += f"\n请输出合并后的新摘要，字数不超过{max_chars}字，直接输出摘要内容，不要有废话。"

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{API_BASE}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            new_summary = data["choices"][0]["message"]["content"].strip()
            # truncate to max_chars just in case
            return new_summary[:max_chars]
    except Exception as e:
        print(f"Error summarizing chat: {e}")
        return existing_summary


class SlidingWindowBuffer:
    """双端队列滑动窗口，固定保留最近 N 轮原始对话"""
    
    def __init__(self, max_turns: int = 5):
        # 1 turn usually = 1 user + 1 assistant + maybe tool calls.
        # We roughly say maxlen = max_turns * 3
        self._buf: deque[dict] = deque(maxlen=max_turns * 3)
    
    def push(self, message: dict) -> dict | None:
        """压入新消息，返回被挤出的消息（None 表示未溢出）"""
        if len(self._buf) == self._buf.maxlen:
            evicted = self._buf[0]
        else:
            evicted = None
        self._buf.append(message)
        return evicted
    
    def to_list(self) -> list[dict]:
        return list(self._buf)


class IncrementalSummaryBuffer:
    """增量摘要缓冲，维护滚动压缩的会话摘要"""
    
    COMPRESS_EVERY = 6  # 每挤出 6 条消息触发一次压缩
    MAX_SUMMARY_CHARS = 200
    
    def __init__(self, initial_summary: str = ""):
        self._summary: str = initial_summary
        self._pending: list[dict] = []
    
    async def add_evicted(self, message: dict) -> None:
        """接收被滑动窗口挤出的消息"""
        self._pending.append(message)
        if len(self._pending) >= self.COMPRESS_EVERY:
            await self._compress()
    
    async def _compress(self) -> None:
        if not self._pending:
            return
        new_summary = await _call_llm_summarize(
            existing_summary=self._summary,
            new_messages=self._pending,
            max_chars=self.MAX_SUMMARY_CHARS,
        )
        self._summary = new_summary
        self._pending.clear()
    
    def get_summary(self) -> str:
        return self._summary

    def get_pending(self) -> list[dict]:
        """返回已挤出但尚未压缩的消息（盲区保护）"""
        return list(self._pending)

    def get_state(self) -> dict:
        return {
            "summary": self._summary,
            "pending": self._pending
        }
    
    def load_state(self, state: dict):
        self._summary = state.get("summary", "")
        self._pending = state.get("pending", [])


class VectorHistoryRecaller:
    """向量化历史召回，ChromaDB 不可用时自动降级"""
    
    def __init__(self, session_id: str):
        self._session_id = session_id
        self._available = False
        self._collection = None
        try:
            import chromadb
            # Default chroma path
            db_dir = os.environ.get("HERMES_AGENT_STATE")
            if not db_dir:
                db_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
            chroma_path = os.path.join(db_dir, "chroma_chat")
            
            client = chromadb.PersistentClient(path=chroma_path)
            self._collection = client.get_or_create_collection(name="chat_history")
            self._available = True
        except Exception as e:
            print(f"ChromaDB not available for chat history: {e}")
    
    async def index_turn(self, user_msg: str, assistant_msg: str) -> None:
        """异步将一轮对话向量化入库"""
        if not self._available or not self._collection:
            return
        if not user_msg and not assistant_msg:
            return
            
        doc_id = f"{self._session_id}_{os.urandom(4).hex()}"
        doc_text = f"User: {user_msg}\nAssistant: {assistant_msg}"
        
        try:
            self._collection.add(
                ids=[doc_id],
                documents=[doc_text],
                metadatas=[{"session_id": self._session_id}]
            )
        except Exception as e:
            print(f"Failed to index chat turn: {e}")
    
    async def recall(self, query: str, top_k: int = 3) -> list[str]:
        """召回与当前问题最相关的历史片段"""
        if not self._available or not self._collection or not query.strip():
            return []
            
        try:
            res = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where={"session_id": self._session_id}
            )
            docs = res.get("documents", [[]])[0]
            return docs
        except Exception as e:
            print(f"Failed to recall chat history: {e}")
            return []


class SessionMemory:
    """统一的会话记忆管理器"""
    
    def __init__(self, session_id: str, repo: Repository):
        self.session_id = session_id
        self.repo = repo
        self.sliding_window = SlidingWindowBuffer(max_turns=5)
        self.summary_buffer = IncrementalSummaryBuffer()
        self.vector_recaller = VectorHistoryRecaller(session_id)
        
        self._load_from_db()

    def _load_from_db(self):
        """从数据库加载已有消息，填充窗口和摘要。"""
        # For simplicity, we just load the last 15 messages into the sliding window.
        # Older messages are implicitly assumed to be lost or already in summary if we had persistent summary state.
        # Here we just re-populate the window.
        msgs = self.repo.get_chat_messages(self.session_id, limit=20)
        # We need to construct dicts suitable for LLM context
        for m in msgs:
            msg_dict = {"role": m["role"], "content": m["content"]}
            if m.get("tool_calls_json"):
                try:
                    tool_calls = json.loads(m["tool_calls_json"])
                    if tool_calls:
                        msg_dict["tool_calls"] = tool_calls
                except:
                    pass
            self.sliding_window.push(msg_dict)
            
    async def add_message(self, role: str, content: str, tool_calls: list | None = None):
        """添加新消息到记忆中"""
        msg_dict = {"role": role, "content": content}
        if tool_calls:
            msg_dict["tool_calls"] = tool_calls
            
        # 1. 存入数据库
        tc_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else ""
        self.repo.add_chat_message(self.session_id, role, content, tc_json)
        
        # 2. 压入滑动窗口
        evicted = self.sliding_window.push(msg_dict)
        
        # 3. 如果被挤出，送入摘要队列
        if evicted:
            await self.summary_buffer.add_evicted(evicted)

    async def get_context_messages(self, current_query: str) -> list[dict]:
        """三层策略组装最终上下文"""
        messages = []
        
        # 1. 摘要注入（最旧，最压缩）
        if summary := self.summary_buffer.get_summary():
            messages.append({"role": "system", "content": f"[历史摘要] {summary}"})
        
        # 2. pending 注入（已从滑动窗口挤出、但尚未满足压缩阈值的消息）
        # 若不注入，这部分消息处于既不在 deque、也不在 summary 的盲区
        pending = self.summary_buffer.get_pending()
        if pending:
            messages.extend(pending)
        
        # 3. 向量召回注入（语义相关）
        recalled = await self.vector_recaller.recall(current_query, top_k=3)
        if recalled:
            messages.append({"role": "system", "content": "[相关历史]\n" + "\n---\n".join(recalled)})
        
        # 4. 滑动窗口原文（最近，最精确）
        messages.extend(self.sliding_window.to_list())
        
        return messages
