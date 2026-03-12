"""
Step 2B: Contextual Chunking (Advanced RAG)
แบ่งเอกสารเป็น chunks พร้อมเพิ่ม context จาก LLM
"""
from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate

# Import centralized config
from config import (
    CHUNK_CONFIG,
    LLM_PROVIDER,
    CONTEXTUAL_TEMPERATURE,
    OLLAMA_MODEL,
    OLLAMA_BASE_URL,
)


def get_contextual_llm():
    """สร้าง LLM สำหรับเพิ่ม context"""
    if LLM_PROVIDER == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=CONTEXTUAL_TEMPERATURE,  # ใช้ต่ำเพื่อความแม่นยำ
        )

    # เพิ่ม provider อื่นๆ ได้ที่นี่
    raise ValueError(f"LLM Provider not supported: {LLM_PROVIDER}")


def add_context_to_chunk(chunk: Document, document_title: str, use_llm: bool = True) -> Document:
    """
    เพิ่ม context ให้ chunk โดยใช้ LLM

    Args:
        chunk: Chunk ที่ต้องการเพิ่ม context
        document_title: ชื่อเอกสารต้นฉบับ
        use_llm: ใช้ LLM เพิ่ม context หรือไม่ (ถ้า False จะเพิ่ม simple context)

    Returns:
        Document ที่มี context เพิ่มเติม
    """

    if not use_llm:
        # Simple context (ไม่ใช้ LLM - เร็วกว่า)
        contextual_content = f"""เอกสาร: {document_title}

{chunk.page_content}
"""
        chunk.page_content = contextual_content
        return chunk

    # ใช้ LLM เพิ่ม context (ช้ากว่า แต่ดีกว่า)
    try:
        llm = get_contextual_llm()

        prompt = ChatPromptTemplate.from_messages([
            ("system", """คุณคือผู้ช่วยที่เพิ่มบริบทให้กับข้อความ

ให้สรุปบริบทของข้อความนี้ใน 1-2 ประโยคสั้นๆ เพื่อช่วยให้เข้าใจว่าข้อความนี้พูดถึงอะไร

ตัวอย่าง:
ข้อความ: "สีฟ้าช่วยให้รู้สึกสงบ"
บริบท: "เรื่องสีในการตกแต่งภายในและผลต่ออารมณ์"
"""),
            ("human", """เอกสาร: {document_title}

ข้อความ:
{content}

บริบท:""")
        ])

        chain = prompt | llm
        context_summary = chain.invoke({
            "document_title": document_title,
            "content": chunk.page_content[:500]  # ใช้แค่ 500 ตัวอักษรแรก
        })

        # เพิ่ม context เข้าไปใน chunk
        contextual_content = f"""บริบท: {context_summary.content}

{chunk.page_content}
"""

        chunk.page_content = contextual_content
        chunk.metadata["has_llm_context"] = True

    except Exception as e:
        print(f"  ไม่สามารถเพิ่ม LLM context: {e}")
        print(f"   กลับไปใช้ simple context แทน")
        # Fallback to simple context
        contextual_content = f"""เอกสาร: {document_title}

{chunk.page_content}
"""
        chunk.page_content = contextual_content
        chunk.metadata["has_llm_context"] = False

    return chunk


def split_documents_with_context(
    documents: List[Document],
    use_llm_context: bool = False
) -> List[Document]:
    """
    แบ่งเอกสารเป็น chunks พร้อมเพิ่ม context

    Args:
        documents: รายการเอกสารที่โหลดมา
        use_llm_context: ใช้ LLM เพิ่ม context หรือไม่

    Returns:
        รายการ chunks พร้อม context
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_CONFIG["chunk_size"],
        chunk_overlap=CHUNK_CONFIG["chunk_overlap"],
        separators=CHUNK_CONFIG["separators"],
        length_function=len,
    )

    # แบ่ง chunks ก่อน
    chunks = text_splitter.split_documents(documents)

    print(f"  แบ่งเป็น {len(chunks)} chunks (จาก {len(documents)} documents)")
    print(f"   Chunk size: {CHUNK_CONFIG['chunk_size']}, Overlap: {CHUNK_CONFIG['chunk_overlap']}")

    if use_llm_context:
        print(f" กำลังเพิ่ม context ด้วย LLM... (อาจใช้เวลาสักครู่)")
    else:
        print(f" กำลังเพิ่ม simple context...")

    # เพิ่ม context ให้แต่ละ chunk
    contextual_chunks = []
    for i, chunk in enumerate(chunks):
        if (i + 1) % 10 == 0:
            print(f"   ประมวลผล: {i + 1}/{len(chunks)} chunks...")

        # ดึงชื่อเอกสารจาก metadata
        source = chunk.metadata.get("source", "Unknown")
        document_title = source.split("/")[-1] if "/" in source else source.split("\\")[-1]

        # เพิ่ม context
        contextual_chunk = add_context_to_chunk(chunk, document_title, use_llm_context)
        contextual_chunks.append(contextual_chunk)

    print(f" เพิ่ม context เรียบร้อย!")

    return contextual_chunks


if __name__ == "__main__":
    # ทดสอบ
    from step1_data_loader import load_all_documents

    docs = load_all_documents()
    if docs:
        print("\n" + "="*80)
        print("ทดสอบ Simple Context (ไม่ใช้ LLM)")
        print("="*80)
        chunks_simple = split_documents_with_context(docs, use_llm_context=False)

        print(f"\nตัวอย่าง chunk แรก:")
        print(f"Content: {chunks_simple[0].page_content[:300]}...")
        print(f"Metadata: {chunks_simple[0].metadata}")

        print("\n" + "="*80)
        print("ทดสอบ LLM Context")
        print("="*80)
        chunks_llm = split_documents_with_context(docs[:1], use_llm_context=True)  # ทดสอบแค่ 1 doc

        print(f"\nตัวอย่าง chunk แรก (with LLM context):")
        print(f"Content: {chunks_llm[0].page_content[:400]}...")
