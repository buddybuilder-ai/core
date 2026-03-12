"""
 ตรวจสอบ Vector Database (ChromaDB)
แสดงข้อมูลใน VectorDB: จำนวน documents, collections, ตัวอย่างข้อมูล
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# โหลด environment variables
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from step3_vectorstore import get_embeddings
from langchain_community.vectorstores import Chroma


def check_vectordb():
    """ตรวจสอบข้อมูลใน VectorDB"""

    _default = str(Path(__file__).parent / "vectorstore" / "chroma_db")
    chroma_path = os.getenv("CHROMA_DB_PATH", _default)

    print("="*80)
    print(" ตรวจสอบ Vector Database")
    print("="*80 + "\n")

    # ตรวจสอบว่า VectorDB มีอยู่หรือไม่
    if not Path(chroma_path).exists():
        print(" ไม่พบ Vector Database!")
        print(f"   Path: {chroma_path}")
        print("\n กรุณารัน: python main.py เพื่อสร้าง VectorDB ก่อน")
        return

    print(f" พบ Vector Database")
    print(f"   Path: {chroma_path}\n")

    try:
        # โหลด VectorDB
        print(" กำลังโหลด VectorDB...")
        embeddings = get_embeddings()
        vectorstore = Chroma(
            persist_directory=chroma_path,
            embedding_function=embeddings
        )

        # ดึงข้อมูล collection
        collection = vectorstore._collection

        # จำนวน documents
        count = collection.count()
        print(f" จำนวน Documents: {count:,}")

        if count == 0:
            print("\n  VectorDB ว่างเปล่า!")
            print(" กรุณารัน: python main.py --rebuild เพื่อเพิ่มข้อมูล")
            return

        # ดึงข้อมูลทั้งหมด (limit 10 ตัวอย่าง)
        print("\n ตัวอย่าง Documents (10 รายการแรก):")
        print("-" * 80)

        results = collection.get(
            limit=10,
            include=["documents", "metadatas"]
        )

        for i, (doc, metadata) in enumerate(zip(results['documents'], results['metadatas']), 1):
            source = metadata.get('source', 'Unknown')
            preview = doc[:150] + "..." if len(doc) > 150 else doc

            print(f"\n[{i}] Source: {source}")
            print(f"    Content: {preview}")

        # สรุปแหล่งที่มา
        print("\n" + "="*80)
        print(" สรุปแหล่งที่มา:")
        print("-" * 80)

        all_results = collection.get(include=["metadatas"])
        sources = {}

        for metadata in all_results['metadatas']:
            source = metadata.get('source', 'Unknown')
            sources[source] = sources.get(source, 0) + 1

        for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
            print(f"  • {Path(source).name}: {count:,} chunks")

        print("\n" + "="*80)

        # ทดสอบค้นหา
        print("\n ทดสอบการค้นหา:")
        print("-" * 80)

        test_query = input("\nพิมพ์คำที่ต้องการค้นหา (Enter = ข้าม): ").strip()

        if test_query:
            print(f"\n ค้นหา: '{test_query}'")
            results = vectorstore.similarity_search(test_query, k=3)

            print(f" พบ {len(results)} ผลลัพธ์:\n")

            for i, doc in enumerate(results, 1):
                source = doc.metadata.get('source', 'Unknown')
                content = doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content

                print(f"[{i}] Source: {source}")
                print(f"    Content: {content}\n")

        print("="*80)
        print(" ตรวจสอบเสร็จสิ้น!")

    except Exception as e:
        print(f"\n เกิดข้อผิดพลาด: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_vectordb()
