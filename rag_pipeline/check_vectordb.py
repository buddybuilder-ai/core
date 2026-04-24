"""
 ตรวจสอบ Vector Database (ChromaDB)
แสดงข้อมูลใน VectorDB: จำนวน documents, collections, ตัวอย่างข้อมูล, สถิติ chunk sizes
Export ได้เป็น CSV และ JSON
"""
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from step3_vectorstore import get_embeddings
from langchain_community.vectorstores import Chroma


def print_separator(char="=", width=80):
    print(char * width)


def export_to_csv(all_docs: list, all_metas: list, output_path: Path) -> None:
    """Export chunks ทั้งหมดเป็น CSV เพื่อตรวจสอบเนื้อหาใน Excel

    columns: chunk_index, source (ชื่อไฟล์), knowledge_type, has_llm_context, size_chars, content
    ใช้ encoding utf-8-sig เพื่อให้ Excel เปิดภาษาไทยได้ถูกต้อง
    """
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["chunk_index", "source", "knowledge_type", "has_llm_context", "size_chars", "content"])
        for i, (doc, meta) in enumerate(zip(all_docs, all_metas)):
            src = Path(meta.get("source", "Unknown")).name
            kt = meta.get("knowledge_type", "")
            has_llm = meta.get("has_llm_context", "")
            writer.writerow([i + 1, src, kt, has_llm, len(doc), doc])
    print(f"  CSV: {output_path}")


def export_to_json(all_docs, all_metas, sizes, buckets, sources, output_path: Path):
    """Export ข้อมูลและสถิติเป็น JSON"""
    data = {
        "exported_at": datetime.now().isoformat(),
        "total_chunks": len(all_docs),
        "stats": {
            "min_chars": min(sizes),
            "max_chars": max(sizes),
            "avg_chars": round(sum(sizes) / len(sizes), 1),
        },
        "size_distribution": buckets,
        "sources": {
            src: {
                "chunks": len(s),
                "avg_chars": round(sum(s) / len(s), 1),
                "min_chars": min(s),
                "max_chars": max(s),
            }
            for src, s in sources.items()
        },
        "chunks": [
            {
                "index": i + 1,
                "source": Path(meta.get("source", "Unknown")).name,
                "knowledge_type": meta.get("knowledge_type", ""),
                "has_llm_context": meta.get("has_llm_context", ""),
                "size_chars": len(doc),
                "content": doc,
            }
            for i, (doc, meta) in enumerate(zip(all_docs, all_metas))
        ],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {output_path}")


def check_vectordb():
    """ตรวจสอบข้อมูลใน VectorDB"""

    _default = str(Path(__file__).parent / "vectorstore" / "chroma_db")
    chroma_path = os.getenv("CHROMA_DB_PATH", _default)

    print_separator()
    print(" ตรวจสอบ Vector Database")
    print_separator()
    print()

    if not Path(chroma_path).exists():
        print(" ไม่พบ Vector Database!")
        print(f"   Path: {chroma_path}")
        print("\n กรุณารัน: python main.py เพื่อสร้าง VectorDB ก่อน")
        return

    print(f" พบ Vector Database")
    print(f"   Path: {chroma_path}\n")

    try:
        print(" กำลังโหลด VectorDB...")
        embeddings = get_embeddings()
        vectorstore = Chroma(
            persist_directory=chroma_path,
            embedding_function=embeddings
        )

        collection = vectorstore._collection
        count = collection.count()
        print(f"\n จำนวน Documents ทั้งหมด: {count:,} chunks\n")

        if count == 0:
            print("  VectorDB ว่างเปล่า!")
            print(" กรุณารัน: python main.py --rebuild เพื่อเพิ่มข้อมูล")
            return

        # ดึงข้อมูลทั้งหมดเพื่อคำนวณสถิติ
        print(" กำลังดึงข้อมูลทั้งหมดเพื่อวิเคราะห์...")
        all_results = collection.get(include=["documents", "metadatas"])
        all_docs = all_results["documents"]
        all_metas = all_results["metadatas"]

        # ============================================================
        # สถิติ Chunk Sizes
        # ============================================================
        print_separator()
        print(" สถิติ Chunk Sizes")
        print_separator("-")

        sizes = [len(doc) for doc in all_docs]
        avg_size = sum(sizes) / len(sizes)
        min_size = min(sizes)
        max_size = max(sizes)

        # แบ่ง buckets
        buckets = {
            "< 200 chars  (เล็กมาก)": 0,
            "200–500 chars (เล็ก)":   0,
            "500–800 chars (กลาง)":   0,
            "800–1000 chars (ดี)":    0,
            "> 1000 chars (ใหญ่)":    0,
        }
        for s in sizes:
            if s < 200:
                buckets["< 200 chars  (เล็กมาก)"] += 1
            elif s < 500:
                buckets["200–500 chars (เล็ก)"] += 1
            elif s < 800:
                buckets["500–800 chars (กลาง)"] += 1
            elif s <= 1000:
                buckets["800–1000 chars (ดี)"] += 1
            else:
                buckets["> 1000 chars (ใหญ่)"] += 1

        print(f"  Min:  {min_size:>6,} chars")
        print(f"  Max:  {max_size:>6,} chars")
        print(f"  Avg:  {avg_size:>6,.0f} chars\n")

        print("  การกระจาย:")
        for label, cnt in buckets.items():
            pct = cnt / len(sizes) * 100
            bar = "█" * int(pct / 2)
            print(f"    {label:<26} {cnt:>4} chunks ({pct:5.1f}%) {bar}")

        # ============================================================
        # สรุปแหล่งที่มา
        # ============================================================
        print()
        print_separator()
        print(" สรุปแหล่งที่มา (Source Files)")
        print_separator("-")

        sources: dict[str, list[int]] = {}
        for doc, meta in zip(all_docs, all_metas):
            src = Path(meta.get("source", "Unknown")).name
            sources.setdefault(src, []).append(len(doc))

        for src, src_sizes in sorted(sources.items(), key=lambda x: len(x[1]), reverse=True):
            src_avg = sum(src_sizes) / len(src_sizes)
            print(f"  • {src}")
            print(f"    chunks: {len(src_sizes):,}  |  avg size: {src_avg:,.0f}  |  min: {min(src_sizes):,}  max: {max(src_sizes):,}")

        # ============================================================
        # สถิติ knowledge_type Labels
        # ============================================================
        print()
        print_separator()
        print(" สถิติ Knowledge Type Labels")
        print_separator("-")

        kt_counts: dict[str, int] = {}
        for meta in all_metas:
            kt = meta.get("knowledge_type", "(ไม่มี label)")
            kt_counts[kt] = kt_counts.get(kt, 0) + 1

        has_labels = any(k != "(ไม่มี label)" for k in kt_counts)
        if not has_labels:
            print("  ⚠  ไม่พบ knowledge_type ใน metadata")
            print("     → Vectorstore ถูก build ด้วย step2 (standard) ไม่ใช่ step2b (contextual)")
            print("     → รัน: python main.py --rebuild --method contextual  เพื่อ rebuild")
        else:
            for kt, cnt in sorted(kt_counts.items(), key=lambda x: x[1], reverse=True):
                pct = cnt / count * 100
                bar = "█" * int(pct / 2)
                llm_cnt = sum(1 for m in all_metas if m.get("knowledge_type") == kt and m.get("has_llm_context"))
                llm_info = f"  (LLM context: {llm_cnt})" if kt != "(ไม่มี label)" else ""
                print(f"  {kt:<20} {cnt:>5} chunks ({pct:5.1f}%) {bar}{llm_info}")

        # ============================================================
        # ดูตัวอย่าง Chunks แบบละเอียด
        # ============================================================
        print()
        print_separator()
        print(" ดูตัวอย่าง Chunks แบบละเอียด")
        print_separator("-")

        sample_input = input(
            "\nจำนวน chunks ที่ต้องการดู (Enter = 5, 'all' = ทั้งหมด): "
        ).strip()

        if sample_input.lower() == "all":
            sample_n = len(all_docs)
        elif sample_input.isdigit():
            sample_n = int(sample_input)
        else:
            sample_n = 5

        sample_n = min(sample_n, len(all_docs))

        # เลือก chunks กระจายทั่ว DB
        step = max(1, len(all_docs) // sample_n)
        indices = list(range(0, len(all_docs), step))[:sample_n]

        for rank, idx in enumerate(indices, 1):
            doc = all_docs[idx]
            meta = all_metas[idx]
            src = Path(meta.get("source", "Unknown")).name
            size = len(doc)

            kt = all_metas[idx].get("knowledge_type", "-")
            has_llm = all_metas[idx].get("has_llm_context", "-")
            print(f"\n{'─'*80}")
            print(f" Chunk #{idx+1}  |  Source: {src}  |  Type: {kt}  |  LLM: {has_llm}  |  Size: {size:,} chars")
            print(f"{'─'*80}")
            print(doc)
            print()

        # ============================================================
        # Export ไฟล์
        # ============================================================
        print()
        print_separator()
        print(" Export ข้อมูล")
        print_separator("-")

        export_input = input(
            "\nต้องการ export ไหม? (csv / json / both / Enter = ข้าม): "
        ).strip().lower()

        if export_input in ("csv", "json", "both"):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_dir = Path(__file__).parent / "exports"
            export_dir.mkdir(exist_ok=True)

            if export_input in ("csv", "both"):
                export_to_csv(
                    all_docs, all_metas,
                    export_dir / f"chunks_{timestamp}.csv"
                )
            if export_input in ("json", "both"):
                export_to_json(
                    all_docs, all_metas, sizes, buckets, sources,
                    export_dir / f"chunks_{timestamp}.json"
                )
            print(f"\n  บันทึกไว้ที่: {export_dir}/")

        # ============================================================
        # ค้นหาทดสอบ
        # ============================================================
        print_separator()
        print(" ทดสอบการค้นหา (Similarity Search)")
        print_separator("-")

        while True:
            test_query = input("\nพิมพ์คำที่ต้องการค้นหา (Enter = ออก): ").strip()
            if not test_query:
                break

            k_input = input("จำนวนผลลัพธ์ (Enter = 3): ").strip()
            k = int(k_input) if k_input.isdigit() else 3

            print(f"\n ค้นหา: '{test_query}'  (top {k})")
            print_separator("-")

            results = vectorstore.similarity_search_with_score(test_query, k=k)

            for i, (doc, score) in enumerate(results, 1):
                src = Path(doc.metadata.get("source", "Unknown")).name
                size = len(doc.page_content)
                print(f"\n[{i}] Source: {src}  |  Size: {size:,} chars  |  Distance: {score:.4f}")
                print(f"{'─'*60}")
                print(doc.page_content)

        print()
        print_separator()
        print(" ตรวจสอบเสร็จสิ้น!")
        print_separator()

    except Exception as e:
        print(f"\n เกิดข้อผิดพลาด: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_vectordb()
