"""
RAG Vectorstore Builder — Rebuild Entry Point

ไฟล์นี้ใช้สำหรับ rebuild vectorstore เท่านั้น
สำหรับทดสอบ RAG แบบ interactive ให้ใช้:
  cd .. && python test_rag_chat.py   (หรือ make rag-test-chat)
"""
import sys
import argparse
from pathlib import Path

# Patch importlib.metadata before any heavy imports.
# transformers calls packages_distributions() at import time; on macOS with
# miniconda some package metadata files are unreadable → OSError [Errno 89].
# transformers calls packages_distributions() at import time.
# On macOS+miniconda this crashes with OSError [Errno 89] on some metadata files.
# Fix: build the mapping cheaply using find_spec (no actual import) so
# transformers can check package availability without importing torch/tf/etc.
import importlib.metadata as _im
import importlib.util as _ilu
_heavy = ["torch", "tensorflow", "jax", "flax", "tokenizers", "sentencepiece",
          "accelerate", "peft", "safetensors", "transformers", "sentence_transformers"]
_pkg_map = {p: [p] for p in _heavy if _ilu.find_spec(p) is not None}
_im.packages_distributions = lambda: _pkg_map

# print ก่อน import อื่นๆ เพื่อให้รู้ว่า process เริ่มทำงานแล้ว
print("RAG Pipeline กำลังเริ่มต้น...", flush=True)

sys.path.insert(0, str(Path(__file__).parent))

print("  [1/3] โหลด pandas + data loader...", end="", flush=True)
from step1_data_loader import load_all_documents
print(" ✓", flush=True)

print("  [2/3] โหลด LangChain + text splitter...", end="", flush=True)
from step2b_contextual_chunking import export_chunks_to_csv, split_documents_with_context
print(" ✓", flush=True)

print("  [3/3] โหลด vectorstore (torch อาจช้า)...", end="", flush=True)
from step3_vectorstore import create_vectorstore
print(" ✓\n", flush=True)


def main():
    """Rebuild vectorstore และแสดงคำแนะนำสำหรับ interactive testing"""
    parser = argparse.ArgumentParser(description="RAG Vectorstore Builder")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild vector store")
    parser.add_argument("--method", choices=["standard", "contextual"],
                       default="contextual", help="วิธี chunking (default: contextual)")
    parser.add_argument("--llm-context", action="store_true",
                       help="ใช้ LLM เพิ่ม context (ช้ากว่า แต่ดีกว่า)")
    args = parser.parse_args()

    print("=" * 80, flush=True)
    print(f"  RAG Vectorstore Builder  |  method={args.method.upper()}  |  llm-context={args.llm_context}", flush=True)
    print("=" * 80 + "\n", flush=True)

    import os
    chroma_path = os.getenv("CHROMA_DB_PATH", "./vectorstore/chroma_db")
    vector_store_exists = Path(chroma_path).exists()

    if not vector_store_exists or args.rebuild:
        # Step 1
        print("[ Step 1 ] โหลดเอกสารจาก data/raw/", flush=True)
        docs = load_all_documents()

        if not docs:
            print("\nไม่พบเอกสารในระบบ!")
            print("กรุณาวางไฟล์ (.pdf, .csv, .xlsx, .txt, .md, .json, .jsonl) ใน data/raw/")
            return

        print(f"  โหลดเสร็จ: {len(docs)} documents\n", flush=True)

        # Step 2
        print(f"[ Step 2 ] Chunking  method={args.method}  llm-context={args.llm_context}", flush=True)

        if args.method == "standard":
            from step2_text_splitter import split_documents
            chunks = split_documents(docs)
            export_chunks_to_csv(chunks)
        elif args.method == "contextual":
            chunks = split_documents_with_context(docs, use_llm_context=args.llm_context)

        print(f"\n[ Step 3 ] {'Rebuild' if args.rebuild else 'สร้าง'} Vector Store  ({len(chunks)} chunks)", flush=True)
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
