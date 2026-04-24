"""
Step 3: Vector Store (ChromaDB)
สร้าง embeddings และเก็บใน ChromaDB
"""
from pathlib import Path
from typing import List
from langchain_core.documents import Document

# Import centralized config
from config import CHROMA_DB_PATH, EMBEDDING_MODEL, TOP_K, SEARCH_TYPE


def get_embeddings():
    """สร้าง HuggingFaceEmbeddings พร้อม auto-detect device (CUDA → MPS → CPU)

    ใช้ normalize_embeddings=True เพื่อให้ L2 distance มีความหมายเดียวกับ cosine similarity
    (L2² = 2·(1 − cosine) เมื่อ normalize แล้ว) ซึ่ง ChromaDB ใช้เป็น relevance score

    Returns:
        HuggingFaceEmbeddings พร้อมใช้งาน
    """
    from langchain_community.embeddings import HuggingFaceEmbeddings

    print(f"Embedding model: {EMBEDDING_MODEL}")

    # ตรวจสอบว่ามี GPU หรือไม่
    device = "cpu"  # Default
    try:
        import torch

        # ตรวจสอบ CUDA (NVIDIA GPU)
        if torch.cuda.is_available():
            device = "cuda"
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # GB
            print(f"    Device: {device}")
            print(f"   GPU: {gpu_name}")
            print(f"   VRAM: {gpu_memory:.1f} GB")

        # ตรวจสอบ MPS (Apple Silicon)
        elif torch.backends.mps.is_available():
            device = "mps"
            print(f"    Device: {device} (Apple Silicon)")

        # Fallback เป็น CPU
        else:
            print(f"     Device: cpu (ไม่พบ GPU)")
            print(f"    Tip: ติดตั้ง PyTorch with CUDA สำหรับความเร็วที่ดีกว่า")

    except ImportError:
        print(f"     Device: cpu (torch ไม่ได้ติดตั้ง)")
    except Exception as e:
        print(f"     Device: cpu (เกิดข้อผิดพลาดในการตรวจจับ GPU: {e})")

    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True}
    )


def create_vectorstore(chunks: List[Document], force_rebuild: bool = False):
    """สร้างหรือโหลด ChromaDB vectorstore จาก chunks ที่ผ่านการแบ่งแล้ว

    ถ้า vectorstore มีอยู่แล้วและไม่ได้ force_rebuild จะโหลดของเดิมแทนการสร้างใหม่
    เพื่อประหยัดเวลา embedding (ใช้เวลานานถ้ามี docs เยอะ)

    Args:
        chunks: รายการ Document chunks ที่จะ embed และเก็บลง ChromaDB
        force_rebuild: ถ้า True จะลบ vectorstore เดิมและสร้างใหม่ทั้งหมด (default: False)

    Returns:
        Chroma vectorstore instance พร้อมใช้งาน
    """
    from langchain_community.vectorstores import Chroma

    embeddings = get_embeddings()

    # ลบ vectorstore เดิมก่อนสร้างใหม่ — ต้องปิด server ที่ใช้ไฟล์อยู่ก่อน
    # มิฉะนั้นจะเกิด PermissionError: chroma.sqlite3 is being used by another process
    if force_rebuild and Path(CHROMA_DB_PATH).exists():
        print(f"  ลบ vectorstore เดิม: {CHROMA_DB_PATH}")
        import shutil
        shutil.rmtree(CHROMA_DB_PATH)

    if Path(CHROMA_DB_PATH).exists() and not force_rebuild:
        # โหลด vectorstore ที่มีอยู่แล้ว — เร็วกว่าการ embed ใหม่ทั้งหมด
        print(f" โหลด vectorstore ที่มีอยู่: {CHROMA_DB_PATH}")
        vectorstore = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=embeddings
        )
    else:
        # Embed chunks ทั้งหมดและบันทึกลง disk — ขั้นตอนที่ใช้เวลานานที่สุด
        print(f" สร้าง vectorstore ใหม่: {CHROMA_DB_PATH}")
        print(f"   Embedding model: {EMBEDDING_MODEL}")
        print(f"   จำนวน chunks: {len(chunks)}")

        vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=CHROMA_DB_PATH
        )
        print(f" สร้าง vectorstore เสร็จแล้ว!")

    return vectorstore


def get_retriever(vectorstore, k: int = TOP_K, search_type: str = SEARCH_TYPE):
    """สร้าง LangChain Retriever จาก vectorstore

    search_type="mmr" (Maximum Marginal Relevance) คืน docs ที่หลากหลายกว่า "similarity"
    ลดการดึง chunks ซ้ำๆ จากเอกสารเดียวกัน ทำให้ context ครอบคลุมมากขึ้น

    Args:
        vectorstore: ChromaDB vectorstore instance
        k: จำนวน chunks ที่จะดึงต่อ query (default: TOP_K จาก config)
        search_type: "mmr" = หลากหลาย, "similarity" = แม่นยำ (default: SEARCH_TYPE จาก config)

    Returns:
        VectorStoreRetriever พร้อมใช้งานกับ LangChain chain
    """
    retriever = vectorstore.as_retriever(
        search_type=search_type,
        search_kwargs={"k": k}
    )

    print(f" Retriever: search_type={search_type}, k={k}")
    return retriever


def get_retriever_with_filter(vectorstore, filters: dict, k: int = TOP_K, search_type: str = SEARCH_TYPE):
    """สร้าง Retriever ที่กรองด้วย metadata ก่อน search

    ใช้เมื่อต้องการจำกัด search ให้อยู่เฉพาะ subset ของ documents
    เช่น ดึงแค่ chunks ที่มี category="placement" หรือ topic_th="ห้องนอน"
    metadata เหล่านี้ถูก index ไว้ตอน load_csv_excel() ใน step1_data_loader.py

    Args:
        vectorstore: ChromaDB vectorstore instance
        filters: dict ของ metadata filter เช่น {"category": "placement"}
        k: จำนวน chunks ที่จะดึง (default: TOP_K จาก config)
        search_type: "mmr" หรือ "similarity" (default: SEARCH_TYPE จาก config)

    Returns:
        VectorStoreRetriever ที่กรองด้วย metadata label
    """
    retriever = vectorstore.as_retriever(
        search_type=search_type,
        search_kwargs={"k": k, "filter": filters}
    )
    print(f" Filtered Retriever: filter={filters}, k={k}")
    return retriever


if __name__ == "__main__":
    # ทดสอบ
    from step1_data_loader import load_all_documents
    from step2_text_splitter import split_documents

    docs = load_all_documents()
    if docs:
        chunks = split_documents(docs)
        vectorstore = create_vectorstore(chunks, force_rebuild=True)

        # ทดสอบค้นหา
        query = "ฮวงจุ้ยในห้องนอน"
        results = vectorstore.similarity_search(query, k=3)

        print(f"\n ทดสอบค้นหา: '{query}'")
        for i, doc in enumerate(results, 1):
            print(f"\n--- Result {i} ---")
            print(doc.page_content[:200])
