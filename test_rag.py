"""Quick RAG integration test — run directly without pytest.

Usage:
    cd "/Users/suthathongkong/Documents/Buddy Builder/core"
    source .venv/bin/activate
    python test_rag.py
"""

import asyncio
import sys
import os

# ให้ Python หา src/ package
sys.path.insert(0, os.path.dirname(__file__))


async def test_relevance_check():
    """ทดสอบ 2-layer relevance check"""
    from src.modules.layout.application.services.rag_service import FengShuiRAGService

    svc = FengShuiRAGService()
    print("\n" + "="*60)
    print("TEST 1: Relevance Check (keyword + L2 distance)")
    print("="*60)

    cases = [
        ("ห้องนอนควรใช้สีอะไรดีครับ", True),
        ("ฮวงจุ้ยโซฟาวางไว้ทิศไหน", True),
        ("วิธีทำ pasta carbonara", False),
        ("ราคาหุ้น ADVANC วันนี้เท่าไหร่", False),
        ("เตียงควรหันหัวไปทางไหน", True),
    ]

    passed = 0
    for question, expected in cases:
        result = svc._check_relevance(question, [])
        status = "✅" if result == expected else "❌"
        print(f"  {status} [{('IN' if result else 'OUT')}] {question}")
        if result == expected:
            passed += 1

    print(f"\n  ผล: {passed}/{len(cases)} passed")
    return passed == len(cases)


async def test_retrieval():
    """ทดสอบ ChromaDB retrieval"""
    from src.modules.layout.application.services.rag_service import FengShuiRAGService

    svc = FengShuiRAGService()
    print("\n" + "="*60)
    print("TEST 2: ChromaDB Retrieval")
    print("="*60)

    vs = svc._ensure_vectorstore()
    if vs is None:
        print("  ❌ ไม่สามารถโหลด vectorstore ได้")
        return False

    context, source_docs = svc._retrieve_context("ห้องนอนควรใช้สีอะไรตามหลักฮวงจุ้ย")
    print(f"  ✅ ดึงได้ {len(source_docs)} documents")
    for i, doc in enumerate(source_docs, 1):
        preview = doc["content"][:80].replace("\n", " ")
        print(f"  [{i}] {preview}...")
    return len(source_docs) > 0


async def test_full_ask():
    """ทดสอบ full RAG pipeline พร้อม LLM"""
    from src.modules.layout.application.services.rag_service import FengShuiRAGService

    svc = FengShuiRAGService()
    print("\n" + "="*60)
    print("TEST 3: Full RAG Ask (เรียก LLM จริง)")
    print("="*60)

    question = "ห้องนอนควรใช้สีอะไรตามหลักฮวงจุ้ย"
    print(f"  คำถาม: {question}")
    print("  ⏳ กำลังถาม...")

    answer, sources = await svc.ask(
        question=question,
        mode="buddy",
        conversation_history=[],
    )

    print(f"\n  คำตอบ:\n{answer}")
    print(f"\n  Sources: {len(sources)} documents")
    return bool(answer) and answer != ""


async def test_out_of_scope():
    """ทดสอบ out-of-scope guard"""
    from src.modules.layout.application.services.rag_service import FengShuiRAGService, OUT_OF_SCOPE_MSG

    svc = FengShuiRAGService()
    print("\n" + "="*60)
    print("TEST 4: Out-of-scope Guard")
    print("="*60)

    answer, sources = await svc.ask(
        question="วิธีทำข้าวผัดกะเพราครับ",
        mode="buddy",
    )
    is_out_of_scope = answer == OUT_OF_SCOPE_MSG
    print(f"  {'✅' if is_out_of_scope else '❌'} คำถามนอก scope → ตอบ out-of-scope message")
    print(f"  ข้อความ: {answer[:80]}")
    return is_out_of_scope


async def test_conversation_history():
    """ทดสอบ conversation history injection"""
    from src.modules.layout.application.services.rag_service import FengShuiRAGService

    svc = FengShuiRAGService()
    print("\n" + "="*60)
    print("TEST 5: Conversation History (follow-up question)")
    print("="*60)

    history = [
        {"role": "user", "content": "ห้องนอนควรใช้สีอะไร"},
        {"role": "assistant", "content": "แนะนำสีน้ำเงินอ่อนหรือสีเขียวอ่อนครับ เหมาะกับการพักผ่อน"},
    ]

    # คำถามสั้น follow-up — ต้องผ่าน keyword check จาก history
    result = svc._has_domain_keywords("แล้วห้องนั่งเล่นล่ะ", history)
    print(f"  {'✅' if result else '❌'} คำถาม follow-up ผ่าน keyword check จาก history")

    history_text = svc._format_chat_history(history)
    has_round = "รอบที่ 1" in history_text
    print(f"  {'✅' if has_round else '❌'} History format ถูกต้อง (มี 'รอบที่ 1')")
    return result and has_round


async def main():
    print("\n🧪 BuddyBuilder RAG Integration Tests")
    print("="*60)

    results = {}

    results["relevance_check"] = await test_relevance_check()
    results["retrieval"] = await test_retrieval()
    results["out_of_scope"] = await test_out_of_scope()
    results["conversation_history"] = await test_conversation_history()

    # Test LLM (optional — ข้ามถ้าไม่มี API key)
    from src.config.settings import get_settings
    settings = get_settings()
    if settings.OPENROUTER_API_KEY and "xxxx" not in settings.OPENROUTER_API_KEY:
        results["full_ask"] = await test_full_ask()
    else:
        print("\n" + "="*60)
        print("TEST 3: Full RAG Ask — ⏭️  SKIPPED (ไม่มี OPENROUTER_API_KEY)")
        print("="*60)
        results["full_ask"] = None

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for name, passed in results.items():
        if passed is None:
            print(f"  ⏭️  {name}: skipped")
        elif passed:
            print(f"  ✅ {name}: passed")
        else:
            print(f"  ❌ {name}: FAILED")

    failed = [k for k, v in results.items() if v is False]
    if failed:
        print(f"\n❌ {len(failed)} test(s) failed: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"\n✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
