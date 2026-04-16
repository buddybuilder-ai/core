"""
Step 4B: RAG Chain with Conversation Memory
รองรับการจดจำบริบทการสนทนา
"""
from typing import List, Tuple
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage

# Import centralized config
from config import (
    LLM_PROVIDER,
    LLM_MODEL_NAME,
    TEMPERATURE,
    MAX_TOKENS,
    TOP_P,
    REPEAT_PENALTY,
    OLLAMA_BASE_URL,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    ANTHROPIC_API_KEY,
    RELEVANCE_THRESHOLD as CONFIG_RELEVANCE_THRESHOLD,
    FUZZY_MATCH_THRESHOLD,
    MAX_HISTORY,
)

# นำเข้าจาก rag_constants — แก้ที่นั่นที่เดียว ครอบคลุมทั้ง dev (step4b) และ production (core)
from rag_constants import SYSTEM_PROMPT, DOMAIN_KEYWORDS, OUT_OF_SCOPE_MSG


def get_llm():
    """สร้าง LLM ตาม LLM_MODEL ใน .env (format: provider/model-name)"""
    if LLM_PROVIDER == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=LLM_MODEL_NAME,
            base_url=OLLAMA_BASE_URL,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            repeat_penalty=REPEAT_PENALTY,
            num_predict=MAX_TOKENS,
        )

    if LLM_PROVIDER == "groq":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=LLM_MODEL_NAME,
            api_key=GROQ_API_KEY,
            base_url=GROQ_BASE_URL,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

    if LLM_PROVIDER == "claude":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=LLM_MODEL_NAME,
            api_key=ANTHROPIC_API_KEY,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

    raise ValueError(f"ไม่รองรับ LLM_PROVIDER: {LLM_PROVIDER} (ตัวเลือก: ollama, groq, claude)")


def format_documents(docs: List[Document]) -> str:
    """แปลง documents เป็น string สำหรับ context"""
    formatted = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "Unknown")
        content = doc.page_content.strip()
        formatted.append(f"[Document {i}] (Source: {source})\n{content}")

    return "\n\n---\n\n".join(formatted)


def format_chat_history(chat_history: List[Tuple[str, str]]) -> str:
    """แปลง chat history เป็น string แบบธรรมชาติ"""
    if not chat_history:
        return "[ยังไม่มีประวัติการสนทนา - นี่คือการสนทนาใหม่]"

    formatted = []
    for i, (human, ai) in enumerate(chat_history, 1):
        formatted.append(f"รอบที่ {i}:\nคุณถาม: {human}\nผมตอบ: {ai}")

    return "\n\n".join(formatted)


def contains_chinese(text: str) -> bool:
    """ตรวจสอบว่ามีตัวอักษรจีนหรือไม่"""
    for char in text:
        if '\u4e00' <= char <= '\u9fff':  # CJK Unified Ideographs
            return True
    return False


class ConversationRAGChain:
    """RAG Chain ที่จำบทสนทนาได้ (stateful) สำหรับใช้ใน dev/testing

    ใช้สำหรับทดสอบ RAG pipeline ใน terminal (test_rag_chat.py)
    Production ใช้ FengShuiRAGService ใน core/src แทน เพราะ stateless เหมาะกับ API

    Flow ต่อ request:
        user question → _check_relevance → retrieve docs → format prompt → LLM → answer
                                                                        ↑
                                                              (พร้อม chat_history)
    """

    def __init__(self, retriever, max_history: int = MAX_HISTORY):
        """ตั้งค่า chain และ LLM — เรียกครั้งเดียวตอน startup

        Args:
            retriever: VectorStoreRetriever จาก step3_vectorstore.get_retriever()
            max_history: จำนวนรอบสนทนาที่เก็บใน memory (default: MAX_HISTORY จาก config)
                         รอบเก่ากว่า max_history จะถูกทิ้งเพื่อไม่ให้ prompt ยาวเกินไป
        """
        self.retriever = retriever
        self.max_history = max_history
        self.chat_history: List[Tuple[str, str]] = []  # เก็บ (human, ai) ทีละคู่

        self.llm = get_llm()

        # Prompt structure: system prompt → history → retrieved context → question
        # ลำดับนี้สำคัญ: system บอก persona, history ให้ LLM รู้บริบท, context ให้ข้อมูล RAG
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", """## ประวัติการสนทนาก่อนหน้า:
{chat_history}

## ข้อมูลอ้างอิงจากฐานความรู้:
{context}

## คำถามใหม่:
{question}

---
 สำคัญ: ตอบเป็นภาษาไทยเท่านั้น ห้ามใช้ตัวอักษรจีนหรือ Pinyin แม้แต่ตัวเดียว

โปรดตอบคำถามโดย:
1. อ่านข้อมูลอ้างอิงจากทุกภาษา (ไทย/อังกฤษ/จีน)
2. เข้าใจและสรุปใจความสำคัญ
3. ตอบเป็นภาษาไทยทั้งหมด 100%
4. ห้ามคัดลอกตัวอักษรจีนหรืออังกฤษจาก context
5. สานต่อบทสนทนาอย่างเป็นธรรมชาติ

ตอบเป็นภาษาไทยเท่านั้นครับ""")
        ])

        # LangChain LCEL chain: dict input → prompt → LLM → parse string output
        # retriever.invoke() เรียกตอน chain.invoke() ไม่ใช่ตอนสร้าง object
        self.chain = (
            {
                "context": lambda x: format_documents(
                    self.retriever.invoke(x["question"])  # ดึง docs จาก vectorstore
                ),
                "chat_history": lambda x: format_chat_history(x["chat_history"]),
                "question": lambda x: x["question"]
            }
            | self.prompt
            | self.llm
            | StrOutputParser()  # แปลง AIMessage → plain string
        )

        print(f" Conversation RAG Chain พร้อมใช้งาน!")
        print(f"   LLM: {LLM_PROVIDER}")
        print(f"   Temperature: {TEMPERATURE}")
        print(f"   Max History: {max_history} รอบ")

    # L2 distance threshold สำหรับ normalized embeddings
    # 0 = identical, 1.0 = cosine~0.5, 1.4 = orthogonal (ไม่เกี่ยวกันเลย)
    RELEVANCE_THRESHOLD = CONFIG_RELEVANCE_THRESHOLD  # ดึงจาก config (default: 0.35)

    # DOMAIN_KEYWORDS, OUT_OF_SCOPE_MSG → imported from rag_constants (module level)

    def _fuzzy_match(self, text: str, keyword: str, threshold: int = None) -> bool:
        """
        ตรวจสอบว่า text มีคำที่คล้ายกับ keyword หรือไม่ (รองรับพิมพ์ผิด)

        Args:
            text: ข้อความที่จะตรวจสอบ
            keyword: คำสำคัญที่ต้องการหา
            threshold: จำนวนตัวอักษรที่ต่างกันได้ (ถ้าไม่ระบุจะใช้ค่าจาก config)

        Returns:
            True ถ้าพบคำที่คล้ายกัน
        """
        if threshold is None:
            threshold = FUZZY_MATCH_THRESHOLD

        words = text.split()
        for word in words:
            # ตรวจสอบความยาวคล้ายกัน
            if abs(len(word) - len(keyword)) > threshold:
                continue

            # นับจำนวนตัวอักษรที่ต่างกัน
            diff_count = sum(1 for a, b in zip(word, keyword) if a != b)
            if diff_count <= threshold:
                return True

        return False

    def _has_domain_keywords(self, question: str, check_history: bool = True) -> bool:
        """
        ตรวจสอบว่าคำถามมีคำสำคัญที่เกี่ยวข้องกับ domain หรือไม่
        (รองรับ: คำพิมพ์ผิด, chat history, partial matching)

        Args:
            question: คำถามที่จะตรวจสอบ
            check_history: ตรวจสอบ chat history ด้วยหรือไม่

        Returns:
            True ถ้ามีคำสำคัญ, False ถ้าไม่มี
        """
        question_lower = question.lower()

        # Layer 1: ตรวจสอบคำถามโดยตรง (exact match)
        for keyword in self.DOMAIN_KEYWORDS:
            if keyword.lower() in question_lower:
                return True

        # Layer 2: ตรวจสอบคำพิมพ์ผิด (fuzzy match)
        for keyword in self.DOMAIN_KEYWORDS:
            if len(keyword) >= 4:  # ตรวจ fuzzy เฉพาะคำยาว >= 4 ตัวอักษร
                if self._fuzzy_match(question_lower, keyword.lower()):
                    return True

        # Layer 3: ตรวจสอบ chat history (สำหรับคำถามสั้นที่ต่อจากบทสนทนา)
        if check_history and self.chat_history:
            # ดูคำถาม 2 รอบล่าสุด
            recent_history = self.chat_history[-2:]
            for human_q, ai_a in recent_history:
                combined_text = (human_q + " " + ai_a).lower()

                # ตรวจว่าประวัติการสนทนามีคำสำคัญหรือไม่
                for keyword in self.DOMAIN_KEYWORDS:
                    if keyword.lower() in combined_text:
                        # ถ้าคำถามปัจจุบันสั้น (< 15 ตัวอักษร) และประวัติมีคำสำคัญ
                        # → ถือว่าเป็นคำถามต่อเนื่อง
                        if len(question) < 15:
                            return True

        return False

    def _check_relevance(self, question: str) -> bool:
        """
        ตรวจสอบว่าคำถามอยู่ใน scope ของฐานความรู้ไหม (2-layer check)

        Layer 1: Keyword check (เร็ว - ตรวจคำสำคัญ)
        Layer 2: Similarity score (แม่นยำ - ตรวจ semantic similarity)

        Returns True ถ้าเกี่ยวข้อง, False ถ้านอก scope
        """
        # Layer 1: Quick keyword check
        has_keywords = self._has_domain_keywords(question)
        print(f"   Keyword check: {' Found' if has_keywords else ' Not found'}")

        # ถ้าไม่มีคำสำคัญเลย → ปฏิเสธทันที (ประหยัด embedding)
        if not has_keywords:
            print(f"   → Rejected (no domain keywords)")
            return False

        # Layer 2: Similarity score check
        try:
            vectorstore = getattr(self.retriever, "vectorstore", None)
            if vectorstore is None:
                return True  # ถ้าเข้าไม่ได้ ให้ผ่านไปก่อน

            docs_with_scores = vectorstore.similarity_search_with_score(question, k=1)
            if not docs_with_scores:
                return False

            best_score = docs_with_scores[0][1]
            is_relevant = best_score <= self.RELEVANCE_THRESHOLD

            print(f"   Similarity score: {best_score:.3f} (threshold: {self.RELEVANCE_THRESHOLD})")
            print(f"   → {' Relevant' if is_relevant else ' Not relevant'}")

            return is_relevant

        except Exception as e:
            print(f"    Relevance check failed: {e}")
            return True  # ถ้า error ให้ผ่านไปก่อน

    def invoke(self, question: str) -> str:
        """ถามคำถามกับ RAG chain พร้อมบริบทการสนทนาที่สะสมมา

        ตรวจ relevance ก่อนเสมอ เพื่อประหยัด LLM token สำหรับคำถามนอก scope

        Args:
            question: คำถามของผู้ใช้

        Returns:
            คำตอบภาษาไทยจาก LLM หรือ OUT_OF_SCOPE_MSG ถ้าคำถามนอก scope
        """
        # ตรวจ relevance ก่อน — ถ้า block ตรงนี้จะไม่เรียก LLM เลย ประหยัด token
        if not self._check_relevance(question):
            print("    Out of scope — skipping LLM call")
            return self.OUT_OF_SCOPE_MSG

        answer = self.chain.invoke({
            "question": question,
            "chat_history": self.chat_history  # ส่ง history ทั้งหมดเข้า prompt
        })

        # ถ้ามีตัวอักษรจีนหลุดออกมา แสดงว่า model ไม่ทำตาม instruction — แจ้งเตือน
        if contains_chinese(answer):
            print("    WARNING: ตรวจพบตัวอักษรจีนในคำตอบ")
            print("    Tip: ลด TEMPERATURE ใน .env หรือเปลี่ยน model")

        # บันทึกคู่ (question, answer) ลง history สำหรับรอบถัดไป
        self.chat_history.append((question, answer))

        # ตัด history เก่าออกถ้าเกิน max_history เพื่อไม่ให้ prompt ยาวเกินไป
        if len(self.chat_history) > self.max_history:
            self.chat_history = self.chat_history[-self.max_history:]

        return answer

    def clear_history(self):
        """ล้าง chat history ทั้งหมด — ใช้เมื่อต้องการเริ่มบทสนทนาใหม่"""
        self.chat_history = []
        print("  ล้างประวัติการสนทนาแล้ว")

    def get_history(self) -> List[Tuple[str, str]]:
        """คืน chat history ทั้งหมดในรูป list ของ (question, answer) tuple"""
        return self.chat_history


def ask_question(rag_chain: ConversationRAGChain, question: str) -> str:
    """
    ถามคำถามกับ RAG system

    Args:
        rag_chain: Conversation RAG chain
        question: คำถาม

    Returns:
        คำตอบจาก AI
    """
    print(f"\n คุณ: {question}")
    print("⏳ กำลังค้นหาและตอบ...")

    answer = rag_chain.invoke(question)

    print(f"\n AI: {answer}")
    return answer


if __name__ == "__main__":
    # ทดสอบ Conversation RAG
    from step3_vectorstore import create_vectorstore, get_retriever
    from step1_data_loader import load_all_documents
    from step2_text_splitter import split_documents

    # โหลดข้อมูล
    docs = load_all_documents()
    if not docs:
        print(" ไม่มีเอกสารในระบบ")
        exit(1)

    # สร้าง vectorstore และ retriever
    chunks = split_documents(docs)
    vectorstore = create_vectorstore(chunks)
    retriever = get_retriever(vectorstore, k=3)

    # สร้าง Conversation RAG chain
    rag_chain = ConversationRAGChain(retriever, max_history=10)

    # ทดสอบการสนทนา
    print("\n" + "="*80)
    print("ทดสอบ Conversation Memory")
    print("="*80)

    # รอบที่ 1
    ask_question(rag_chain, "ห้องนอนควรใช้สีอะไรดี?")

    print("\n" + "-"*80)

    # รอบที่ 2 - อ้างอิงคำตอบก่อนหน้า
    ask_question(rag_chain, "แล้วสีที่บอกนี้ใช้กับห้องนั่งเล่นได้ไหม?")

    print("\n" + "-"*80)

    # รอบที่ 3 - ถามต่อเนื่อง
    ask_question(rag_chain, "มีสีอื่นแนะนำอีกไหม?")

    print("\n" + "="*80)
    print(f" ประวัติการสนทนา: {len(rag_chain.get_history())} รอบ")
