"""
Step 2C: Hypothetical Questions (Advanced RAG)
สร้างคำถามสมมติจาก chunks แล้ว embed คำถามแทน
"""
from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate

# Import centralized config
from config import (
    CHUNK_CONFIG,
    LLM_PROVIDER,
    QUESTION_GEN_TEMPERATURE,
    OLLAMA_MODEL,
    OLLAMA_BASE_URL,
    QUESTIONS_PER_CHUNK,
)


def get_question_llm():
    """สร้าง LLM สำหรับ generate คำถาม"""
    if LLM_PROVIDER == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=QUESTION_GEN_TEMPERATURE,  # ใช้ปานกลางเพื่อให้มีความหลากหลาย
        )

    raise ValueError(f"LLM Provider not supported: {LLM_PROVIDER}")


def generate_questions_from_chunk(chunk: Document, num_questions: int = 3) -> List[str]:
    """
    สร้างคำถามสมมติจาก chunk

    Args:
        chunk: Chunk ที่ต้องการสร้างคำถาม
        num_questions: จำนวนคำถามที่ต้องการ

    Returns:
        รายการคำถามที่สร้างได้
    """
    try:
        llm = get_question_llm()

        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""คุณคือผู้เชี่ยวชาญด้านฮวงจุ้ยและการออกแบบภายใน

จากข้อความที่ให้มา ให้สร้างคำถาม {num_questions} ข้อ ที่ผู้ใช้อาจจะถาม เกี่ยวกับเนื้อหานี้

กฎ:
- คำถามต้องเป็นภาษาไทย
- คำถามต้องตรงประเด็น ไม่กว้างเกินไป
- แต่ละคำถามแยกบรรทัด
- ไม่ต้องใส่เลขข้อ

ตัวอย่าง:
ห้องนอนควรใช้สีอะไรดี
การจัดวางเตียงนอนที่ถูกต้องคืออย่างไร
ทิศทางหัวเตียงมีผลอย่างไร
"""),
            ("human", """เนื้อหา:
{content}

คำถาม:""")
        ])

        chain = prompt | llm
        response = chain.invoke({"content": chunk.page_content[:800]})

        # แยกคำถามออกมา
        questions = [q.strip() for q in response.content.strip().split('\n') if q.strip()]

        # ลบเลขข้อออก (ถ้ามี)
        questions = [q.lstrip('0123456789.- ') for q in questions]

        return questions[:num_questions]

    except Exception as e:
        print(f"  ไม่สามารถสร้างคำถาม: {e}")
        return []


def create_qa_chunks(documents: List[Document], questions_per_chunk: int = QUESTIONS_PER_CHUNK) -> List[Document]:
    """
    สร้าง chunks ในรูปแบบ Q&A

    Args:
        documents: รายการเอกสาร
        questions_per_chunk: จำนวนคำถามต่อ chunk

    Returns:
        รายการ chunks ที่มีคำถาม + เนื้อหา
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_CONFIG["chunk_size"],
        chunk_overlap=CHUNK_CONFIG["chunk_overlap"],
        separators=CHUNK_CONFIG["separators"],
        length_function=len,
    )

    # แบ่ง chunks ก่อน
    chunks = text_splitter.split_documents(documents)

    print(f"  แบ่งเป็น {len(chunks)} chunks")
    print(f" กำลังสร้างคำถามด้วย LLM... (อาจใช้เวลาสักครู่)")

    qa_chunks = []

    for i, chunk in enumerate(chunks):
        if (i + 1) % 5 == 0:
            print(f"   ประมวลผล: {i + 1}/{len(chunks)} chunks...")

        # สร้างคำถามจาก chunk
        questions = generate_questions_from_chunk(chunk, questions_per_chunk)

        if questions:
            # สร้าง chunk ใหม่ที่มีคำถาม + เนื้อหา
            qa_content = f"""คำถามที่เกี่ยวข้อง:
{chr(10).join(f'- {q}' for q in questions)}

เนื้อหา:
{chunk.page_content}
"""

            new_chunk = Document(
                page_content=qa_content,
                metadata={
                    **chunk.metadata,
                    "questions": questions,
                    "has_questions": True
                }
            )
            qa_chunks.append(new_chunk)
        else:
            # ถ้าสร้างคำถามไม่ได้ ใช้ chunk เดิม
            chunk.metadata["has_questions"] = False
            qa_chunks.append(chunk)

    print(f" สร้างคำถามเรียบร้อย!")
    print(f"   Chunks ที่มีคำถาม: {sum(1 for c in qa_chunks if c.metadata.get('has_questions', False))}/{len(qa_chunks)}")

    return qa_chunks


if __name__ == "__main__":
    # ทดสอบ
    from step1_data_loader import load_all_documents

    docs = load_all_documents()
    if docs:
        print("\n" + "="*80)
        print("ทดสอบสร้างคำถามจาก Content")
        print("="*80)

        # ทดสอบแค่ 1-2 documents
        qa_chunks = create_qa_chunks(docs[:2], questions_per_chunk=3)

        print(f"\nตัวอย่าง chunk แรก:")
        print(f"Content:\n{qa_chunks[0].page_content[:500]}...")
        print(f"\nMetadata: {qa_chunks[0].metadata}")
