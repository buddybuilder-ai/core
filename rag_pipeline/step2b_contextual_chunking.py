"""
Step 2B: Contextual Chunking (Advanced RAG)
แบ่งเอกสารเป็น chunks พร้อมเพิ่ม context และ classify knowledge_type ในครั้งเดียว
"""
import csv
import time
from datetime import datetime
from pathlib import Path
from typing import List

from config import (
    ANTHROPIC_API_KEY,
    CHUNK_CONFIG,
    CONTEXTUAL_TEMPERATURE,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    LLM_MODEL_NAME,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
)

EXPORTS_DIR = Path(__file__).parent / "exports"

# Keyword lists สำหรับ classify แบบไม่ใช้ LLM (use_llm=False)
_FENG_SHUI_KW = [
    "ฮวงจุ้ย", "feng shui", "fengshui", "กัว", "kua", "chi", "ชี่",
    "ทิศมงคล", "ming gua", "minggua", "พลังงานฮวงจุ้ย", "ธาตุ",
    "เลขกัว", "ทิศดี", "ทิศเสีย", "ทิศอัปมงคล", "ทิศมงคล",
]
_INTERIOR_KW = [
    "ตกแต่ง", "interior", "เฟอร์นิเจอร์", "furniture", "ผ้าม่าน",
    "วอลเปเปอร์", "lighting", "แสงสว่าง", "วัสดุ", "สีทา", "สีห้อง",
    "โคมไฟ", "พรม", "ผนัง", "เพดาน", "พื้น",
]


class _RecursiveCharacterTextSplitter:
    """Lightweight recursive character text splitter — no transformers dependency."""

    def __init__(self, chunk_size: int, chunk_overlap: int, separators: list[str]):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators

    def split_text(self, text: str) -> list[str]:
        return self._split(text, self.separators)

    def _split(self, text: str, separators: list[str]) -> list[str]:
        if not separators:
            return self._merge([text])
        sep = separators[0]
        remaining = separators[1:]
        if sep == "":
            splits = list(text)
        else:
            splits = text.split(sep)

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for s in splits:
            s_len = len(s)
            if current_len + s_len + (len(sep) if current else 0) > self.chunk_size and current:
                merged = sep.join(current)
                if len(merged) > self.chunk_size and remaining:
                    chunks.extend(self._split(merged, remaining))
                else:
                    chunks.append(merged)
                # keep overlap
                overlap_parts: list[str] = []
                overlap_len = 0
                for part in reversed(current):
                    if overlap_len + len(part) + len(sep) > self.chunk_overlap:
                        break
                    overlap_parts.insert(0, part)
                    overlap_len += len(part) + len(sep)
                current = overlap_parts
                current_len = overlap_len

            current.append(s)
            current_len += s_len + (len(sep) if len(current) > 1 else 0)

        if current:
            merged = sep.join(current)
            if len(merged) > self.chunk_size and remaining:
                chunks.extend(self._split(merged, remaining))
            else:
                chunks.append(merged)

        return [c for c in chunks if c.strip()]

    def _merge(self, splits: list[str]) -> list[str]:
        chunks: list[str] = []
        current = ""
        for s in splits:
            if len(current) + len(s) > self.chunk_size and current:
                chunks.append(current)
                current = current[-self.chunk_overlap:] if self.chunk_overlap else ""
            current += s
        if current:
            chunks.append(current)
        return chunks

    def split_documents(self, documents: list) -> list:
        from langchain_core.documents import Document
        result = []
        for doc in documents:
            for chunk_text in self.split_text(doc.page_content):
                result.append(Document(page_content=chunk_text, metadata=dict(doc.metadata)))
        return result


def _keyword_classify(text: str) -> str:
    """Classify knowledge_type จาก keyword ใน content (ไม่ใช้ LLM)"""
    t = text.lower()
    has_fs = any(kw in t for kw in _FENG_SHUI_KW)
    has_id = any(kw in t for kw in _INTERIOR_KW)
    if has_fs and has_id:
        return "both"
    if has_id:
        return "interior_design"
    return "feng_shui"  # default — domain นี้คือ feng shui


def get_contextual_llm():
    """สร้าง LLM สำหรับ contextual chunking + classify"""
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


def add_context_to_chunk(
    chunk,
    document_title: str,
    use_llm: bool = True,
    llm=None,
):
    """เพิ่ม context นำหน้า chunk และ classify knowledge_type

    - use_llm=False: simple context (ชื่อไฟล์) + keyword classify — เร็ว ไม่เสีย token
    - use_llm=True + llm: ใช้ LLM instance ที่ส่งมา (สร้างครั้งเดียวข้างนอก)
    - use_llm=True + llm=None: สร้าง LLM ใหม่ (backward-compat, ช้ากว่า)

    Returns:
        chunk ที่ page_content มี context นำหน้า + metadata["knowledge_type"] ถูกตั้งแล้ว
    """
    if not use_llm:
        chunk.page_content = f"เอกสาร: {document_title}\n\n{chunk.page_content}"
        chunk.metadata["knowledge_type"] = _keyword_classify(chunk.page_content)
        chunk.metadata["has_llm_context"] = False
        return chunk

    try:
        from langchain_core.prompts import ChatPromptTemplate
        _prompt = ChatPromptTemplate.from_messages([
            ("system", """คุณคือผู้ช่วยที่เพิ่มบริบทและจัดประเภทข้อความด้านฮวงจุ้ยและการตกแต่งภายใน

ให้ตอบ 2 บรรทัดเท่านั้น โดยใช้รูปแบบนี้พอดี:
บริบท: <สรุปข้อความใน 1-2 ประโยค>
ประเภท: <feng_shui หรือ interior_design หรือ both>

นิยามประเภท:
- feng_shui: หลักฮวงจุ้ย เลขกัว ทิศมงคล chi พลังงาน
- interior_design: การตกแต่ง สี แสง เฟอร์นิเจอร์ วัสดุ (ไม่เกี่ยวฮวงจุ้ย)
- both: ผสมทั้งสองอย่าง"""),
            ("human", "เอกสาร: {document_title}\n\nข้อความ:\n{content}"),
        ])
        _llm = llm if llm is not None else get_contextual_llm()
        chain = _prompt | _llm
        result = chain.invoke({
            "document_title": document_title,
            "content": chunk.page_content[:500],
        })

        output = result.content.strip()
        lines = [l.strip() for l in output.split("\n") if l.strip()]

        context_summary = ""
        knowledge_type: str | None = None

        for line in lines:
            if line.startswith("บริบท:"):
                context_summary = line.split(":", 1)[1].strip()
            elif line.startswith("ประเภท:"):
                raw = line.split(":", 1)[1].strip().lower()
                for valid in ("feng_shui", "interior_design", "both"):
                    if valid in raw:
                        knowledge_type = valid
                        break

        # fallback ถ้า LLM ไม่ตามรูปแบบ
        if not knowledge_type:
            knowledge_type = _keyword_classify(chunk.page_content)

        if context_summary:
            chunk.page_content = f"บริบท: {context_summary}\n\n{chunk.page_content}"
        chunk.metadata["knowledge_type"] = knowledge_type
        chunk.metadata["has_llm_context"] = True

    except Exception as e:
        # \n เพื่อ break partial line ที่ caller print ไว้ด้วย end=""
        print(f"\n  ⚠  LLM error: {e} → fallback keyword classify")
        chunk.page_content = f"เอกสาร: {document_title}\n\n{chunk.page_content}"
        chunk.metadata["knowledge_type"] = _keyword_classify(chunk.page_content)
        chunk.metadata["has_llm_context"] = False

    return chunk


def export_chunks_to_csv(chunks: "List") -> Path:
    """Export chunks ทั้งหมดไป exports/chunks_YYYYMMDD_HHMMSS.csv

    Columns: chunk_id, source, knowledge_type, has_llm_context, content_preview
    """
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = EXPORTS_DIR / f"chunks_{timestamp}.csv"

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "chunk_id", "source", "knowledge_type",
            "has_llm_context", "content_preview",
        ])
        for i, chunk in enumerate(chunks, 1):
            writer.writerow([
                i,
                chunk.metadata.get("source", ""),
                chunk.metadata.get("knowledge_type", ""),
                chunk.metadata.get("has_llm_context", ""),
                chunk.page_content[:500].replace("\n", " "),
            ])

    print(f"  Export CSV → {output_path}  ({len(chunks)} chunks)")
    return output_path


def split_documents_with_context(
    documents: "List",
    use_llm_context: bool = False,
) -> "List":
    """แบ่งเอกสารเป็น chunks พร้อม context + knowledge_type label

    Pipeline: documents → split → add_context_to_chunk (ทุก chunk) → export CSV

    Args:
        documents: Document list จาก step1_data_loader
        use_llm_context: True = LLM classify+context (ดีกว่า แต่ช้า)
                         False = keyword classify + simple context (เร็ว)

    Returns:
        chunks พร้อม metadata["knowledge_type"] และ context นำหน้า
    """
    # --- สร้าง LLM ครั้งเดียว (ไม่สร้างใหม่ทุก chunk) ---
    llm_instance = None
    if use_llm_context:
        print(f"  กำลังเชื่อมต่อ LLM: {LLM_PROVIDER}/{LLM_MODEL_NAME}  temp={CONTEXTUAL_TEMPERATURE}...", flush=True)
        llm_instance = get_contextual_llm()
        print(f"  LLM พร้อมแล้ว")
    else:
        print(f"  Classify: keyword-based (ไม่ใช้ LLM)")

    # --- แบ่ง chunks ---
    # ใช้ splitter ของเราเองแทน langchain_text_splitters เพื่อหลีกเลี่ยง
    # transformers dependency ที่ทำให้ import ช้า 20+ วินาที
    text_splitter = _RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_CONFIG["chunk_size"],
        chunk_overlap=CHUNK_CONFIG["chunk_overlap"],
        separators=CHUNK_CONFIG["separators"],
    )
    print(f"  กำลังแบ่ง chunks จาก {len(documents)} เอกสาร...", end="", flush=True)
    chunks = text_splitter.split_documents(documents)
    print(f" ได้ {len(chunks)} chunks  (size={CHUNK_CONFIG['chunk_size']}, overlap={CHUNK_CONFIG['chunk_overlap']})")

    total = len(chunks)
    loop_start = time.time()
    contextual_chunks: list = []

    print(f"  เริ่ม {'LLM context + classify' if use_llm_context else 'keyword classify'} ({total} chunks)...\n")

    for i, chunk in enumerate(chunks):
        source = chunk.metadata.get("source", "Unknown")
        document_title = source.split("/")[-1] if "/" in source else source.split("\\")[-1]

        if use_llm_context:
            print(f"  [{i+1:>{len(str(total))}}/{total}] {document_title:<35}", end="", flush=True)
            chunk_start = time.time()
            contextual_chunks.append(add_context_to_chunk(chunk, document_title, use_llm=True, llm=llm_instance))
            kt = contextual_chunks[-1].metadata.get("knowledge_type", "?")
            print(f"→ {kt:<18} ({time.time() - chunk_start:.1f}s)")

            if (i + 1) % 10 == 0:
                elapsed = time.time() - loop_start
                eta = elapsed / (i + 1) * (total - i - 1)
                m, s = divmod(int(eta), 60)
                print(f"  {'─' * 62}")
                print(f"  Progress {i+1}/{total}  |  Elapsed {elapsed:.0f}s  |  ETA ~{m}m{s:02d}s")
                print(f"  {'─' * 62}")
        else:
            contextual_chunks.append(add_context_to_chunk(chunk, document_title, use_llm=False))
            if (i + 1) % 100 == 0 or (i + 1) == total:
                elapsed = time.time() - loop_start
                pct = (i + 1) / total * 100
                print(f"  [{i+1}/{total}] {pct:.0f}%  ({elapsed:.1f}s)", flush=True)

    elapsed_total = time.time() - loop_start
    fs = sum(1 for c in contextual_chunks if c.metadata.get("knowledge_type") == "feng_shui")
    id_ = sum(1 for c in contextual_chunks if c.metadata.get("knowledge_type") == "interior_design")
    bt = sum(1 for c in contextual_chunks if c.metadata.get("knowledge_type") == "both")
    print(f"\n  เสร็จใน {elapsed_total:.1f}s  |  feng_shui={fs}  interior_design={id_}  both={bt}")

    export_chunks_to_csv(contextual_chunks)

    return contextual_chunks


if __name__ == "__main__":
    from step1_data_loader import load_all_documents

    docs = load_all_documents()
    if docs:
        print("\n" + "=" * 80)
        print("ทดสอบ Simple Context + Keyword Classify")
        print("=" * 80)
        chunks_simple = split_documents_with_context(docs, use_llm_context=False)
        print(f"\nตัวอย่าง chunk แรก:")
        print(f"Content: {chunks_simple[0].page_content[:300]}...")
        print(f"Metadata: {chunks_simple[0].metadata}")

        print("\n" + "=" * 80)
        print("ทดสอบ LLM Context + Classify")
        print("=" * 80)
        chunks_llm = split_documents_with_context(docs[:1], use_llm_context=True)
        print(f"\nตัวอย่าง chunk แรก (with LLM):")
        print(f"Content: {chunks_llm[0].page_content[:400]}...")
        print(f"Metadata: {chunks_llm[0].metadata}")
