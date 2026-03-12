"""
Step 2: Text Splitter
แบ่งเอกสารเป็น chunks เล็กๆ เพื่อให้ embedding ได้ดีขึ้น
"""
from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Import centralized config
from config import CHUNK_CONFIG


def split_documents(documents: List[Document]) -> List[Document]:
    """
    แบ่งเอกสารเป็น chunks

    Args:
        documents: รายการเอกสารที่โหลดมา

    Returns:
        รายการ chunks
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_CONFIG["chunk_size"],
        chunk_overlap=CHUNK_CONFIG["chunk_overlap"],
        separators=CHUNK_CONFIG["separators"],
        length_function=len,
    )

    chunks = text_splitter.split_documents(documents)

    print(f"  แบ่งเป็น {len(chunks)} chunks (จาก {len(documents)} documents)")
    print(f"   Chunk size: {CHUNK_CONFIG['chunk_size']}, Overlap: {CHUNK_CONFIG['chunk_overlap']}")

    return chunks


if __name__ == "__main__":
    # ทดสอบ
    from step1_data_loader import load_all_documents

    docs = load_all_documents()
    if docs:
        chunks = split_documents(docs)
        print(f"\nตัวอย่าง chunk แรก:")
        print(f"Content: {chunks[0].page_content[:300]}...")
        print(f"Metadata: {chunks[0].metadata}")
