"""Feng Shui RAG Service with Conversation Memory.

LLM backend: OpenRouter (matching core's existing infrastructure).
Vectorstore: ChromaDB loaded by vectorstore_service (from feng-shui-rag pipeline).

แก้ SYSTEM_PROMPT, DOMAIN_KEYWORDS, OUT_OF_SCOPE_MSG ที่:
  feng-shui-rag/src/rag_constants.py  ← single source of truth
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _rlog(msg: str) -> None:
    """Write RAG debug line to stderr + /tmp/rag.log for visibility."""
    line = msg + "\n"
    sys.stderr.write(line)
    sys.stderr.flush()
    try:
        with open("/tmp/rag.log", "a", encoding="utf-8") as _f:
            _f.write(line)
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
from rag_constants import DOMAIN_KEYWORDS  # noqa: E402
from rag_constants import EXCLUDE_KEYWORDS  # noqa: E402
from rag_constants import MODE_ADDITIONS as _MODE_ADDITIONS  # noqa: E402
from rag_constants import OUT_OF_SCOPE_MSG  # noqa: E402
from rag_constants import SYSTEM_PROMPT as _SYSTEM_PROMPT_BASE  # noqa: E402

# ---------------------------------------------------------------------------
# Quick keyword sets for query-type pre-classification (no LLM needed)
# ---------------------------------------------------------------------------
_FENG_SHUI_TERMS: frozenset[str] = frozenset([
    "ฮวงจุ้ย", "feng shui", "fengshui", "กัว", "ming gua", "minggua",
    "ทิศมงคล", "ทิศหัวนอน", "ทิศนอน", "ทิศเสีย", "ทิศอัปมงคล",
    "ชี", "chi", "ธาตุ", "ห้าธาตุ", "เลขกัว", "กัวบุคคล", "กัวคน",
    "พลังงานฮวงจุ้ย", "มิงกัว",
])
_INTERIOR_TERMS: frozenset[str] = frozenset([
    "ตกแต่ง", "interior", "เฟอร์นิเจอร์", "furniture", "สีผนัง",
    "แสงสว่าง", "lighting", "วอลเปเปอร์", "wallpaper", "ออกแบบ",
    "design", "decor", "โทนสี", "ทาสี", "วัสดุ", "material",
])


class FengShuiRAGService:
    """RAG service implementing feng-shui-rag's ConversationRAGChain principles.

    Designed to be used in the chat "question" intent path, replacing raw LLM calls
    with a full RAG pipeline that includes:

    - Layer 1 relevance: domain keyword matching + fuzzy match (same as feng-shui-rag)
    - Layer 2 relevance: ChromaDB L2 distance threshold (0.35, same as feng-shui-rag)
    - Document retrieval: MMR search via ChromaDB (from feng-shui-rag vectorstore)
    - Conversation history: formatted and injected into prompt (same format as feng-shui-rag)
    - LLM: OpenRouter (adapts to core's infrastructure instead of Ollama/Claude direct)
    """

    # Fuzzy match tolerance — identical to feng-shui-rag config FUZZY_MATCH_THRESHOLD
    FUZZY_MATCH_THRESHOLD: int = 3

    def __init__(self) -> None:
        self._vectorstore: Any = None
        self._retriever: Any = None
        from src.config.settings import get_settings

        s = get_settings()
        # อ่านจาก RAG_RELEVANCE_THRESHOLD ใน .env (default 1.0 = รับทุกคำถามใน domain)
        self.RELEVANCE_THRESHOLD: float = s.RAG_RELEVANCE_THRESHOLD

    # ------------------------------------------------------------------
    # Vectorstore (lazy-loaded, same singleton pattern as vectorstore_service.py)
    # ------------------------------------------------------------------

    def _ensure_vectorstore(self) -> Any:
        """Lazy-load the ChromaDB vectorstore built by feng-shui-rag pipeline."""
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
    # Layer 1: Domain keyword check + fuzzy match
    # (mirrors ConversationRAGChain._has_domain_keywords)
    # ------------------------------------------------------------------

    def _fuzzy_match(self, text: str, keyword: str) -> bool:
        """Character-level fuzzy matching for typo tolerance.

        Same algorithm as feng-shui-rag step4b_rag_with_memory.py _fuzzy_match().
        Checks each word in text against keyword; allows up to FUZZY_MATCH_THRESHOLD
        character differences.
        """
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
        """Layer 1 relevance: domain keywords + fuzzy match + conversation context.

        Sub-layer 0: Exclude non-bedroom rooms — block ถ้าคำถามมีห้องอื่น และไม่มี bedroom keyword
        Sub-layer 1: Exact keyword match in question
        Sub-layer 2: Fuzzy match for long keywords (>= 4 chars)
        Sub-layer 3: History context for short follow-up questions (< 15 chars)
        """
        q_lower = question.lower()

        # Sub-layer 0: block ห้องอื่นที่ไม่ใช่ห้องนอน
        has_exclude = any(kw.lower() in q_lower for kw in EXCLUDE_KEYWORDS)
        if has_exclude:
            has_bedroom = any(kw.lower() in q_lower for kw in BEDROOM_KEYWORDS)
            if not has_bedroom:
                matched_exclude = next(kw for kw in EXCLUDE_KEYWORDS if kw.lower() in q_lower)
                _rlog(f'  [RAG] Layer 0 ❌  non-bedroom room: "{matched_exclude}" (no bedroom keyword)')
                return False
            _rlog("  [RAG] Layer 0 ✅  exclude keyword found but bedroom keyword also present")

        # Sub-layer 1: exact keyword match (collect all for debug visibility)
        exact_matches = [kw for kw in DOMAIN_KEYWORDS if kw.lower() in q_lower]
        if exact_matches:
            _rlog(f"  [RAG] Layer 1 ✅  exact match: {exact_matches}")
            return True

        # Sub-layer 2: fuzzy match on long keywords
        fuzzy_matches = [
            kw for kw in DOMAIN_KEYWORDS if len(kw) >= 4 and self._fuzzy_match(q_lower, kw.lower())
        ]
        if fuzzy_matches:
            _rlog(f"  [RAG] Layer 1 ✅  fuzzy match: {fuzzy_matches}")
            return True

        # Sub-layer 3: follow-up question via conversation history
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
    # Layer 2: L2 distance similarity check
    # (mirrors ConversationRAGChain._check_relevance Layer 2)
    # ------------------------------------------------------------------

    def _check_relevance(
        self,
        question: str,
        conversation_history: list[dict[str, str]],
    ) -> tuple[bool, list[Any]]:
        """2-layer relevance check before calling LLM.

        Layer 1: Keyword check (fast — no embedding needed).
        Layer 2: L2 distance against vectorstore (mirrors feng-shui-rag threshold 0.35).

        Returns (is_relevant, prefetched_docs) — prefetched_docs reuses the embedding
        call from Layer 2 so ask() skips a second embed round-trip.
        On Layer 1 failure or vectorstore unavailability, prefetched_docs is [].
        """
        from src.config.settings import get_settings

        settings = get_settings()
        top_k = settings.RAG_TOP_K

        _rlog(f"\n{'─' * 60}")
        _rlog(f'  [RAG] Question: "{question[:80]}"')
        _rlog(f"  [RAG] Threshold={self.RELEVANCE_THRESHOLD}  TOP_K={top_k}  Fuzzy≤{self.FUZZY_MATCH_THRESHOLD}")

        # Layer 1
        if not self._has_domain_keywords(question, conversation_history):
            _rlog(f"  [RAG] → BLOCKED (Layer 1 failed)\n{'─' * 60}")
            return False, []

        # Layer 2
        vs = self._ensure_vectorstore()
        if vs is None:
            _rlog("  [RAG] Layer 2 ⚠️  vectorstore unavailable — allowing query")
            return True, []

        try:
            docs_with_scores = vs.similarity_search_with_score(question, k=top_k)
            if not docs_with_scores:
                _rlog(f"  [RAG] Layer 2 ❌  no documents found\n{'─' * 60}")
                return False, []

            _rlog(f"  [RAG] Layer 2 — L2 Similarity Scores (threshold ≤ {self.RELEVANCE_THRESHOLD}):")
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
            # Return the already-fetched docs to avoid a second embedding call in ask()
            prefetched = [doc for doc, _ in docs_with_scores]
            return is_relevant, prefetched
        except Exception as exc:
            logger.warning("RAG L2 relevance check failed (%s) — allowing query", exc)
            _rlog(f"  [RAG] Layer 2 ⚠️  similarity search failed: {exc}")
            _rlog(f"{'─' * 60}")
            return True, []

    # ------------------------------------------------------------------
    # Query-type classifier: feng_shui / interior_design / both
    # Uses keyword check first; falls back to LLM_MODEL_ROUTER if ambiguous.
    # ------------------------------------------------------------------

    async def _classify_query(self, question: str) -> str:
        """Classify the user question as 'feng_shui', 'interior_design', or 'both'.

        Step 1: Fast keyword check — no LLM call needed for clear cases.
        Step 2: Call LLM_MODEL_ROUTER (gpt-4o-mini) for ambiguous questions.
        Returns 'both' on any error so retrieval is never blocked.
        """
        q = question.lower()
        has_fs = any(kw in q for kw in _FENG_SHUI_TERMS)
        has_id = any(kw in q for kw in _INTERIOR_TERMS)

        if has_fs and not has_id:
            _rlog(f"  [RAG] QueryType: feng_shui (keyword)")
            return "feng_shui"
        if has_id and not has_fs:
            _rlog(f"  [RAG] QueryType: interior_design (keyword)")
            return "interior_design"

        # Ambiguous — call LLM_MODEL_ROUTER for a fast 1-token answer
        try:
            import httpx

            from src.config.settings import get_settings

            s = get_settings()
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    f"{s.OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {s.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://buddybuilder.ai",
                        "X-Title": "BuddyBuilder AI",
                    },
                    json={
                        "model": s.LLM_MODEL_ROUTER,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "จำแนกคำถามต่อไปนี้ว่าเกี่ยวกับอะไรมากที่สุด "
                                    "ตอบเพียง 1 คำ: feng_shui, interior_design, หรือ both"
                                ),
                            },
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
                    else:
                        kt = "both"
                    _rlog(f"  [RAG] QueryType: {kt} (LLM)")
                    return kt
        except Exception as exc:
            _rlog(f"  [RAG] QueryType LLM failed ({exc}) → both")

        _rlog("  [RAG] QueryType: both (fallback)")
        return "both"

    # ------------------------------------------------------------------
    # Document retrieval
    # (mirrors step3_vectorstore.py get_retriever + step4b format_documents)
    # ------------------------------------------------------------------

    def _retrieve_context(
        self,
        question: str,
        prefetched_docs: list[Any] | None = None,
        knowledge_type: str = "both",
    ) -> tuple[str, list[dict[str, Any]]]:
        """Retrieve relevant chunks from ChromaDB and format as Thai-labelled context.

        knowledge_type filter: when not 'both', adds a ChromaDB metadata filter so
        only chunks labelled feng_shui/interior_design/both are returned.
        prefetched_docs (from Layer 2 check) are reused only when knowledge_type=='both'
        to avoid returning unfiltered results.
        Returns (formatted_context_str, source_docs_list).
        """
        # Reuse prefetched docs only when no filter is needed
        if prefetched_docs and knowledge_type == "both":
            docs = prefetched_docs
        else:
            vs = self._ensure_vectorstore()
            if vs is None:
                return "", []

            try:
                from src.config.settings import get_settings

                s = get_settings()
                meta_filter = (
                    {"knowledge_type": {"$in": [knowledge_type, "both"]}}
                    if knowledge_type != "both"
                    else None
                )
                if meta_filter:
                    _rlog(f"  [RAG] Retrieval filter: knowledge_type ∈ [{knowledge_type}, both]")
                search_kwargs: dict[str, Any] = {"k": s.RAG_TOP_K}
                if meta_filter:
                    search_kwargs["filter"] = meta_filter

                retriever = vs.as_retriever(
                    search_type=s.RAG_SEARCH_TYPE,
                    search_kwargs=search_kwargs,
                )
                docs = retriever.invoke(question)

                # Fallback: if filter returned nothing, retry without filter
                if not docs and meta_filter:
                    _rlog("  [RAG] Filter returned 0 docs → retrying without filter")
                    docs = vs.as_retriever(
                        search_type=s.RAG_SEARCH_TYPE,
                        search_kwargs={"k": s.RAG_TOP_K},
                    ).invoke(question)
            except Exception as exc:
                logger.warning("FengShuiRAGService retrieval failed: %s", exc)
                return "", []

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

        context = "\n\n---\n\n".join(formatted_parts)
        return context, source_docs

    # ------------------------------------------------------------------
    # Prompt building
    # (mirrors ConversationRAGChain prompt template structure)
    # ------------------------------------------------------------------

    def _format_chat_history(self, conversation_history: list[dict[str, str]]) -> str:
        """Format conversation history for LLM prompt.

        Mirrors feng-shui-rag format_chat_history() — pairs user/assistant turns
        as numbered rounds ("รอบที่ N").
        """
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
    ) -> list[dict[str, str]]:
        """Build messages array for OpenRouter API.

        Prompt structure mirrors ConversationRAGChain.prompt:
        - System: SYSTEM_PROMPT + mode addition
        - Human: chat_history + context + question (same sections as feng-shui-rag)
        """
        mode_addition = _MODE_ADDITIONS.get(mode, _MODE_ADDITIONS["buddy"])
        system_content = f"{_SYSTEM_PROMPT_BASE}\n\n{mode_addition}"

        history_text = self._format_chat_history(conversation_history)
        context_text = context if context else "[ไม่มีข้อมูลเพิ่มเติมจากฐานความรู้]"

        user_content = (
            f"[บทสนทนาก่อนหน้า]\n{history_text}\n\n[ข้อมูลอ้างอิง]\n{context_text}\n\n[คำถาม]\n{question}"
        )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ask(
        self,
        question: str,
        mode: str = "buddy",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Answer a feng shui / design question using RAG with conversation memory.

        Implements the full ConversationRAGChain.invoke() flow:
        1. 2-layer relevance check (keywords + L2 distance) — returns OUT_OF_SCOPE_MSG if fail
        2. ChromaDB retrieval (MMR, k=RAG_TOP_K)
        3. Prompt construction (history + context + question)
        4. LLM call via OpenRouter

        Args:
            question: User's question text.
            mode: Personality mode — "buddy" | "mentor" | "fun".
            conversation_history: Previous turns [{role, content}, ...] from the request.
                This mirrors the stateless approach: history is passed by the client
                (same conversation_history field in ChatStreamRequest).

        Returns:
            (answer_str, source_documents_list) — source_docs match ChatResponse.source_documents schema.
        """
        history = conversation_history or []

        # --- Relevance guard (mirrors ConversationRAGChain._check_relevance) ---
        # _check_relevance now returns (is_relevant, prefetched_docs) so we can
        # reuse the Layer-2 embedding result instead of embedding the query twice.
        is_relevant, prefetched_docs = self._check_relevance(question, history)
        if not is_relevant:
            logger.info("FengShuiRAGService: out-of-scope → %r", question[:60])
            _rlog("  [RAG] OUT_OF_SCOPE — returning default message")
            return OUT_OF_SCOPE_MSG, []

        # --- Detect mixed-room question: inject hard constraint into user message ---
        q_lower = question.lower()
        excluded_rooms = [kw for kw in EXCLUDE_KEYWORDS if kw.lower() in q_lower]
        has_bedroom = any(kw.lower() in q_lower for kw in BEDROOM_KEYWORDS)
        if excluded_rooms and has_bedroom:
            rooms_str = ", ".join(excluded_rooms[:3])
            question_for_llm = (
                f"[ระบบ: คำถามนี้พูดถึง {rooms_str} ซึ่งอยู่นอก scope — "
                f"ห้ามตอบส่วน {rooms_str} เด็ดขาด ตอบเฉพาะห้องนอนเท่านั้น]\n{question}"
            )
            _rlog(f"  [RAG] Mixed-room detected ({rooms_str}) — injecting constraint into prompt")
        else:
            question_for_llm = question

        # --- Classify query type then retrieve filtered context ---
        knowledge_type = await self._classify_query(question)
        context, source_docs = self._retrieve_context(
            question, prefetched_docs=prefetched_docs or None, knowledge_type=knowledge_type
        )

        # --- Build prompt messages ---
        messages = self._build_messages(question_for_llm, context, history, mode)

        # --- Call LLM (OpenRouter or Ollama depending on LLM_PROVIDER) ---
        import httpx

        from src.config.settings import get_settings

        settings = get_settings()

        provider = settings.LLM_PROVIDER
        model = settings.LLM_MODEL_NAME

        if provider == "ollama":
            url = f"{settings.OLLAMA_BASE_URL}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
            provider_label = f"Ollama ({model})"
        elif provider == "groq":
            url = f"{settings.GROQ_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            provider_label = f"Groq ({model})"
        else:
            url = f"{settings.OPENROUTER_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://buddybuilder.ai",
                "X-Title": "BuddyBuilder AI",
            }
            provider_label = f"OpenRouter ({model})"

        _rlog(
            f"\n  ┌─ RAG → LLM Call ───────────────────────────────────\n"
            f"  │  Model      : {provider_label}\n"
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
                        "model": model,
                        "messages": messages,
                        "temperature": settings.LLM_TEMPERATURE_RAG,
                        "max_tokens": 1200,
                    },
                    timeout=60.0,
                )
                if response.status_code == 200:
                    answer = str(response.json()["choices"][0]["message"]["content"])
                    logger.debug("FengShuiRAGService: answered %d chars", len(answer))
                    return answer, source_docs
                logger.error(
                    "FengShuiRAGService: LLM error %d — %s",
                    response.status_code,
                    response.text[:200],
                )
                return (
                    f"ขออภัยครับ ระบบมีปัญหาชั่วคราว (error {response.status_code})",
                    [],
                )
        except Exception as exc:
            logger.exception("FengShuiRAGService.ask failed")
            return f"ขออภัยครับ เกิดข้อผิดพลาด: {exc}", []

    async def ask_stream(
        self,
        question: str,
        mode: str = "buddy",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> "AsyncIterator[tuple[str, str, list[dict[str, Any]] | None]]":
        """Streaming variant of `ask` — yields ("delta"|"final", text, sources|None).

        Mirrors `ask()` exactly through relevance, retrieval, and prompt building,
        but switches the LLM call to SSE streaming. Yields:
          - ("delta",  token_chunk, None) repeatedly as chunks arrive
          - ("final",  full_answer,  source_docs) once at the end

        If relevance fails, yields a single ("final", OUT_OF_SCOPE_MSG, []).
        """
        import json

        import httpx

        from src.config.settings import get_settings

        history = conversation_history or []

        is_relevant, prefetched_docs = self._check_relevance(question, history)
        if not is_relevant:
            logger.info("FengShuiRAGService: out-of-scope (stream) → %r", question[:60])
            yield ("final", OUT_OF_SCOPE_MSG, [])
            return

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

        knowledge_type = await self._classify_query(question)
        context, source_docs = self._retrieve_context(
            question, prefetched_docs=prefetched_docs or None, knowledge_type=knowledge_type
        )
        messages = self._build_messages(question_for_llm, context, history, mode)

        settings = get_settings()
        provider = settings.LLM_PROVIDER
        model = settings.LLM_MODEL_NAME

        if provider == "ollama":
            url = f"{settings.OLLAMA_BASE_URL}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
        elif provider == "groq":
            url = f"{settings.GROQ_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
        else:
            url = f"{settings.OPENROUTER_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://buddybuilder.ai",
                "X-Title": "BuddyBuilder AI",
            }

        full: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": settings.LLM_TEMPERATURE_RAG,
                        "max_tokens": 1200,
                        "stream": True,
                    },
                ) as response:
                    if response.status_code != 200:
                        err_body = (await response.aread()).decode("utf-8", errors="replace")
                        logger.error(
                            "FengShuiRAGService.stream: LLM error %d — %s",
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
            logger.exception("FengShuiRAGService.ask_stream failed")
            yield ("final", f"ขออภัยครับ เกิดข้อผิดพลาด: {exc}", [])
            return

        yield ("final", "".join(full), source_docs)
