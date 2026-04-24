"""
Step 1: Data Loader
โหลดไฟล์ Dataset จาก data/raw/ (PDF, CSV, XLSX, TXT, MD, JSON, JSONL)
"""
import os
from pathlib import Path
from typing import List


DATA_RAW_PATH = Path(__file__).parent / "data" / "raw"


def _normalize_text(text: str) -> str:
    """Normalize line endings ให้เป็น \n เสมอ (แก้ความต่างระหว่าง Mac/Windows)"""
    return text.replace('\r\n', '\n').replace('\r', '\n').strip()


def _format_val(val) -> str:
    """แปลงค่าจาก Excel เป็น string แบบ consistent (แก้ 1.0 vs 1 ระหว่าง platform)"""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))  # 1.0 → "1"
    return str(val)


def load_pdf(file_path: str) -> "List[Document]":
    """โหลดไฟล์ PDF พร้อม normalize line endings
    รองรับ PDF ที่เข้ารหัส (encrypted) — ลอง decrypt ด้วย password ว่างก่อน
    """
    from langchain_community.document_loaders import PyPDFLoader
    try:
        loader = PyPDFLoader(file_path, password="")
        docs = loader.load()
    except Exception:
        loader = PyPDFLoader(file_path)
        docs = loader.load()

    docs = [doc for doc in docs if doc.page_content.strip()]
    for doc in docs:
        doc.page_content = _normalize_text(doc.page_content)
    return docs


# คอลัมน์ที่จะดึงมาเป็น label metadata
LABEL_COLUMNS = [
    "category", "topic_th", "topic_id", "group_th", "group_en",
    "element_th", "element_en", "check_type", "furniture_involved"
]


def load_csv_excel(file_path: str) -> "List[Document]":
    """โหลดไฟล์ CSV หรือ Excel พร้อม label metadata จากคอลัมน์ที่กำหนด"""
    import pandas as pd
    from langchain_core.documents import Document
    docs = []

    if file_path.endswith(".csv"):
        # ลอง encoding ที่พบบ่อยในไฟล์ภาษาไทย
        for encoding in ("utf-8", "utf-8-sig", "cp874", "tis-620", "latin-1"):
            try:
                df = pd.read_csv(file_path, encoding=encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            df = pd.read_csv(file_path, encoding="utf-8", errors="replace")
        sheets = {"Sheet1": df}
    else:
        xl = pd.ExcelFile(file_path)
        sheets = {name: xl.parse(name) for name in xl.sheet_names}

    for sheet_name, df in sheets.items():
        for idx, row in df.iterrows():
            content = _normalize_text("\n".join([
                f"{col}: {_format_val(val)}" for col, val in row.items() if pd.notna(val)
            ]))
            metadata = {"source": file_path, "row": int(idx), "sheet": sheet_name}
            for col in LABEL_COLUMNS:
                if col in df.columns and pd.notna(row.get(col)):
                    metadata[col] = _format_val(row[col])
            docs.append(Document(page_content=content, metadata=metadata))

    return docs


def load_text(file_path: str) -> "List[Document]":
    """โหลดไฟล์ TXT หรือ MD"""
    from langchain_community.document_loaders import TextLoader
    loader = TextLoader(file_path, encoding="utf-8")
    return loader.load()


def load_json(file_path: str) -> "List[Document]":
    """โหลดไฟล์ JSON หรือ JSONL"""
    import json
    from langchain_core.documents import Document

    docs = []
    with open(file_path, "r", encoding="utf-8") as f:
        if file_path.endswith(".jsonl"):
            for line in f:
                data = json.loads(line)
                content = json.dumps(data, ensure_ascii=False, indent=2)
                docs.append(Document(page_content=content, metadata={"source": file_path}))
        else:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    content = json.dumps(item, ensure_ascii=False, indent=2)
                    docs.append(Document(page_content=content, metadata={"source": file_path}))
            else:
                content = json.dumps(data, ensure_ascii=False, indent=2)
                docs.append(Document(page_content=content, metadata={"source": file_path}))
    return docs


def load_all_documents() -> "List[Document]":
    """โหลดเอกสารทั้งหมดจาก data/raw/"""
    all_docs = []

    if not DATA_RAW_PATH.exists():
        print(f"  ไม่พบโฟลเดอร์ {DATA_RAW_PATH}")
        return all_docs

    files = list(DATA_RAW_PATH.rglob("*"))

    for file_path in files:
        if file_path.is_file():
            file_str = str(file_path)
            try:
                if file_path.suffix == ".pdf":
                    print(f" โหลด PDF: {file_path.name}")
                    all_docs.extend(load_pdf(file_str))

                elif file_path.suffix in [".csv", ".xlsx"]:
                    print(f" โหลด CSV/Excel: {file_path.name}")
                    all_docs.extend(load_csv_excel(file_str))

                elif file_path.suffix in [".txt", ".md"]:
                    print(f" โหลด Text: {file_path.name}")
                    all_docs.extend(load_text(file_str))

                elif file_path.suffix in [".json", ".jsonl"]:
                    print(f" โหลด JSON: {file_path.name}")
                    all_docs.extend(load_json(file_str))

            except (OSError, ValueError, UnicodeDecodeError, RuntimeError) as e:
                print(f" ไม่สามารถโหลด {file_path.name}: {e}")

    print(f"\n โหลดเอกสารทั้งหมด: {len(all_docs)} documents")
    return all_docs


if __name__ == "__main__":
    docs = load_all_documents()
    if docs:
        print(f"\nตัวอย่างเอกสารแรก:")
        print(f"Content: {docs[0].page_content[:200]}...")
        print(f"Metadata: {docs[0].metadata}")
