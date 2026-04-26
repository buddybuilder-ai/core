"""Feng Shui RAG Service with Conversation Memory.

LLM backend: OpenRouter (matching core's existing infrastructure).
Vectorstore: ChromaDB loaded by vectorstore_service (from feng-shui-rag pipeline).

แก้ SYSTEM_PROMPT, DOMAIN_KEYWORDS, OUT_OF_SCOPE_MSG ที่:
  feng-shui-rag/src/rag_constants.py  ← single source of truth

Flow (ใหม่):
  Layer 1 (keyword) → Classify (LLM, no embed) → Embed+Retrieve once w/ filter → LLM answer w/ persona
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _rlog(msg: str) -> None:
    """Write RAG debug line to stdout + /tmp/rag.log for visibility."""
    import sys
    encoded = (msg + "\n").encode("utf-8", errors="replace")
    try:
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
    except Exception:
        try:
            print(msg.encode("utf-8", errors="replace").decode("ascii", errors="replace"), flush=True)
        except Exception:
            pass
    try:
        with open("/tmp/rag.log", "a", encoding="utf-8") as _f:
            _f.write(msg + "\n")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Import shared constants from core/rag_pipeline/rag_constants.py
# (single source of truth — แก้ที่ rag_pipeline/rag_constants.py)
# parents: services(0)→application(1)→layout(2)→modules(3)→src(4)→core(5)
# ---------------------------------------------------------------------------
_RAG_PIPELINE = Path(__file__).resolve().parents[5] / "rag_pipeline"
if str(_RAG_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_RAG_PIPELINE))

from rag_constants import BEDROOM_KEYWORDS  # noqa: E402, I001
from rag_constants import CLASSIFY_SYSTEM_PROMPT as _CLASSIFY_SYSTEM_PROMPT  # noqa: E402
from rag_constants import DOMAIN_KEYWORDS  # noqa: E402
from rag_constants import EXCLUDE_KEYWORDS  # noqa: E402
from rag_constants import MODE_ADDITIONS as _MODE_ADDITIONS  # noqa: E402
from rag_constants import OUT_OF_SCOPE_MSG  # noqa: E402
from rag_constants import PERSONA_PROMPTS as _PERSONA_PROMPTS  # noqa: E402
from rag_constants import SYSTEM_PROMPT_RULES as _SYSTEM_PROMPT_RULES  # noqa: E402


class FengShuiRAGService:
    """RAG service — flow: Layer1 → Classify (LLM) → Embed+Retrieve once (filtered) → LLM w/ persona."""

    FUZZY_MATCH_THRESHOLD: int = 3

    def __init__(self) -> None:
        self._vectorstore: Any = None
        self._retriever: Any = None
        from src.config.settings import get_settings

        s = get_settings()
        self.RELEVANCE_THRESHOLD: float = s.RAG_RELEVANCE_THRESHOLD

    # ------------------------------------------------------------------
    # Vectorstore (lazy-loaded)
    # ------------------------------------------------------------------

    def _ensure_vectorstore(self) -> Any:
        if self._vectorstore is None:
            try:
                from src.config.settings import get_settings
                from src.modules.layout.infrastructure.vectorstore_service import (
                    get_cached_vectorstore,
                )

                settings = get_settings()
                self._vectorstore = get_cached_vectorstore(
                    settings.CHROMA_DB_PATH, settings.EMBEDDING_MODEL_LOCAL
                )
                self._retriever = self._vectorstore.as_retriever(
                    search_type=settings.RAG_SEARCH_TYPE,
                    search_kwargs={"k": settings.RAG_TOP_K},
                )
                logger.info(
                    "FengShuiRAGService: vectorstore loaded from %s", settings.CHROMA_DB_PATH
                )
            except Exception as exc:
                logger.warning("FengShuiRAGService: could not load vectorstore (%s)", exc)
        return self._vectorstore

    # ------------------------------------------------------------------
    # Layer 1: Domain keyword check + fuzzy match (sync, no LLM, no embed)
    # ------------------------------------------------------------------

    def _fuzzy_match(self, text: str, keyword: str) -> bool:
        threshold = self.FUZZY_MATCH_THRESHOLD
        for word in text.split():
            if abs(len(word) - len(keyword)) > threshold:
                continue
            diff_count = sum(1 for a, b in zip(word, keyword) if a != b)
            if diff_count <= threshold:
                return True
        return False

    def _has_domain_keywords(
        self,
        question: str,
        conversation_history: list[dict[str, str]],
    ) -> bool:
        """Layer 1: keyword + fuzzy match + history context. No embedding, no LLM."""
        q_lower = question.lower()

        # Sub-layer 0: block non-bedroom rooms
        has_exclude = any(kw.lower() in q_lower for kw in EXCLUDE_KEYWORDS)
        if has_exclude:
            has_bedroom = any(kw.lower() in q_lower for kw in BEDROOM_KEYWORDS)
            if not has_bedroom:
                matched_exclude = next(kw for kw in EXCLUDE_KEYWORDS if kw.lower() in q_lower)
                _rlog(f'  [RAG] Layer 0 ❌  non-bedroom room: "{matched_exclude}" (no bedroom keyword)')
                return False
            _rlog("  [RAG] Layer 0 ✅  exclude keyword found but bedroom keyword also present")

        exact_matches = [kw for kw in DOMAIN_KEYWORDS if kw.lower() in q_lower]
        if exact_matches:
            _rlog(f"  [RAG] Layer 1 ✅  exact match: {exact_matches}")
            return True

        fuzzy_matches = [
            kw for kw in DOMAIN_KEYWORDS if len(kw) >= 4 and self._fuzzy_match(q_lower, kw.lower())
        ]
        if fuzzy_matches:
            _rlog(f"  [RAG] Layer 1 ✅  fuzzy match: {fuzzy_matches}")
            return True

        if conversation_history and len(question) < 15:
            recent = conversation_history[-4:]
            for turn in recent:
                combined = turn.get("content", "").lower()
                for kw in DOMAIN_KEYWORDS:
                    if kw.lower() in combined:
                        _rlog(f'  [RAG] Layer 1 ✅  history context match: "{kw}"')
                        return True

        _rlog("  [RAG] Layer 1 ❌  no domain keywords found")
        return False

    # ------------------------------------------------------------------
    # Classify: feng_shui / interior_design / both  (LLM, raw text, no embed)
    # Runs BEFORE embedding so filter is known at embed time.
    # ------------------------------------------------------------------

    async def _classify_query(self, question: str) -> str:
        """Classify question type via LLM — called before embedding."""
        import httpx
        from src.config.settings import get_settings

        s = get_settings()
        provider = s.LLM_PROVIDER
        model = s.LLM_MODEL_NAME

        if provider == "ollama":
            url = f"{s.OLLAMA_BASE_URL}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
        elif provider == "groq":
            url = f"{s.GROQ_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {s.GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
        else:
            url = f"{s.OPENROUTER_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {s.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://buddybuilder.ai",
                "X-Title": "BuddyBuilder AI",
            }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    url,
                    headers=headers,
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
                            {"role": "user", "content": question},
                        ],
                        "max_tokens": 10,
                        "temperature": 0,
                    },
                )
                if resp.status_code == 200:
                    raw = resp.json()["choices"][0]["message"]["content"].strip().lower()
                    if "feng_shui" in raw or "feng shui" in raw:
                        kt = "feng_shui"
                    elif "interior" in raw:
                        kt = "interior_design"
                    elif "both" in raw:
                        kt = "both"
                    else:
                        kt = "feng_shui"
                    _rlog(f"  [RAG] QueryType: {kt} (LLM/{provider})")
                    return kt
                _rlog(f"  [RAG] QueryType LLM status={resp.status_code} → both (fallback)")
        except Exception as exc:
            _rlog(f"  [RAG] QueryType LLM failed ({exc}) → both (fallback)")

        return "both"

    # ------------------------------------------------------------------
    # Query enrichment — inject Kua context
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_kua_from_history(history: list[dict[str, str]]) -> str | None:
        import re
        pattern = re.compile(
            r"\*{0,2}กัว\*{0,2}\s*[=:]*\s*\*{0,2}([1-9])\*{0,2}"
            r"|\*{0,2}เลขกัว\*{0,2}\s*\*{0,2}([1-9])\*{0,2}"
            r"|\*{0,2}ได้กัว\*{0,2}\s*\*{0,2}([1-9])\*{0,2}",
            re.UNICODE,
        )
        for turn in reversed(history):
            if turn.get("role") == "assistant":
                m = pattern.search(turn.get("content", ""))
                if m:
                    return next(g for g in m.groups() if g is not None)
        return None

    @staticmethod
    def _has_birth_info(question: str) -> bool:
        import re
        has_year = bool(re.search(r"(เกิด|ปี)\s*(ค\.?ศ\.?)?\s*[12]\d{3}", question))
        has_gender = any(kw in question for kw in ("ชาย", "หญิง", "ผู้ชาย", "ผู้หญิง", "เพศชาย", "เพศหญิง"))
        return has_year and has_gender

    @staticmethod
    def _enrich_retrieval_query(question: str, history: list[dict[str, str]]) -> str:
        import re
        if re.search(r"กัว\s*[1-9]", question):
            return question
        kua = FengShuiRAGService._extract_kua_from_history(history)
        if kua:
            _rlog(f"  [RAG] Query enriched with Kua {kua} from history")
            return f"กัว {kua} {question}"
        return question

    # ------------------------------------------------------------------
    # Layer 2 + Retrieve — single embed call, filter applied from classify result
    # ------------------------------------------------------------------

    def _embed_and_retrieve(
        self,
        query: str,
        knowledge_type: str,
    ) -> tuple[bool, str, list[dict[str, Any]]]:
        """Embed query once, check L2 threshold, retrieve with filter.

        knowledge_type is already known (from _classify_query), so the ChromaDB
        filter is set at embed time — no wasted prefetched docs, no re-embedding.

        Returns (is_relevant, context_str, source_docs).
        """
        from src.config.settings import get_settings

        s = get_settings()
        top_k = s.RAG_TOP_K

        vs = self._ensure_vectorstore()
        if vs is None:
            _rlog("  [RAG] Layer 2 ⚠️  vectorstore unavailable — allowing query")
            return True, "", []

        meta_filter = (
            {"knowledge_type": {"$in": [knowledge_type, "both"]}}
            if knowledge_type != "both"
            else None
        )

        if meta_filter:
            _rlog(f"  [RAG] Layer 2 — filter: knowledge_type ∈ [{knowledge_type}, both]")
        else:
            _rlog("  [RAG] Layer 2 — filter: all types (knowledge_type=both)")

        search_kwargs: dict[str, Any] = {"k": top_k}
        if meta_filter:
            search_kwargs["filter"] = meta_filter

        try:
            docs_with_scores = vs.similarity_search_with_score(query, **search_kwargs)

            # Fallback: retry without filter if filtered result is empty
            if not docs_with_scores and meta_filter:
                _rlog("  [RAG] Filter returned 0 docs → retrying without filter")
                docs_with_scores = vs.similarity_search_with_score(query, k=top_k)

            if not docs_with_scores:
                _rlog(f"  [RAG] Layer 2 ❌  no documents found\n{'─' * 60}")
                return False, "", []

            _rlog(f"  [RAG] Layer 2 — L2 Scores (threshold ≤ {self.RELEVANCE_THRESHOLD}):")
            for i, (doc, score) in enumerate(docs_with_scores, 1):
                status = "✅" if score <= self.RELEVANCE_THRESHOLD else "❌"
                src = doc.metadata.get("source", "?").split("/")[-1]
                preview = doc.page_content[:60].replace("\n", " ")
                _rlog(f"    [{i}] L2={score:.4f} {status}  src={src}")
                _rlog(f'        "{preview}..."')

            best_score: float = docs_with_scores[0][1]
            is_relevant = best_score <= self.RELEVANCE_THRESHOLD
            verdict = "✅ PASS → ส่ง LLM" if is_relevant else "❌ BLOCKED"
            _rlog(f"  [RAG] Best={best_score:.4f} → {verdict}")
            _rlog(f"{'─' * 60}")

            if not is_relevant:
                return False, "", []

            context, source_docs = self._format_docs([doc for doc, _ in docs_with_scores])
            return True, context, source_docs

        except Exception as exc:
            logger.warning("RAG embed+retrieve failed (%s) - allowing query", exc)
            _rlog(f"  [RAG] Layer 2 ⚠️  failed: {exc} — allowing")
            return True, "", []

    def _format_docs(self, docs: list[Any]) -> tuple[str, list[dict[str, Any]]]:
        """Format retrieved docs into (context_str, source_docs_list)."""
        formatted_parts: list[str] = []
        source_docs: list[dict[str, Any]] = []

        _rlog(f"  [RAG] Retrieved {len(docs)} doc(s) → LLM context:")
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "ฐานความรู้")
            kt = doc.metadata.get("knowledge_type", "?")
            src_short = source.split("/")[-1]
            preview = doc.page_content.strip()[:70].replace("\n", " ")
            _rlog(f"    [{i}] src={src_short}  type={kt}")
            _rlog(f'        "{preview}..."')

            content = doc.page_content.strip()
            formatted_parts.append(f"[เอกสาร {i}] (แหล่งที่มา: {source})\n{content}")
            source_docs.append({"content": content[:400], "metadata": dict(doc.metadata)})

        return "\n\n---\n\n".join(formatted_parts), source_docs

    # ------------------------------------------------------------------
    # Prompt building — persona selected from knowledge_type
    # ------------------------------------------------------------------

    def _format_chat_history(self, conversation_history: list[dict[str, str]]) -> str:
        if not conversation_history:
            return "[ยังไม่มีประวัติการสนทนา - นี่คือการสนทนาใหม่]"

        formatted: list[str] = []
        turn_num = 1
        i = 0
        while i < len(conversation_history):
            turn = conversation_history[i]
            role = turn.get("role", "")
            content = turn.get("content", "")
            if role == "user":
                human_msg = content
                ai_msg = ""
                if (
                    i + 1 < len(conversation_history)
                    and conversation_history[i + 1].get("role") == "assistant"
                ):
                    ai_msg = conversation_history[i + 1].get("content", "")
                    i += 2
                else:
                    i += 1
                formatted.append(f"รอบที่ {turn_num}:\nคุณถาม: {human_msg}\nผมตอบ: {ai_msg}")
                turn_num += 1
            else:
                i += 1

        return "\n\n".join(formatted)

    def _build_messages(
        self,
        question: str,
        context: str,
        conversation_history: list[dict[str, str]],
        mode: str,
        knowledge_type: str = "both",
    ) -> list[dict[str, str]]:
        """Build messages — system prompt uses persona matching knowledge_type."""
        persona = _PERSONA_PROMPTS.get(knowledge_type, _PERSONA_PROMPTS["both"])
        mode_addition = _MODE_ADDITIONS.get(mode, _MODE_ADDITIONS["buddy"])
        system_content = f"{persona}\n\n{_SYSTEM_PROMPT_RULES}\n\n{mode_addition}"

        messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]

        for turn in conversation_history:
            role = turn.get("role", "user")
            content = turn.get("content", "").strip()
            if content and role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

        kua_num = FengShuiRAGService._extract_kua_from_history(conversation_history)
        if kua_num:
            detected_kua = f"กัว {kua_num} (พบจากการสนทนาก่อนหน้า)"
        elif FengShuiRAGService._has_birth_info(question):
            detected_kua = "[ข้อความนี้มีปีเกิด+เพศ — กรณี A: คำนวณกัวทันที ห้ามถามซ้ำ]"
        else:
            detected_kua = "[ไม่พบเลขกัวในประวัติ — ใช้หลักทั่วไป]"

        context_text = context if context else "[ไม่มีข้อมูลเพิ่มเติมจากฐานความรู้]"
        user_content = (
            f"[เลขกัวที่ตรวจพบ: {detected_kua}]\n\n"
            f"[ข้อมูลอ้างอิง]\n{context_text}\n\n"
            f"[คำถาม]\n{question}"
        )
        messages.append({"role": "user", "content": user_content})

        _rlog(
            f"  [RAG] Prompt: {len(messages)} messages ({len(conversation_history)} history + system + current)"
            f"  persona={knowledge_type}"
        )
        return messages

    # ------------------------------------------------------------------
    # LLM call helper — resolves provider URL + headers once
    # ------------------------------------------------------------------

    def _get_llm_url_and_headers(self) -> tuple[str, dict[str, str], str]:
        from src.config.settings import get_settings
        s = get_settings()
        provider = s.LLM_PROVIDER
        model = s.LLM_MODEL_NAME

        if provider == "ollama":
            return (
                f"{s.OLLAMA_BASE_URL}/v1/chat/completions",
                {"Content-Type": "application/json"},
                f"Ollama ({model})",
            )
        if provider == "groq":
            return (
                f"{s.GROQ_BASE_URL}/chat/completions",
                {"Authorization": f"Bearer {s.GROQ_API_KEY}", "Content-Type": "application/json"},
                f"Groq ({model})",
            )
        return (
            f"{s.OPENROUTER_BASE_URL}/chat/completions",
            {
                "Authorization": f"Bearer {s.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://buddybuilder.ai",
                "X-Title": "BuddyBuilder AI",
            },
            f"OpenRouter ({model})",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ask(
        self,
        question: str,
        mode: str = "buddy",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Answer a feng shui / design question using RAG.

        Flow: Layer1 (keyword) → Classify (LLM) → Embed+Retrieve once w/ filter → LLM answer w/ persona
        """
        import httpx
        from src.config.settings import get_settings

        settings = get_settings()
        history = (conversation_history or [])[-settings.MAX_HISTORY * 2:]

        _rlog(f"\n{'─' * 60}")
        _rlog(f'  [RAG] Question: "{question[:80]}"')
        _rlog(f"  [RAG] History: {len(history)} messages  Threshold={self.RELEVANCE_THRESHOLD}  TOP_K={settings.RAG_TOP_K}")

        # 1. Layer 1 — keyword gate (sync, no LLM, no embed)
        if not self._has_domain_keywords(question, history):
            _rlog(f"  [RAG] → BLOCKED (Layer 1)\n{'─' * 60}")
            return OUT_OF_SCOPE_MSG, []

        # 2. Mixed-room constraint injection (sync)
        q_lower = question.lower()
        excluded_rooms = [kw for kw in EXCLUDE_KEYWORDS if kw.lower() in q_lower]
        has_bedroom = any(kw.lower() in q_lower for kw in BEDROOM_KEYWORDS)
        if excluded_rooms and has_bedroom:
            rooms_str = ", ".join(excluded_rooms[:3])
            question_for_llm = (
                f"[ระบบ: คำถามนี้พูดถึง {rooms_str} ซึ่งอยู่นอก scope — "
                f"ห้ามตอบส่วน {rooms_str} เด็ดขาด ตอบเฉพาะห้องนอนเท่านั้น]\n{question}"
            )
            _rlog(f"  [RAG] Mixed-room detected ({rooms_str}) — injecting constraint")
        else:
            question_for_llm = question

        # 3. Classify (LLM, raw text) — determines persona + retrieval filter
        knowledge_type = await self._classify_query(question)

        # 4. Enrich retrieval query with Kua if in history
        retrieval_query = self._enrich_retrieval_query(question, history)

        # 5. Embed ONCE with filter already known — Layer 2 + retrieve combined
        is_relevant, context, source_docs = self._embed_and_retrieve(retrieval_query, knowledge_type)
        if not is_relevant:
            logger.info("FengShuiRAGService: out-of-scope (L2) -> %r", question[:60])
            return OUT_OF_SCOPE_MSG, []

        # 6. Build prompt with persona matching knowledge_type
        messages = self._build_messages(question_for_llm, context, history, mode, knowledge_type)

        # 7. LLM answer call
        url, headers, provider_label = self._get_llm_url_and_headers()
        _rlog(
            f"\n  ┌─ RAG → LLM Call ───────────────────────────────────\n"
            f"  │  Model      : {provider_label}\n"
            f"  │  Persona    : {knowledge_type}\n"
            f"  │  Temperature: {settings.LLM_TEMPERATURE_RAG}\n"
            f"  │  Threshold  : {self.RELEVANCE_THRESHOLD} (L2)  TOP_K={settings.RAG_TOP_K}\n"
            f"  └────────────────────────────────────────────────────"
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json={
                        "model": settings.LLM_MODEL_NAME,
                        "messages": messages,
                        "temperature": settings.LLM_TEMPERATURE_RAG,
                        "max_tokens": settings.RAG_MAX_TOKENS,
                    },
                    timeout=60.0,
                )
                if response.status_code == 200:
                    answer = str(response.json()["choices"][0]["message"]["content"])
                    logger.debug("FengShuiRAGService: answered %d chars", len(answer))
                    return answer, source_docs
                logger.error(
                    "FengShuiRAGService: LLM error %d - %s",
                    response.status_code,
                    response.text[:200],
                )
                return f"ขออภัยครับ ระบบมีปัญหาชั่วคราว (error {response.status_code})", []
        except Exception as exc:
            import traceback as _tb, os as _os
            _trace = _tb.format_exc()
            try:
                _log_path = _os.path.join(_os.environ.get("TEMP", "C:/temp"), "rag_error.log")
                with open(_log_path, "a", encoding="utf-8") as _ef:
                    _ef.write("[ask ERROR]\n" + _trace + "\n")
            except Exception:
                pass
            _rlog(f"[ask ERROR] {type(exc).__name__}: {exc}\n{_trace}")
            return f"ขออภัยครับ เกิดข้อผิดพลาด: {exc}", []

    async def ask_stream(
        self,
        question: str,
        mode: str = "buddy",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> "AsyncIterator[tuple[str, str, list[dict[str, Any]] | None]]":
        """Streaming variant — yields ("delta"|"final", text, sources|None).

        Flow: Layer1 (keyword) → Classify (LLM) → Embed+Retrieve once w/ filter → LLM stream w/ persona
        """
        import json
        import httpx
        from src.config.settings import get_settings

        settings = get_settings()
        history = (conversation_history or [])[-settings.MAX_HISTORY * 2:]

        _rlog(f"\n{'─' * 60}")
        _rlog(f'  [RAG stream] Question: "{question[:80]}"')

        # 1. Layer 1 — keyword gate
        if not self._has_domain_keywords(question, history):
            _rlog(f"  [RAG stream] → BLOCKED (Layer 1)\n{'─' * 60}")
            yield ("final", OUT_OF_SCOPE_MSG, [])
            return

        # 2. Mixed-room constraint
        q_lower = question.lower()
        excluded_rooms = [kw for kw in EXCLUDE_KEYWORDS if kw.lower() in q_lower]
        has_bedroom = any(kw.lower() in q_lower for kw in BEDROOM_KEYWORDS)
        if excluded_rooms and has_bedroom:
            rooms_str = ", ".join(excluded_rooms[:3])
            question_for_llm = (
                f"[ระบบ: คำถามนี้พูดถึง {rooms_str} ซึ่งอยู่นอก scope — "
                f"ห้ามตอบส่วน {rooms_str} เด็ดขาด ตอบเฉพาะห้องนอนเท่านั้น]\n{question}"
            )
        else:
            question_for_llm = question

        # 3. Classify (LLM, raw text) — determines persona + filter
        knowledge_type = await self._classify_query(question)

        # 4. Enrich retrieval query
        retrieval_query = self._enrich_retrieval_query(question, history)

        # 5. Embed ONCE with filter — Layer 2 + retrieve
        is_relevant, context, source_docs = self._embed_and_retrieve(retrieval_query, knowledge_type)
        if not is_relevant:
            logger.info("FengShuiRAGService: out-of-scope (L2, stream) -> %r", question[:60])
            yield ("final", OUT_OF_SCOPE_MSG, [])
            return

        # 6. Build prompt with persona
        messages = self._build_messages(question_for_llm, context, history, mode, knowledge_type)

        # 7. LLM streaming
        url, headers, _ = self._get_llm_url_and_headers()

        full: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json={
                        "model": settings.LLM_MODEL_NAME,
                        "messages": messages,
                        "temperature": settings.LLM_TEMPERATURE_RAG,
                        "max_tokens": settings.RAG_MAX_TOKENS,
                        "stream": True,
                    },
                ) as response:
                    if response.status_code != 200:
                        err_body = (await response.aread()).decode("utf-8", errors="replace")
                        logger.error(
                            "FengShuiRAGService.stream: LLM error %d - %s",
                            response.status_code,
                            err_body[:200],
                        )
                        yield (
                            "final",
                            f"ขออภัยครับ ระบบมีปัญหาชั่วคราว (error {response.status_code})",
                            [],
                        )
                        return

                    async for raw_line in response.aiter_lines():
                        if not raw_line:
                            continue
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            obj = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        choices = obj.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        chunk = delta.get("content")
                        if chunk:
                            full.append(chunk)
                            yield ("delta", chunk, None)
        except Exception as exc:
            import traceback as _tb, os as _os
            _trace = _tb.format_exc()
            try:
                _log_path = _os.path.join(_os.environ.get("TEMP", "C:/temp"), "rag_error.log")
                with open(_log_path, "a", encoding="utf-8") as _ef:
                    _ef.write("[ask_stream ERROR]\n" + _trace + "\n")
            except Exception:
                pass
            yield ("final", f"DEBUG {type(exc).__name__}: {exc}", [])
            return

        yield ("final", "".join(full), source_docs)
