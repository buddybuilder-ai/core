"""Interactive RAG Chat Tester — พิมพ์คำถามเองได้เลย

Usage:
    cd "/Users/suthathongkong/Documents/Buddy Builder/core"
    source .venv/bin/activate
    python test_rag_chat.py

Commands:
    พิมพ์คำถาม → ถาม RAG
    /mode buddy|mentor|fun → เปลี่ยน mode
    /sources → toggle แสดง source documents
    /relevance <คำถาม> → ทดสอบ relevance check อย่างเดียว (ไม่เรียก LLM)
    /retrieve <คำถาม> → ดู documents ที่ดึงมาก่อนส่ง LLM
    /history → ดู conversation history
    /clear → ล้าง history
    /exit → ออก
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


def print_separator(char="─", width=70):
    print(char * width)


def print_header():
    print_separator("═")
    print("  BuddyBuilder RAG Chat Tester")
    print("  พิมพ์คำถามได้เลย | /help สำหรับคำสั่ง | /exit เพื่อออก")
    print_separator("═")


def print_help():
    print("""
คำสั่ง:
  /mode buddy|mentor|fun    เปลี่ยน personality mode
  /sources                  toggle แสดง/ซ่อน source documents
  /debug                    toggle แสดง fuzzy match + similarity scores ทุกคำถาม
  /relevance <คำถาม>         ทดสอบ relevance check (ไม่เรียก LLM)
  /retrieve <คำถาม>          ดู documents ที่จะ inject ก่อนส่ง LLM
  /history                  ดู conversation history ปัจจุบัน
  /clear                    ล้าง conversation history
  /exit                     ออกจากโปรแกรม
""")


async def cmd_relevance(svc, question: str):
    """ทดสอบ 2-layer relevance check"""
    from src.modules.layout.application.services.rag_service import DOMAIN_KEYWORDS

    q_lower = question.lower()
    print(f"\n  Layer 1: Keyword Check")

    matched_kw = [kw for kw in DOMAIN_KEYWORDS if kw.lower() in q_lower]
    has_kw = bool(matched_kw)
    print(f"    {'✅' if has_kw else '❌'} Exact match: {matched_kw[:5] if matched_kw else 'ไม่พบ'}")

    if not has_kw:
        fuzzy_matched = []
        for kw in DOMAIN_KEYWORDS:
            if len(kw) >= 4 and svc._fuzzy_match(q_lower, kw.lower()):
                fuzzy_matched.append(kw)
        print(f"    {'✅' if fuzzy_matched else '❌'} Fuzzy match: {fuzzy_matched[:3] if fuzzy_matched else 'ไม่พบ'}")
        has_kw = bool(fuzzy_matched)

    if not has_kw:
        print(f"    → REJECTED (Layer 1 failed — no domain keywords)")
        return

    print(f"\n  Layer 2: L2 Distance Check")
    vs = svc._ensure_vectorstore()
    if vs is None:
        print(f"    ⚠️  Vectorstore ไม่พร้อม — ข้าม Layer 2")
        return

    try:
        docs = vs.similarity_search_with_score(question, k=3)
        for i, (doc, score) in enumerate(docs, 1):
            threshold = svc.RELEVANCE_THRESHOLD
            status = "✅" if score <= threshold else "❌"
            preview = doc.page_content[:60].replace("\n", " ")
            print(f"    [{i}] L2={score:.4f} (threshold={threshold}) {status}")
            print(f"        {preview}...")

        best_score = docs[0][1] if docs else 999
        is_relevant = best_score <= svc.RELEVANCE_THRESHOLD
        print(f"\n    → {'✅ RELEVANT (จะส่งต่อ LLM)' if is_relevant else '❌ NOT RELEVANT (จะ block)'}")
    except Exception as e:
        print(f"    ⚠️  Error: {e}")


async def cmd_retrieve(svc, question: str):
    """ดู documents ที่จะ inject เข้า LLM"""
    print(f"\n  ดึง documents จาก ChromaDB สำหรับ: \"{question}\"")
    context, source_docs = svc._retrieve_context(question)
    if not source_docs:
        print("  ❌ ไม่พบ documents")
        return
    print(f"  ✅ ดึงได้ {len(source_docs)} documents\n")
    for i, doc in enumerate(source_docs, 1):
        print(f"  ── Document {i} ──")
        content = doc["content"].replace("\n", " ")
        print(f"  {content[:200]}...")
        if doc.get("metadata"):
            src = doc["metadata"].get("source", "?")
            print(f"  source: {src}")
        print()


async def show_debug_panel(svc, question: str, settings):
    """แสดง debug info: fuzzy match + similarity scores + vectorstore path"""
    from src.modules.layout.application.services.rag_service import DOMAIN_KEYWORDS

    print(f"\n  ┌─── Debug ─────────────────────────────────────────────────")

    # Vectorstore location
    import os
    vstore_path = os.path.abspath(settings.CHROMA_DB_PATH)
    print(f"  │ 📁 Vectorstore: {vstore_path}")
    print(f"  │ 📏 Threshold:   L2 ≤ {svc.RELEVANCE_THRESHOLD}  |  TOP_K={settings.RAG_TOP_K}  |  Fuzzy≤{svc.FUZZY_MATCH_THRESHOLD}  |  Temp={settings.LLM_TEMPERATURE_RAG}")

    # Layer 1: keyword + fuzzy
    q_lower = question.lower()
    exact = [kw for kw in DOMAIN_KEYWORDS if kw.lower() in q_lower]
    fuzzy_hits = []
    if not exact:
        for kw in DOMAIN_KEYWORDS:
            if len(kw) >= 4 and svc._fuzzy_match(q_lower, kw.lower()):
                fuzzy_hits.append(kw)

    if exact:
        print(f"  │ 🔑 Layer 1 ✅  exact: {exact[:4]}")
    elif fuzzy_hits:
        print(f"  │ 🔑 Layer 1 ✅  fuzzy: {fuzzy_hits[:4]}")
    else:
        print(f"  │ 🔑 Layer 1 ❌  ไม่พบ keyword")

    # Layer 2: similarity scores for all TOP_K docs
    vs = svc._ensure_vectorstore()
    if vs is not None:
        try:
            docs = vs.similarity_search_with_score(question, k=settings.RAG_TOP_K)
            print(f"  │ 📊 Layer 2 — Similarity Scores (L2 distance):")
            for i, (doc, score) in enumerate(docs, 1):
                ok = score <= svc.RELEVANCE_THRESHOLD
                src = doc.metadata.get("source", "?")
                preview = doc.page_content[:50].replace("\n", " ")
                print(f"  │   [{i}] {'✅' if ok else '❌'} L2={score:.4f}  src={src}")
                print(f"  │       \"{preview}...\"")
            best = docs[0][1] if docs else 999
            verdict = "✅ PASS → ส่ง LLM" if best <= svc.RELEVANCE_THRESHOLD else "❌ FAIL → block"
            print(f"  │ 🏆 Best={best:.4f}  {verdict}")
        except Exception as e:
            print(f"  │ ⚠️  similarity_search error: {e}")
    else:
        print(f"  │ 📊 Layer 2 ⚠️  Vectorstore ไม่พร้อม")

    print(f"  └───────────────────────────────────────────────────────────")


async def main():
    from src.modules.layout.application.services.rag_service import FengShuiRAGService

    print_header()

    # Init service
    print("\n  โหลด FengShuiRAGService...")
    svc = FengShuiRAGService()

    from src.config.settings import get_settings
    settings = get_settings()

    # Warm up vectorstore + show location
    import os
    vs = svc._ensure_vectorstore()
    vstore_path = os.path.abspath(settings.CHROMA_DB_PATH)
    if vs is None:
        print(f"  ⚠️  Vectorstore ไม่พร้อม ({vstore_path})")
    else:
        print(f"  ✅ Vectorstore: {vstore_path}")

    print(f"  📏 Threshold: L2 ≤ {svc.RELEVANCE_THRESHOLD}  |  TOP_K={settings.RAG_TOP_K}  |  Fuzzy≤{svc.FUZZY_MATCH_THRESHOLD}  |  Temp={settings.LLM_TEMPERATURE_RAG}")

    # แสดง LLM ที่ใช้จริง + ตรวจสอบความพร้อม
    if settings.LLM_PROVIDER == "ollama":
        import httpx as _httpx
        try:
            r = _httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=3.0)
            ollama_ok = r.status_code == 200
        except Exception:
            ollama_ok = False
        if ollama_ok:
            print(f"  ✅ LLM: Ollama ({settings.OLLAMA_MODEL_RAG}) — พร้อมใช้งาน")
        else:
            print(f"  ⚠️  LLM: Ollama ({settings.OLLAMA_MODEL_RAG}) — ไม่ได้รัน! ให้รัน: ollama serve")
        has_api_key = ollama_ok
    else:
        has_api_key = bool(settings.OPENROUTER_API_KEY) and "xxxx" not in settings.OPENROUTER_API_KEY
        if has_api_key:
            print(f"  ✅ LLM: OpenRouter ({settings.LLM_MODEL_RAG}) — พร้อมใช้งาน")
        else:
            print(f"  ⚠️  LLM: OpenRouter — ไม่มี OPENROUTER_API_KEY, ถามจริงไม่ได้")

    # State
    mode = "buddy"
    show_sources = False
    show_debug = False
    conversation_history: list[dict] = []

    print(f"\n  Mode: {mode} | Sources: {'on' if show_sources else 'off'} | Debug: {'on' if show_debug else 'off'}")
    print_separator()

    while True:
        try:
            user_input = input(f"\nคุณ [{mode}]: ").strip()
            if not user_input:
                continue

            # --- Commands ---
            if user_input == "/exit":
                print("\n👋 ลาก่อนครับ!")
                break

            elif user_input == "/help":
                print_help()

            elif user_input == "/history":
                if not conversation_history:
                    print("  (ยังไม่มี history)")
                else:
                    print(f"\n  History ({len(conversation_history)//2} รอบ):")
                    for i in range(0, len(conversation_history), 2):
                        u = conversation_history[i].get("content", "")[:80]
                        a = conversation_history[i+1].get("content", "")[:80] if i+1 < len(conversation_history) else ""
                        print(f"  [{i//2+1}] คุณ: {u}")
                        print(f"       AI: {a}...")

            elif user_input == "/clear":
                conversation_history = []
                print("  ✅ ล้าง history แล้ว")

            elif user_input == "/sources":
                show_sources = not show_sources
                print(f"  Sources: {'✅ on' if show_sources else '❌ off'}")

            elif user_input == "/debug":
                show_debug = not show_debug
                print(f"  Debug: {'✅ on (แสดง similarity + fuzzy ทุกคำถาม)' if show_debug else '❌ off'}")

            elif user_input.startswith("/mode "):
                new_mode = user_input[6:].strip()
                if new_mode in ("buddy", "mentor", "fun"):
                    mode = new_mode
                    print(f"  ✅ เปลี่ยนเป็น mode: {mode}")
                else:
                    print("  ❌ mode ต้องเป็น buddy | mentor | fun")

            elif user_input.startswith("/relevance "):
                q = user_input[11:].strip()
                await cmd_relevance(svc, q)

            elif user_input.startswith("/retrieve "):
                q = user_input[10:].strip()
                await cmd_retrieve(svc, q)

            # --- Normal question ---
            else:
                if not has_api_key:
                    if settings.LLM_PROVIDER == "ollama":
                        print(f"  ⚠️  Ollama ไม่ได้รัน — รัน: ollama serve  แล้วลองใหม่")
                    else:
                        print("  ⚠️  ไม่มี OPENROUTER_API_KEY — ใช้ /relevance หรือ /retrieve แทนครับ")
                    continue

                if show_debug:
                    await show_debug_panel(svc, user_input, settings)

                print("  ⏳ กำลังค้นหาและตอบ...")
                answer, source_docs = await svc.ask(
                    question=user_input,
                    mode=mode,
                    conversation_history=conversation_history,
                )

                print(f"\nAI: {answer}")

                if show_sources and source_docs:
                    print(f"\n  ── Sources ({len(source_docs)}) ──")
                    for i, doc in enumerate(source_docs, 1):
                        preview = doc["content"][:100].replace("\n", " ")
                        src = doc.get("metadata", {}).get("source", "?")
                        print(f"  [{i}] {preview}...")
                        print(f"       source: {src}")

                # เก็บ history (max 10 รอบ = 20 entries)
                conversation_history.append({"role": "user", "content": user_input})
                conversation_history.append({"role": "assistant", "content": answer})
                if len(conversation_history) > 20:
                    conversation_history = conversation_history[-20:]

        except KeyboardInterrupt:
            print("\n\n👋 ลาก่อนครับ!")
            break
        except Exception as e:
            print(f"\n  ❌ Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
