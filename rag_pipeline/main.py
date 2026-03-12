"""
 RAG: Interior Design + ฮวงจุ้ย (Advanced Version)
Entry Point สำหรับ Advanced RAG techniques
"""
import sys
import argparse
from pathlib import Path

# เพิ่ม rag_pipeline/ เข้า path (scripts อยู่ที่นี่โดยตรง)
sys.path.insert(0, str(Path(__file__).parent))

from step1_data_loader import load_all_documents
from step2b_contextual_chunking import split_documents_with_context
from step2c_hypothetical_questions import create_qa_chunks
from step3_vectorstore import create_vectorstore, get_retriever
from step4b_rag_with_memory import ConversationRAGChain, ask_question


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description=" RAG: Interior Design + ฮวงจุ้ย")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild vector store")
    parser.add_argument("--test", action="store_true", help="ทดสอบด้วยคำถามตัวอย่าง")
    parser.add_argument("--method", choices=["standard", "contextual", "questions"],
                       default="standard", help="วิธี chunking (default: standard, ลอง contextual สำหรับผลลัพธ์ดีกว่า)")
    parser.add_argument("--llm-context", action="store_true",
                       help="ใช้ LLM เพิ่ม context (ช้ากว่า แต่ดีกว่า)")
    args = parser.parse_args()

    print("="*80)
    print(" RAG: Interior Design + ฮวงจุ้ย")
    print(f"   Method: {args.method.upper()}")
    if args.method == "standard":
        print("    Tip: ใช้ --method contextual สำหรับผลลัพธ์ดีกว่า")
    print("="*80 + "\n")

    # ตรวจสอบว่า vector store มีอยู่แล้วหรือไม่
    import os
    chroma_path = os.getenv("CHROMA_DB_PATH", "./vectorstore/chroma_db")
    vector_store_exists = Path(chroma_path).exists()

    # ถ้า vector store ไม่มี หรือ rebuild ให้โหลดเอกสาร
    if not vector_store_exists or args.rebuild:
        # Step 1: โหลดเอกสาร
        print(" Step 1: โหลดเอกสารจาก data/raw/")
        docs = load_all_documents()

        if not docs:
            print("\n ไม่พบเอกสารในระบบ!")
            print(" กรุณาวางไฟล์ (.pdf, .csv, .xlsx, .txt, .md, .json, .jsonl) ใน data/raw/")
            return

        # Step 2: แบ่ง chunks (ใช้วิธีที่เลือก)
        print(f"\n  Step 2: แบ่งเอกสารเป็น chunks ({args.method})")

        if args.method == "standard":
            from step2_text_splitter import split_documents
            chunks = split_documents(docs)

        elif args.method == "contextual":
            chunks = split_documents_with_context(docs, use_llm_context=args.llm_context)

        elif args.method == "questions":
            chunks = create_qa_chunks(docs, questions_per_chunk=3)

        # Step 3: สร้าง vectorstore
        print(f"\n  Step 3: {'Rebuild' if args.rebuild else 'สร้าง'} Vector Store")
        vectorstore = create_vectorstore(chunks, force_rebuild=args.rebuild)
    else:
        # โหลด vector store ที่มีอยู่แล้ว
        print("  โหลด Vector Store ที่มีอยู่แล้ว...")
        print(f"   Path: {chroma_path}")
        print(f"    Tip: ใช้ --rebuild เพื่อสร้างใหม่ด้วย advanced method")
        vectorstore = create_vectorstore([], force_rebuild=False)

    retriever = get_retriever(vectorstore, k=3, search_type="mmr")

    # Step 4: สร้าง RAG chain (with Conversation Memory)
    print("\n Step 4: สร้าง RAG Chain")
    rag_chain = ConversationRAGChain(retriever, max_history=10)

    print("\n" + "="*80)

    # โหมดทดสอบ
    if args.test:
        print(" โหมดทดสอบ - คำถามตัวอย่าง")
        print("="*80 + "\n")

        test_questions = [
            "ฮวงจุ้ยในห้องนอนควรเป็นอย่างไร?",
            "สีอะไรเหมาะกับห้องนั่งเล่น?",
            "การจัดวางโต๊ะทำงานตามหลักฮวงจุ้ย",
        ]

        for q in test_questions:
            ask_question(rag_chain, q)
            print("\n" + "="*80 + "\n")

        return

    # โหมด Interactive Chat
    print(" โหมด Chat - พิมพ์คำถามของคุณ")
    print("   พิมพ์ 'clear' เพื่อล้างประวัติการสนทนา")
    print("   พิมพ์ 'exit' เพื่อออก")
    print("="*80 + "\n")

    while True:
        try:
            question = input("คุณ: ").strip()

            if not question:
                continue

            if question.lower() in ["exit", "quit", "bye", "ออก"]:
                print("\n👋 ขอบคุณที่ใช้งาน!")
                break

            # ล้างประวัติการสนทนา
            if question.lower() == "clear":
                rag_chain.clear_history()
                continue

            answer = ask_question(rag_chain, question)
            print()

        except KeyboardInterrupt:
            print("\n\n👋 ขอบคุณที่ใช้งาน!")
            break
        except Exception as e:
            print(f"\n เกิดข้อผิดพลาด: {e}\n")


if __name__ == "__main__":
    main()
