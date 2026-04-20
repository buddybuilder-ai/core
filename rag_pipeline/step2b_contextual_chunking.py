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
    LLM_MODEL_NAME,
    CONTEXTUAL_TEMPERATURE,
    OLLAMA_BASE_URL,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    ANTHROPIC_API_KEY,
)


def get_contextual_llm():
    """สร้าง LLM สำหรับ generate context summary ของแต่ละ chunk

    ใช้ CONTEXTUAL_TEMPERATURE (ต่ำกว่า TEMPERATURE ทั่วไป) เพื่อให้ summary
    มีความแม่นยำและไม่ creative เกินไป — LLM_MODEL อ่านจาก .env
    """
    if LLM_PROVIDER == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=LLM_MODEL_NAME,
            base_url=OLLAMA_BASE_URL,
            temperature=CONTEXTUAL_TEMPERATURE,
        )

    if LLM_PROVIDER == "groq":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=LLM_MODEL_NAME,
            api_key=GROQ_API_KEY,
            base_url=GROQ_BASE_URL,
            temperature=CONTEXTUAL_TEMPERATURE,
        )

    if LLM_PROVIDER == "claude":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=LLM_MODEL_NAME,
            api_key=ANTHROPIC_API_KEY,
            temperature=CONTEXTUAL_TEMPERATURE,
        )

    raise ValueError(f"LLM Provider not supported: {LLM_PROVIDER}")


def add_context_to_chunk(chunk: Document, document_title: str, use_llm: bool = True) -> Document:
    """เพิ่ม context นำหน้า chunk เพื่อช่วยให้ embedding มีความหมายชัดขึ้น

    แนวคิด Contextual Retrieval (Anthropic): chunk เดี่ยวๆ มักขาดบริบท เช่น
    "ห้ามวางเตียงตรงกับประตู" — ไม่รู้ว่าเป็นกฎของอะไร
    การเติม context นำหน้าทำให้ embedding จับใจความได้ครบกว่า

    - use_llm=False: เติมแค่ชื่อไฟล์ — เร็ว ใช้สำหรับ rebuild ด่วน
    - use_llm=True:  LLM สรุป 1-2 ประโยค — ช้ากว่าแต่ embedding แม่นขึ้น
                     ใช้ content แค่ 500 ตัวอักษรแรกเพื่อประหยัด token

    Args:
        chunk: Document chunk ที่ต้องการเพิ่ม context
        document_title: ชื่อไฟล์ต้นฉบับ (ดึงจาก metadata["source"])
        use_llm: True = ใช้ LLM สรุป context, False = เติมแค่ชื่อไฟล์

    Returns:
        Document เดิมที่ page_content มี context นำหน้าแล้ว (แก้ in-place)
    """

    if not use_llm:
        # Simple context: เติมแค่ชื่อไฟล์ต้นฉบับ ไม่เรียก LLM
        contextual_content = f"""เอกสาร: {document_title}

{chunk.page_content}
"""
        chunk.page_content = contextual_content
        return chunk

    # LLM context: ให้ LLM สรุปว่า chunk นี้พูดถึงอะไรใน 1-2 ประโยค
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
            "content": chunk.page_content[:500]  # จำกัด 500 ตัวอักษรเพื่อประหยัด token
        })

        # วาง LLM summary ไว้ก่อน chunk content เพื่อให้ embedding เก็บ context ไว้ด้วย
        contextual_content = f"""บริบท: {context_summary.content}

{chunk.page_content}
"""

        chunk.page_content = contextual_content
        chunk.metadata["has_llm_context"] = True  # บันทึกว่า chunk นี้ผ่าน LLM แล้ว

    except Exception as e:
        print(f"  ไม่สามารถเพิ่ม LLM context: {e}")
        print(f"   กลับไปใช้ simple context แทน")
        # Fallback: ถ้า LLM ล้มเหลว ใช้ simple context แทนเพื่อไม่ให้ pipeline หยุด
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
    """แบ่งเอกสารเป็น chunks และเติม context นำหน้าแต่ละ chunk

    Pipeline: documents → RecursiveCharacterTextSplitter → add_context_to_chunk (ทุก chunk)

    RecursiveCharacterTextSplitter แบ่งโดยลำดับ separator: ย่อหน้า → บรรทัด → ช่องว่าง → ตัวอักษร
    ทำให้ chunk มีเนื้อหาครบประโยคมากกว่าการตัดแบบ fixed-size

    Args:
        documents: รายการ Document ที่โหลดจาก step1_data_loader
        use_llm_context: True = ให้ LLM สรุป context (ดีกว่า แต่ช้า ต้องมี LLM ใน .env)
                         False = เติมแค่ชื่อไฟล์ (เร็วกว่า เหมาะสำหรับ rebuild ด่วน)

    Returns:
        รายการ Document chunks พร้อม context นำหน้า พร้อม embed ลง vectorstore
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_CONFIG["chunk_size"],
        chunk_overlap=CHUNK_CONFIG["chunk_overlap"],
        separators=CHUNK_CONFIG["separators"],  # ลำดับ: \n\n → \n → space → char
        length_function=len,
    )

    # แบ่ง chunks จากทุก document ก่อน แล้วค่อยเพิ่ม context ทีหลัง
    chunks = text_splitter.split_documents(documents)

    print(f"  แบ่งเป็น {len(chunks)} chunks (จาก {len(documents)} documents)")
    print(f"   Chunk size: {CHUNK_CONFIG['chunk_size']}, Overlap: {CHUNK_CONFIG['chunk_overlap']}")

    if use_llm_context:
        print(f" กำลังเพิ่ม context ด้วย LLM... (อาจใช้เวลาสักครู่)")
    else:
        print(f" กำลังเพิ่ม simple context...")

    contextual_chunks = []
    for i, chunk in enumerate(chunks):
        if (i + 1) % 10 == 0:
            # แสดง progress ทุก 10 chunks เพราะถ้าใช้ LLM จะช้า
            print(f"   ประมวลผล: {i + 1}/{len(chunks)} chunks...")

        # ดึงชื่อไฟล์จาก source path (รองรับทั้ง / และ \ ของ Windows/Unix)
        source = chunk.metadata.get("source", "Unknown")
        document_title = source.split("/")[-1] if "/" in source else source.split("\\")[-1]

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
