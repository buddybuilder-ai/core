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
                logger.info("FengShuiRAGService: vectorstore loaded from %s", settings.CHROMA_DB_PATH)
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
                print(f"  [RAG] Layer 0 ❌  non-bedroom room: \"{matched_exclude}\" (no bedroom keyword)")
                return False
            print("  [RAG] Layer 0 ✅  exclude keyword found but bedroom keyword also present")

        # Sub-layer 1: exact keyword match (collect all for debug visibility)
        exact_matches = [kw for kw in DOMAIN_KEYWORDS if kw.lower() in q_lower]
        if exact_matches:
            print(f"  [RAG] Layer 1 ✅  exact match: {exact_matches}")
            return True

        # Sub-layer 2: fuzzy match on long keywords
        fuzzy_matches = [kw for kw in DOMAIN_KEYWORDS if len(kw) >= 4 and self._fuzzy_match(q_lower, kw.lower())]
        if fuzzy_matches:
            print(f"  [RAG] Layer 1 ✅  fuzzy match: {fuzzy_matches}")
            return True

        # Sub-layer 3: follow-up question via conversation history
        if conversation_history and len(question) < 15:
            recent = conversation_history[-4:]
            for turn in recent:
                combined = turn.get("content", "").lower()
                for kw in DOMAIN_KEYWORDS:
                    if kw.lower() in combined:
                        print(f"  [RAG] Layer 1 ✅  history context match: \"{kw}\"")
                        return True

        print("  [RAG] Layer 1 ❌  no domain keywords found")
        return False

    # ------------------------------------------------------------------
    # Layer 2: L2 distance similarity check
    # (mirrors ConversationRAGChain._check_relevance Layer 2)
    # ------------------------------------------------------------------

    def _check_relevance(
        self,
        question: str,
        conversation_history: list[dict[str, str]],
    ) -> bool:
        """2-layer relevance check before calling LLM.

        Layer 1: Keyword check (fast — no embedding needed).
        Layer 2: L2 distance against vectorstore (mirrors feng-shui-rag threshold 0.35).

        Returns True if question is in scope, False to skip LLM.
        """
        from src.config.settings import get_settings
        settings = get_settings()
        top_k = settings.RAG_TOP_K

        print(f"\n{'─'*60}")
        print(f"  [RAG] Question: \"{question[:80]}\"")
        print(f"  [RAG] Threshold={self.RELEVANCE_THRESHOLD}  TOP_K={top_k}  Fuzzy≤{self.FUZZY_MATCH_THRESHOLD}")

        # Layer 1
        if not self._has_domain_keywords(question, conversation_history):
            print(f"  [RAG] → BLOCKED (Layer 1 failed)\n{'─'*60}")
            return False

        # Layer 2
        vs = self._ensure_vectorstore()
        if vs is None:
            print("  [RAG] Layer 2 ⚠️  vectorstore unavailable — allowing query")
            return True

        try:
            docs_with_scores = vs.similarity_search_with_score(question, k=top_k)
            if not docs_with_scores:
                print(f"  [RAG] Layer 2 ❌  no documents found\n{'─'*60}")
                return False

            print(f"  [RAG] Layer 2 — L2 Similarity Scores (threshold ≤ {self.RELEVANCE_THRESHOLD}):")
            for i, (doc, score) in enumerate(docs_with_scores, 1):
                status = "✅" if score <= self.RELEVANCE_THRESHOLD else "❌"
                src = doc.metadata.get("source", "?").split("/")[-1]
                preview = doc.page_content[:60].replace("\n", " ")
                print(f"    [{i}] L2={score:.4f} {status}  src={src}")
                print(f"        \"{preview}...\"")

            best_score: float = docs_with_scores[0][1]
            is_relevant = best_score <= self.RELEVANCE_THRESHOLD
            verdict = "✅ PASS → ส่ง LLM" if is_relevant else "❌ BLOCKED"
            print(f"  [RAG] Best={best_score:.4f} → {verdict}")
            print(f"{'─'*60}")
            return is_relevant
        except Exception as exc:
            logger.warning("RAG L2 relevance check failed (%s) — allowing query", exc)
            return True

    # ------------------------------------------------------------------
    # Document retrieval
    # (mirrors step3_vectorstore.py get_retriever + step4b format_documents)
    # ------------------------------------------------------------------

    def _retrieve_context(self, question: str) -> tuple[str, list[dict[str, Any]]]:
        """Retrieve relevant chunks from ChromaDB and format as Thai-labelled context.

        Uses MMR search (same as feng-shui-rag get_retriever search_type="mmr").
        Returns (formatted_context_str, source_docs_list).
        """
        vs = self._ensure_vectorstore()
        if vs is None:
            return "", []

        try:
            retriever = self._retriever
            if retriever is None:
                from src.config.settings import get_settings

                s = get_settings()
                retriever = vs.as_retriever(
                    search_type=s.RAG_SEARCH_TYPE,
                    search_kwargs={"k": s.RAG_TOP_K},
                )

            docs = retriever.invoke(question)

            formatted_parts: list[str] = []
            source_docs: list[dict[str, Any]] = []
            for i, doc in enumerate(docs, 1):
                source = doc.metadata.get("source", "ฐานความรู้")
                content = doc.page_content.strip()
                # Format matches feng-shui-rag format_documents() style
                formatted_parts.append(f"[เอกสาร {i}] (แหล่งที่มา: {source})\n{content}")
                source_docs.append(
                    {"content": content[:400], "metadata": dict(doc.metadata)}
                )

            context = "\n\n---\n\n".join(formatted_parts)
            return context, source_docs

        except Exception as exc:
            logger.warning("FengShuiRAGService retrieval failed: %s", exc)
            return "", []

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
                formatted.append(
                    f"รอบที่ {turn_num}:\nคุณถาม: {human_msg}\nผมตอบ: {ai_msg}"
                )
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
            f"[บทสนทนาก่อนหน้า]\n{history_text}\n\n"
            f"[ข้อมูลอ้างอิง]\n{context_text}\n\n"
            f"[คำถาม]\n{question}"
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
        if not self._check_relevance(question, history):
            logger.info("FengShuiRAGService: out-of-scope → %r", question[:60])
            print("  [RAG] OUT_OF_SCOPE — returning default message")
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
            print(f"  [RAG] Mixed-room detected ({rooms_str}) — injecting constraint into prompt")
        else:
            question_for_llm = question

        # --- Retrieve context from ChromaDB ---
        context, source_docs = self._retrieve_context(question)

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
            print(f"  [RAG] LLM: Ollama ({model})")
        elif provider == "groq":
            url = f"{settings.GROQ_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            print(f"  [RAG] LLM: Groq ({model})")
        else:
            # openrouter หรือ provider อื่น
            url = f"{settings.OPENROUTER_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://buddybuilder.ai",
                "X-Title": "BuddyBuilder AI",
            }
            print(f"  [RAG] LLM: OpenRouter ({model})")

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
