"""
RAG Vectorstore Builder — Rebuild Entry Point

ไฟล์นี้ใช้สำหรับ rebuild vectorstore เท่านั้น
สำหรับทดสอบ RAG แบบ interactive ให้ใช้:
  cd .. && python test_rag_chat.py   (หรือ make rag-test-chat)
"""
import sys
import argparse
from pathlib import Path

# เพิ่ม rag_pipeline/ เข้า path (scripts อยู่ที่นี่โดยตรง)
sys.path.insert(0, str(Path(__file__).parent))

from step1_data_loader import load_all_documents
from step2b_contextual_chunking import split_documents_with_context
from step2c_hypothetical_questions import create_qa_chunks
from step3_vectorstore import create_vectorstore


def main():
    """Rebuild vectorstore และแสดงคำแนะนำสำหรับ interactive testing"""
    parser = argparse.ArgumentParser(description="RAG Vectorstore Builder")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild vector store")
    parser.add_argument("--method", choices=["standard", "contextual", "questions"],
                       default="contextual", help="วิธี chunking (default: contextual)")
    parser.add_argument("--llm-context", action="store_true",
                       help="ใช้ LLM เพิ่ม context (ช้ากว่า แต่ดีกว่า — ต้องมี Ollama)")
    args = parser.parse_args()

    print("="*80)
    print(" RAG Vectorstore Builder")
    print(f"   Method: {args.method.upper()}")
    print("="*80 + "\n")

    import os
    chroma_path = os.getenv("CHROMA_DB_PATH", "./vectorstore/chroma_db")
    vector_store_exists = Path(chroma_path).exists()

    if not vector_store_exists or args.rebuild:
        # Step 1: โหลดเอกสาร
        print(" Step 1: โหลดเอกสารจาก data/raw/")
        docs = load_all_documents()

        if not docs:
            print("\n ไม่พบเอกสารในระบบ!")
            print(" กรุณาวางไฟล์ (.pdf, .csv, .xlsx, .txt, .md, .json, .jsonl) ใน data/raw/")
            return

        # Step 2: แบ่ง chunks
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
        create_vectorstore(chunks, force_rebuild=args.rebuild)

    else:
        print(f"  Vectorstore มีอยู่แล้ว: {chroma_path}")
        print(f"  ใช้ --rebuild เพื่อสร้างใหม่")

    print("\n" + "="*80)
    print(" เสร็จแล้ว! สำหรับ interactive testing ให้รัน:")
    print("   cd .. && python test_rag_chat.py")
    print("   หรือ: make rag-test-chat")
    print("="*80)


if __name__ == "__main__":
    main()
