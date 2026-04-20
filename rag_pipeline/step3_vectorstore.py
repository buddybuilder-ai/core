"""
Step 3: Vector Store (ChromaDB)
สร้าง embeddings และเก็บใน ChromaDB
"""
from pathlib import Path
from typing import List
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# Import centralized config
from config import CHROMA_DB_PATH, EMBEDDING_MODEL, TOP_K, SEARCH_TYPE


def get_embeddings():
    
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
    """
    สร้าง Vector Store จาก chunks

    Args:
        chunks: รายการ chunks ที่จะ embed
        force_rebuild: rebuild ทับของเดิม (default: False)

    Returns:
        Chroma vectorstore
    """
    embeddings = get_embeddings()

    # ถ้าต้องการ rebuild ให้ลบของเดิมก่อน
    if force_rebuild and Path(CHROMA_DB_PATH).exists():
        print(f"  ลบ vectorstore เดิม: {CHROMA_DB_PATH}")
        import shutil
        shutil.rmtree(CHROMA_DB_PATH)

    # สร้าง vectorstore
    if Path(CHROMA_DB_PATH).exists() and not force_rebuild:
        print(f" โหลด vectorstore ที่มีอยู่: {CHROMA_DB_PATH}")
        vectorstore = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=embeddings
        )
    else:
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
    """
    สร้าง Retriever จาก vectorstore

    Args:
        vectorstore: ChromaDB vectorstore
        k: จำนวน chunks ที่จะดึง (default: 5)
        search_type: "similarity" หรือ "mmr" (default: "mmr")

    Returns:
        Retriever object
    """
    retriever = vectorstore.as_retriever(
        search_type=search_type,  # "mmr" = Maximum Marginal Relevance (หลากหลายกว่า)
        search_kwargs={"k": k}
    )

    print(f" Retriever: search_type={search_type}, k={k}")
    return retriever


def get_retriever_with_filter(vectorstore, filters: dict, k: int = TOP_K, search_type: str = SEARCH_TYPE):
    """
    สร้าง Retriever ที่ filter ด้วย metadata labels

    Args:
        vectorstore: ChromaDB vectorstore
        filters: dict เช่น {"category": "placement"} หรือ {"topic_th": "ห้องนอน"}
        k: จำนวน chunks ที่จะดึง
        search_type: "similarity" หรือ "mmr"

    Returns:
        Retriever object ที่กรองด้วย label
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
