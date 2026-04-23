# RAG Pipeline — คู่มืออธิบายโค้ด

> เอกสารนี้อธิบายทุกฟังก์ชันใน `core/rag_pipeline/` แบบละเอียด
> เหมาะสำหรับอ่านประกอบโค้ดหรือเมื่อต้องการเข้าใจก่อนแก้ไข

---

## ภาพรวม Pipeline

```
data/raw/  ──►  step1  ──►  step2*  ──►  step3  ──►  vectorstore/
(ไฟล์ดิบ)    (โหลด)    (แบ่ง chunk)   (embed)    (ChromaDB)
                                                         │
                                            step4b ◄─────┘
                                         (RAG chain + memory)
```

ลำดับการทำงานเมื่อ **build** vectorstore:

| ลำดับ | ไฟล์ | หน้าที่ |
|-------|------|---------|
| 0 | `config.py` | อ่าน `.env` → ตัวแปร config ทั้งหมด |
| 0 | `rag_constants.py` | SYSTEM_PROMPT, keywords, out-of-scope msg |
| 1 | `step1_data_loader.py` | โหลดไฟล์ดิบ → `List[Document]` |
| 2 | `step2_text_splitter.py` | แบ่ง chunk แบบ standard (ไม่มี LLM) |
| 2b | `step2b_contextual_chunking.py` | แบ่ง chunk + เติม context นำหน้า |
| 3 | `step3_vectorstore.py` | embed → บันทึกลง ChromaDB |
| 4b | `step4b_rag_with_memory.py` | RAG chain พร้อม conversation memory (dev/test) |
| — | `main.py` | entry point สำหรับ rebuild vectorstore |
| — | `check_vectordb.py` | ตรวจสอบ/export ข้อมูลใน vectorstore |

---

## `config.py` — ตัวแปร Configuration

ไฟล์นี้ไม่มีฟังก์ชันหลัก แต่เป็นจุดรวมตัวแปรทั้งหมดที่ไฟล์อื่น `import` ไปใช้
อ่านค่าจาก `core/.env` ผ่าน `python-dotenv`

### กลไกเลือก LLM

```python
_LLM_MODEL_RAW = os.getenv("LLM_MODEL", "ollama/qwen2.5:7b")
LLM_PROVIDER, _, LLM_MODEL_NAME = _LLM_MODEL_RAW.partition("/")
```

ตัวแปรเดียวใน `.env` (`LLM_MODEL`) แยก provider กับ model ออกจากกันอัตโนมัติด้วย `/`

| ตัวอย่าง `.env` | `LLM_PROVIDER` | `LLM_MODEL_NAME` |
|----------------|----------------|-----------------|
| `ollama/qwen2.5:7b` | `ollama` | `qwen2.5:7b` |
| `groq/llama-3.3-70b-versatile` | `groq` | `llama-3.3-70b-versatile` |
| `claude/claude-sonnet-4-20250514` | `claude` | `claude-sonnet-4-20250514` |

### ตัวแปรสำคัญ

| ตัวแปร | Default | ความหมาย |
|--------|---------|-----------|
| `TEMPERATURE` | `0.3` | ความ creative ของ LLM (0=ตอบตรง, 1=สร้างสรรค์) |
| `CONTEXTUAL_TEMPERATURE` | `0.2` | Temperature สำหรับ step2b — ต่ำกว่าเพราะต้องการ summary แม่นยำ |
| `RELEVANCE_THRESHOLD` | `0.35` | L2 distance สูงสุดที่ถือว่า "เกี่ยวข้อง" (0=identical, ~1.4=ไม่เกี่ยว) |
| `TOP_K` | `5` | จำนวน chunks ที่ดึงต่อ query |
| `SEARCH_TYPE` | `mmr` | วิธีค้นหา: `mmr` (หลากหลาย) หรือ `similarity` (แม่นยำ) |
| `CHUNK_SIZE` | `1000` | ขนาด chunk (ตัวอักษร) |
| `CHUNK_OVERLAP` | `200` | ส่วนทับซ้อนระหว่าง chunk เพื่อไม่ให้ขาดบริบท |
| `MAX_HISTORY` | `10` | จำนวนรอบสนทนาสูงสุดที่เก็บใน memory |

### `print_config()`

```python
def print_config():
```

แสดงค่า config ทั้งหมดในรูปแบบอ่านง่าย ใช้สำหรับ debug เมื่อสงสัยว่าค่าใดถูกโหลดมาจากไหน
เรียกได้โดยตรง: `python config.py`

---

## `rag_constants.py` — Single Source of Truth

ไม่มีฟังก์ชัน — เป็นไฟล์ constants ล้วนๆ แต่สำคัญมากเพราะ **แก้ที่นี่ที่เดียว มีผลกับทั้งระบบ**

### `SYSTEM_PROMPT`

บุคลิกและกฎการตอบของ AI ทั้งหมดอยู่ในนี้ ประกอบด้วย:

- **สูตรคำนวณเลขกัว (Ming Gua)**: ขั้นตอนทีละขั้น พร้อมตารางทิศมงคล 8 กัว  
  ใส่ไว้ใน prompt เพราะต้องการให้ LLM คำนวณเองได้ถูกต้องแม้ไม่มี context จาก vectorstore
- **กฎเหล็ก 8 ข้อ**: ห้ามปัดความรับผิดชอบ, ห้าม hallucinate กัว, ห้ามพูดเรื่องวิญญาณ, ฯลฯ
- **รูปแบบการตอบ**: ต่างกันสำหรับคำถามทั่วไป vs คำถามคำนวณกัว

### `MODE_ADDITIONS`

```python
MODE_ADDITIONS: dict[str, str] = { "mentor": "...", "buddy": "...", "fun": "..." }
```

ส่วนเพิ่มเติมที่ append ต่อท้าย `SYSTEM_PROMPT` เมื่อ frontend ส่ง mode มา
แต่ละ mode ปรับน้ำเสียงโดยไม่เปลี่ยนความถูกต้องของข้อมูล:
- `mentor` — อาจารย์ อธิบายหลักการ
- `buddy` — เพื่อนสนิท กระชับ
- `fun` — สนุก มีชีวิตชีวา

### `DOMAIN_KEYWORDS`

```python
DOMAIN_KEYWORDS: list = ["ฮวงจุ้ย", "เกิดปี", "เพศชาย", "ห้องนอน", ...]
```

รายการคำที่ระบบถือว่า "อยู่ใน scope" — ใช้ใน **Layer 1** ของ relevance check
ถ้าคำถามมีคำใดคำหนึ่งในนี้ → ผ่าน Layer 1 แล้วไปตรวจ Layer 2 (similarity score)

> หมายเหตุ: รวม `"เกิดปี"`, `"เพศชาย"`, `"เพศหญิง"`, `"kua"` เพราะ user ถามเรื่องกัวโดยไม่พูดว่า "ฮวงจุ้ย" เลย

### `BEDROOM_KEYWORDS`

คำที่ยืนยันว่าคำถามพูดถึง "ห้องนอน" จริงๆ ใช้คู่กับ `EXCLUDE_KEYWORDS`
ถ้าคำถามมี EXCLUDE_KEYWORD แต่ **ไม่มี** BEDROOM_KEYWORD → block ก่อน Layer 1

### `EXCLUDE_KEYWORDS`

ห้องที่ไม่ใช่ห้องนอน เช่น `"ห้องนั่งเล่น"`, `"ออฟฟิศ"`, `"office"`
รวม loanword และ English variants ที่ user มักพิมพ์แทน "ห้องทำงาน"

### `OUT_OF_SCOPE_MSG`

ข้อความตอบกลับเมื่อคำถามผ่าน relevance check ไม่ได้
แก้ที่นี่ที่เดียว ข้อความปรากฏเหมือนกันทั้งใน dev (step4b) และ production (rag_service)

---

## `step1_data_loader.py` — โหลดข้อมูลดิบ

### `_normalize_text(text)`

```python
def _normalize_text(text: str) -> str:
```

แปลง line endings ให้เป็น `\n` เสมอ  
Windows ใช้ `\r\n`, Mac เก่าใช้ `\r`, Unix ใช้ `\n` — ถ้าไม่ normalize จะเกิด chunk ที่มี `\r` อยู่ข้างในซึ่งทำให้ embedding ต่างกัน

### `_format_val(val)`

```python
def _format_val(val) -> str:
```

แปลงค่าจาก Excel เป็น string แบบ consistent
ปัญหา: Excel อ่านตัวเลขจำนวนเต็มเป็น float เช่น `1.0` บน Windows, `1` บน Mac
วิธีแก้: ถ้าค่าเป็น `float` และเป็นจำนวนเต็ม → แปลงเป็น `int` ก่อน → แล้ว `str`

### `load_pdf(file_path)`

```python
def load_pdf(file_path: str) -> List[Document]:
```

ใช้ `PyPDFLoader` จาก LangChain
ลอง decrypt ด้วย `password=""` ก่อน (PDF บางไฟล์ encrypt ด้วย password ว่าง) ถ้าไม่ได้จึง fallback เป็น `PyPDFLoader` ปกติ
กรองหน้าว่างออก (`page_content.strip()`) เพื่อไม่ให้มี chunk เปล่าลง vectorstore

### `load_csv_excel(file_path)`

```python
def load_csv_excel(file_path: str) -> List[Document]:
```

โหลด CSV หรือ Excel และแปลงแต่ละ row เป็น Document หนึ่งชิ้น

**ลำดับ encoding สำหรับ CSV ไทย:**
```
utf-8 → utf-8-sig → cp874 → tis-620 → latin-1
```
ลอง decode ทีละอัน ถ้าล้มเหลวทั้งหมดจึง fallback เป็น `errors="replace"`

**Label Metadata:**
คอลัมน์ใน `LABEL_COLUMNS` (เช่น `category`, `topic_th`, `element_th`) จะถูก copy เป็น metadata ของ Document
ทำให้ใช้ `get_retriever_with_filter()` กรองได้ในภายหลัง เช่น `{"category": "placement"}`

**Excel Multi-sheet:**
โหลดทุก sheet อัตโนมัติ ชื่อ sheet เก็บไว้ใน `metadata["sheet"]`

### `load_text(file_path)`

```python
def load_text(file_path: str) -> List[Document]:
```

โหลด `.txt` หรือ `.md` โดยใช้ `TextLoader` กับ `encoding="utf-8"`
ง่ายที่สุดในบรรดา loaders

### `load_json(file_path)`

```python
def load_json(file_path: str) -> List[Document]:
```

รองรับทั้ง `.json` และ `.jsonl`:
- **JSONL** (JSON Lines): แต่ละบรรทัดคือ JSON object แยกกัน → แปลงเป็น Document ทีละบรรทัด
- **JSON** ปกติ: ถ้า root เป็น list → Document ต่อ item, ถ้าเป็น object → Document เดียว

### `load_all_documents()`

```python
def load_all_documents() -> List[Document]:
```

Entry point หลักของ step 1 — สแกน `data/raw/` แบบ recursive แล้ว dispatch ไปยัง loader ที่เหมาะสมตาม extension:

```
.pdf   → load_pdf()
.csv / .xlsx → load_csv_excel()
.txt / .md   → load_text()
.json / .jsonl → load_json()
```

ไฟล์ที่ extension ไม่รู้จักจะถูกข้ามโดยไม่ error

---

## `step2_text_splitter.py` — Standard Text Splitting

### `split_documents(documents)`

```python
def split_documents(documents: List[Document]) -> List[Document]:
```

แบ่งเอกสารเป็น chunks ด้วย `RecursiveCharacterTextSplitter` โดยไม่มีการ transform เนื้อหา
เป็นวิธีเร็วที่สุดและง่ายที่สุด ใช้เมื่อไม่ต้องการ advanced RAG

**ลำดับ separators:**
```python
separators = ["\n\n", "\n", " ", ""]
```
ตัดที่ย่อหน้าก่อน ถ้าย่อหน้าไหนยาวเกิน `chunk_size` จึงตัดที่ `\n` แล้วค่อยตัดที่ space และตัวอักษรเป็นลำดับสุดท้าย วิธีนี้รักษาประโยคได้ดีกว่าการตัดตามตำแหน่งตัวอักษร

**เมื่อไรควรใช้ step2 แทน step2b/2c:**
- Rebuild ด่วนเมื่อข้อมูลเปลี่ยน
- ทดสอบ pipeline เบื้องต้น
- ไม่มี Ollama/LLM ในเครื่อง

---

## `step2b_contextual_chunking.py` — Contextual Chunking + Knowledge Type Classification

แนวคิดจาก Anthropic "Contextual Retrieval": chunk เดี่ยวๆ มักขาดบริบท
เช่น `"ห้ามวางเตียงตรงกับประตู"` — ไม่รู้ว่าเป็นกฎของอะไร
การเติม context นำหน้าทำให้ embedding จับใจความได้ครบกว่า

> **อัพเดตล่าสุด:** step2b ทำงาน 2 อย่างในครั้งเดียวคือเติม context สรุป **และ** classify `knowledge_type` (`feng_shui` / `interior_design` / `both`) ลงใน metadata — ค่านี้ถูก `/chat/rag` ใช้กรองเอกสารให้ตรง query type

### `_FENG_SHUI_KW` / `_INTERIOR_KW`

Keyword lists สำหรับ classify แบบ keyword-based (ไม่ใช้ LLM) ใช้ใน `_keyword_classify()` และ fallback ของ LLM mode

### `_keyword_classify(text)` *(ใหม่)*

```python
def _keyword_classify(text: str) -> str:
```

Classify `knowledge_type` จาก keyword โดยไม่ใช้ LLM:
- มีทั้งสอง → `"both"`
- มีเฉพาะ interior → `"interior_design"`
- มีเฉพาะ feng shui หรือไม่ชัดเจน → `"feng_shui"` (default เพราะ domain นี้คือ feng shui)

### `_RecursiveCharacterTextSplitter` *(ใหม่)*

Custom text splitter ที่ implement เอง ไม่ใช้ `langchain_text_splitters`
เหตุผล: LangChain text splitter import `transformers` library ทำให้ startup ช้า **20+ วินาที**
Logic เหมือน LangChain ทุกอย่าง: recursive split ตาม `separators = ["\n\n", "\n", " ", ""]` พร้อม overlap

### `get_contextual_llm()`

```python
def get_contextual_llm():
```

สร้าง LLM สำหรับ generate context summary + classify ของแต่ละ chunk
ใช้ `CONTEXTUAL_TEMPERATURE` (default 0.2) ซึ่งต่ำกว่า `TEMPERATURE` ทั่วไป เพราะต้องการ summary แม่นยำ
รองรับ 3 providers: `ollama`, `groq`, `claude`

### `add_context_to_chunk(chunk, document_title, use_llm, llm)` *(อัพเดต)*

```python
def add_context_to_chunk(chunk, document_title: str, use_llm: bool = True, llm=None) -> Document:
```

เพิ่ม context นำหน้า chunk และตั้ง `metadata["knowledge_type"]` พร้อมกัน มี 2 โหมด:

**`use_llm=False` (Simple mode):**
```
เอกสาร: ชื่อไฟล์.csv

<เนื้อหาเดิม>
```
Classify ด้วย `_keyword_classify()` — เร็ว ไม่เรียก LLM เหมาะสำหรับ rebuild ด่วน

**`use_llm=True` (LLM mode):**

LLM prompt ถามพร้อมกัน 2 อย่างในครั้งเดียว (ประหยัด token):
```
บริบท: <สรุป 1-2 ประโยค>
ประเภท: <feng_shui | interior_design | both>
```
Output format นี้ถูก parse แล้วตั้งเป็น `metadata["knowledge_type"]`
ถ้า LLM ไม่ตอบตาม format → fallback เป็น `_keyword_classify()` อัตโนมัติ
ถ้า LLM error → fallback เป็น simple mode ทั้งหมด ไม่หยุด pipeline

**Parameter `llm`:** รับ LLM instance ที่สร้างไว้แล้ว ถ้าไม่ส่งจะสร้างใหม่ทุก chunk (ช้ากว่า)

**Metadata ที่ตั้งค่า:**
| key | ค่า | ความหมาย |
|-----|-----|-----------|
| `knowledge_type` | `feng_shui` / `interior_design` / `both` | ใช้กรองใน `/chat/rag` |
| `has_llm_context` | `True` / `False` | ช่วย debug ว่า chunk ไหนได้ LLM context |

### `export_chunks_to_csv(chunks)` *(ใหม่)*

```python
def export_chunks_to_csv(chunks: List) -> Path:
```

Export chunks ทั้งหมดไปที่ `rag_pipeline/exports/chunks_YYYYMMDD_HHMMSS.csv` อัตโนมัติหลัง split เสร็จ
Columns: `chunk_id`, `source`, `knowledge_type`, `has_llm_context`, `content_preview` (500 ตัวอักษรแรก)
ใช้ `utf-8-sig` ให้ Excel เปิดภาษาไทยได้ถูกต้อง

### `split_documents_with_context(documents, use_llm_context)` *(อัพเดต)*

```python
def split_documents_with_context(documents: List, use_llm_context: bool = False) -> List:
```

Pipeline หลักของ step2b:
1. สร้าง LLM instance **ครั้งเดียว** ก่อนเริ่ม loop (ไม่สร้างใหม่ทุก chunk — เร็วกว่า)
2. แบ่ง documents → chunks ด้วย `_RecursiveCharacterTextSplitter` (custom, ไม่ใช้ LangChain)
3. วนลูปทุก chunk → เรียก `add_context_to_chunk()` พร้อม LLM instance ที่แชร์ร่วมกัน
4. Progress: ทุก 10 chunks (LLM mode) หรือ ทุก 100 chunks (keyword mode)
5. แสดงสถิติ `feng_shui` / `interior_design` / `both` เมื่อเสร็จ
6. เรียก `export_chunks_to_csv()` อัตโนมัติ

**การเรียกใช้:**
```bash
# keyword classify (เร็ว — แนะนำสำหรับ dev)
python main.py --method contextual

# LLM classify + context (แม่นยำกว่า — ต้องมี LLM)
python main.py --method contextual --llm-context
```

---

## `step3_vectorstore.py` — ChromaDB Vector Store

### `get_embeddings()`

```python
def get_embeddings() -> HuggingFaceEmbeddings:
```

สร้าง `HuggingFaceEmbeddings` พร้อม auto-detect device:
1. ตรวจ CUDA (NVIDIA GPU) → แสดงชื่อ GPU และ VRAM
2. ตรวจ MPS (Apple Silicon)
3. Fallback เป็น CPU

**`normalize_embeddings=True`** — สำคัญมาก:
> เมื่อ normalize แล้ว L2 distance กับ cosine similarity มีความหมายเดียวกัน:
> `L2² = 2 × (1 − cosine)`
> ChromaDB ใช้ L2 เป็น default ดังนั้น threshold ใน config คือ L2 distance ไม่ใช่ cosine

| L2 Distance | ความหมาย |
|-------------|---------|
| `0.0` | identical (เหมือนกันทุกบิต) |
| `~0.35` | threshold default (เกี่ยวข้องกัน) |
| `~1.0` | cosine ≈ 0.5 (เกี่ยวข้องน้อย) |
| `~1.41` | orthogonal (ไม่เกี่ยวกันเลย) |

### `create_vectorstore(chunks, force_rebuild)`

```python
def create_vectorstore(chunks: List[Document], force_rebuild: bool = False):
```

สร้างหรือโหลด ChromaDB vectorstore:
- ถ้า path มีอยู่แล้วและ `force_rebuild=False` → โหลดของเดิม (ประหยัดเวลา embedding)
- ถ้า `force_rebuild=True` → ลบ directory เดิมด้วย `shutil.rmtree()` แล้วสร้างใหม่

> **คำเตือน:** ถ้า FastAPI server กำลังเปิดใช้งาน ChromaDB อยู่ การ rebuild จะเกิด `PermissionError: chroma.sqlite3 is being used by another process` — ต้องหยุด server ก่อนเสมอ

### `get_retriever(vectorstore, k, search_type)`

```python
def get_retriever(vectorstore, k: int = TOP_K, search_type: str = SEARCH_TYPE):
```

สร้าง `VectorStoreRetriever` จาก vectorstore

**`search_type="mmr"` (Maximum Marginal Relevance):**
ดึง docs ที่ทั้ง relevant กับ query และหลากหลายจากกัน
ลดการดึง chunks ที่ซ้ำกันจากเอกสารเดียว เพิ่ม coverage ของ context

**`search_type="similarity"`:**
ดึง k อันดับแรกที่ใกล้เคียง query ที่สุดเท่านั้น แม่นยำกว่าแต่อาจซ้ำ

### `get_retriever_with_filter(vectorstore, filters, k, search_type)`

```python
def get_retriever_with_filter(vectorstore, filters: dict, k: int = TOP_K, search_type: str = SEARCH_TYPE):
```

เพิ่ม metadata pre-filter ก่อน similarity search
ใช้เมื่อต้องการค้นใน subset ของ documents เช่น:

```python
# ค้นเฉพาะ chunks ที่มี category="placement"
retriever = get_retriever_with_filter(vs, {"category": "placement"})

# ค้นเฉพาะ topic ห้องนอน
retriever = get_retriever_with_filter(vs, {"topic_th": "ห้องนอน"})
```

metadata เหล่านี้ถูก index ไว้ตอน `load_csv_excel()` ใน step1 (`LABEL_COLUMNS`)

---

## `step4b_rag_with_memory.py` — RAG Chain + Conversation Memory

> ไฟล์นี้ใช้สำหรับ **dev/testing** เท่านั้น
> Production ใช้ `FengShuiRAGService` ใน `core/src/` แทน เพราะ stateless เหมาะกับ FastAPI

**อัพเดตล่าสุด:** `SYSTEM_PROMPT`, `DOMAIN_KEYWORDS`, `OUT_OF_SCOPE_MSG` ย้ายไปอยู่ใน `rag_constants.py` แล้ว — import จากที่นั่นเพื่อให้ dev และ production ใช้ค่าเดียวกัน ไม่ต้อง sync กันเอง `FUZZY_MATCH_THRESHOLD` ก็ import จาก `config.py` แทนที่จะ hardcode

### `get_llm()`

```python
def get_llm():
```

สร้าง LLM ตาม `LLM_PROVIDER` ใน config รองรับ `ollama`, `groq`, `claude`
แต่ละ provider ใช้ parameters ต่างกัน:
- Ollama: `top_p`, `repeat_penalty`, `num_predict` (ควบคุม generation ละเอียดกว่า)
- Groq/Claude: `max_tokens` เท่านั้น (OpenAI-compatible API)

### `format_documents(docs)`

```python
def format_documents(docs: List[Document]) -> str:
```

แปลง list ของ Document เป็น string ที่ LLM อ่านได้ รูปแบบ:
```
[Document 1] (Source: feng_shui_rules.csv)
เนื้อหา...

---

[Document 2] (Source: bedroom_guide.pdf)
เนื้อหา...
```

### `format_chat_history(chat_history)`

```python
def format_chat_history(chat_history: List[Tuple[str, str]]) -> str:
```

แปลง list ของ `(question, answer)` เป็น string สำหรับ prompt
ถ้า history ว่าง → คืน `"[ยังไม่มีประวัติการสนทนา - นี่คือการสนทนาใหม่]"`

### `contains_chinese(text)`

```python
def contains_chinese(text: str) -> bool:
```

ตรวจสอบ Unicode range `U+4E00–U+9FFF` (CJK Unified Ideographs)
ใช้หลัง LLM ตอบเพื่อแจ้งเตือนถ้า model ใส่ตัวอักษรจีนมาทั้งที่ prompt บอกห้าม
ปัญหานี้เกิดบ่อยเมื่อ `TEMPERATURE` สูงเกินไป หรือ model ไม่ follow instruction ดี

---

### `class ConversationRAGChain`

RAG chain แบบ stateful สำหรับ terminal testing เก็บ `chat_history` ไว้ใน object

#### `__init__(retriever, max_history)`

```python
def __init__(self, retriever, max_history: int = MAX_HISTORY):
```

ตั้งค่า chain ทั้งหมดครั้งเดียวตอน startup:

1. สร้าง LLM instance
2. สร้าง prompt template (system → human ที่มี `{chat_history}`, `{context}`, `{question}`)
3. ประกอบ LCEL chain:

```python
chain = {
    "context":      lambda x: format_documents(retriever.invoke(x["question"])),
    "chat_history": lambda x: format_chat_history(x["chat_history"]),
    "question":     lambda x: x["question"]
} | prompt | llm | StrOutputParser()
```

**ลำดับ prompt สำคัญ:** `system` (persona/rules) → `human` ที่มี history + context + question
เพราะ LLM จะรับรู้ system instruction ก่อน แล้วค่อย process context และคำถาม

#### `_fuzzy_match(text, keyword, threshold)`

```python
def _fuzzy_match(self, text: str, keyword: str, threshold: int = None) -> bool:
```

ตรวจสอบคำที่พิมพ์ผิดแบบง่าย — นับตัวอักษรที่ต่างกัน
ตัวอย่าง: `"ฮวงจุ้ย"` match กับ `"ฮวงจุ้ย่"` (พิมพ์ผิด 1 ตัว) ถ้า threshold=1
ตรวจเฉพาะคำยาว >= 4 ตัวอักษร เพราะคำสั้น fuzzy match จะเกิด false positive มาก

#### `_has_domain_keywords(question, check_history)`

```python
def _has_domain_keywords(self, question: str, check_history: bool = True) -> bool:
```

ตรวจสอบ 3 ชั้น:
1. **Exact match**: `keyword in question_lower`
2. **Fuzzy match**: ตรวจคำยาว >= 4 ตัวอักษรว่าพิมพ์ผิดน้อยกว่า threshold หรือไม่
3. **History match**: ถ้าคำถามสั้น (< 15 ตัวอักษร) และ history 2 รอบล่าสุดมี domain keyword → ถือว่าต่อเนื่อง

ชั้นที่ 3 แก้ปัญหาคำถามสั้นๆ เช่น `"แล้วสีอื่นล่ะ?"` ที่ไม่มี domain keyword แต่ชัดเจนว่าต่อจากบทสนทนาเรื่องฮวงจุ้ย

#### `_check_relevance(question)`

```python
def _check_relevance(self, question: str) -> bool:
```

**Layer 1** — Keyword check (เร็ว):
- ถ้าไม่มี domain keyword → reject ทันที ไม่เรียก embedding

**Layer 2** — Similarity score (แม่นยำ):
- Embed คำถาม → ค้นหาใน vectorstore → ดู L2 distance ของ chunk ที่ใกล้ที่สุด
- ถ้า `best_score > RELEVANCE_THRESHOLD` → คำถามไม่ match กับ knowledge base → reject

```
L2 ≤ threshold  →  relevant  →  เรียก LLM
L2 > threshold  →  out of scope  →  คืน OUT_OF_SCOPE_MSG
```

> หมายเหตุ: `step4b` ทำ 2 embedding ต่อ request (check + retrieve)
> Production `rag_service.py` แก้ปัญหานี้โดย return prefetched docs จาก `_check_relevance()` แล้วส่งต่อให้ `_retrieve_context()` ใช้ต่อ

#### `invoke(question)`

```python
def invoke(self, question: str) -> str:
```

Flow ต่อ request:
```
1. _check_relevance()  →  ถ้า False → คืน OUT_OF_SCOPE_MSG ทันที (ประหยัด token)
2. chain.invoke()      →  ดึง docs + format prompt + เรียก LLM
3. contains_chinese()  →  ถ้า True → print warning (ไม่ block)
4. chat_history.append(question, answer)
5. trim history ถ้าเกิน max_history
6. คืน answer
```

#### `clear_history()`

```python
def clear_history(self):
```

ล้าง `chat_history` ทั้งหมด ใช้เมื่อต้องการเริ่มบทสนทนาใหม่ใน terminal

#### `get_history()`

```python
def get_history(self) -> List[Tuple[str, str]]:
```

คืน reference ของ `chat_history` ทั้งหมด (list ของ `(question, answer)` tuple)

---

## `main.py` — Vectorstore Builder Entry Point

### `main()`

```python
def main():
```

Entry point สำหรับ rebuild vectorstore ผ่าน CLI:

```bash
# สร้างใหม่ด้วย contextual chunking (default)
python main.py --rebuild

# เลือก method
python main.py --rebuild --method standard       # เร็วสุด ไม่ transform
python main.py --rebuild --method contextual     # เติม context (แนะนำ)

# contextual + LLM summary (ดีสุด แต่ต้องมี LLM)
python main.py --rebuild --method contextual --llm-context
```

**Logic:**
```
มี vectorstore อยู่แล้ว + ไม่มี --rebuild  → แสดงข้อความ skip
มี --rebuild หรือไม่มี vectorstore           → โหลด → แบ่ง → embed
```

---

## `check_vectordb.py` — ตรวจสอบ ChromaDB

เครื่องมือสำหรับ debug vectorstore แบบ interactive ไม่มีผลต่อข้อมูล

### `print_separator(char, width)`

```python
def print_separator(char: str = "=", width: int = 80) -> None:
```

พิมพ์เส้นคั่น `char * width` ช่วยจัดรูปแบบ output ใน terminal

### `export_to_csv(all_docs, all_metas, output_path)`

```python
def export_to_csv(all_docs: list, all_metas: list, output_path: Path) -> None:
```

Export chunks ทั้งหมดเป็น CSV สำหรับตรวจสอบใน Excel
columns: `chunk_index`, `source`, `size_chars`, `content`
ใช้ `encoding="utf-8-sig"` เพราะ Excel บน Windows ต้องการ BOM signature เพื่อแสดงภาษาไทยได้ถูกต้อง

### `export_to_json(all_docs, all_metas, sizes, buckets, sources, output_path)`

```python
def export_to_json(..., output_path: Path) -> None:
```

Export chunks พร้อม metadata และสถิติรวมเป็น JSON ไฟล์เดียว โครงสร้าง:
```json
{
  "exported_at": "2025-...",
  "total_chunks": 300,
  "stats": { "min_chars": 150, "max_chars": 1200, "avg_chars": 650 },
  "size_distribution": { "< 200 chars": 5, "200-500 chars": 80, ... },
  "sources": { "feng_shui.csv": { "chunks": 200, "avg_chars": 600 } },
  "chunks": [ { "index": 1, "source": "...", "size_chars": 700, "content": "..." } ]
}
```

### `check_vectordb()`

```python
def check_vectordb() -> None:
```

Interactive tool หลัก — รันด้วย `python check_vectordb.py` แล้วตอบ prompt:

**1. สถิติ Chunk Sizes** — แสดง min/max/avg และ histogram แบบ ASCII bar chart:
```
< 200 chars  (เล็กมาก)      5 chunks ( 1.6%) █
200–500 chars (เล็ก)       80 chunks (26.7%) █████████████
500–800 chars (กลาง)      120 chunks (40.0%) ████████████████████
800–1000 chars (ดี)        70 chunks (23.3%) ███████████
> 1000 chars (ใหญ่)        25 chunks ( 8.3%) ████
```

**2. สรุปแหล่งที่มา** — breakdown ต่อไฟล์ (จำนวน chunks, avg/min/max size)

**3. ตัวอย่าง Chunks** — เลือกจำนวน หรือ `all` เพื่อดูทั้งหมด
เลือก chunks กระจายทั่ว DB (ไม่ใช่แค่ตั้งแต่ต้น) โดยคำนวณ `step = len(docs) // sample_n`

**4. Export** — `csv` / `json` / `both` / Enter=ข้าม
บันทึกไว้ที่ `rag_pipeline/exports/chunks_<timestamp>.csv|json`

**5. Similarity Search ทดสอบ** — พิมพ์คำถาม ดูผลลัพธ์พร้อม L2 distance score
วนลูปจนกว่าจะกด Enter เพื่อออก

---

## การไหลของข้อมูลระหว่างไฟล์

```
.env
 │
 ▼
config.py ──────────────────────────────────────────────────────┐
 │                                                              │
 │   rag_constants.py (SYSTEM_PROMPT, keywords)                 │
 │          │                                                   │
 ▼          ▼                                                   │
step1_data_loader.py                                            │
  └── load_all_documents() → List[Document]                     │
          │                                                     │
          ▼                                                     │
   (เลือก 1 อย่าง)                                              │
   step2_text_splitter.py      ─── split_documents()            │
   step2b_contextual_chunking.py ─ split_documents_with_context()│
          │                                                     │
          ▼                                                     │
step3_vectorstore.py                                            │
  ├── get_embeddings()        ← EMBEDDING_MODEL ◄───────────────┤
  ├── create_vectorstore()    ← CHROMA_DB_PATH  ◄───────────────┤
  └── get_retriever()         ← TOP_K, SEARCH_TYPE ◄────────────┤
          │                                                     │
          ▼                                                     │
step4b_rag_with_memory.py (dev) ◄── RELEVANCE_THRESHOLD ◄───────┘
  └── ConversationRAGChain
        ├── _check_relevance()  → Layer 1 (keywords) + Layer 2 (L2)
        └── invoke()            → LLM → answer

          │  (production path)
          ▼
src/modules/layout/application/services/rag_service.py
  └── FengShuiRAGService  (stateless — ใช้ใน FastAPI)
        ├── ask()          → (answer, source_docs)
        └── ask_stream()   → yields ("delta"|"final", text, sources)
                │
                ▼
src/api/v1/chat/router.py  POST /chat/rag
  └── event_generator()   → SSE stream
        ├── "delta" → event: answer_delta\ndata: {"type":"answer_delta","delta":"..."}
        └── "final" → event: answer\ndata: {"type":"answer","answer":"...","source_documents":[...]}
```

---

---

## API Integration — `POST /chat/rag`

> endpoint นี้เป็น **production path** ของ RAG pipeline เชื่อมต่อ `FengShuiRAGService` เข้ากับ frontend ผ่าน SSE streaming

### ที่อยู่ไฟล์

```
core/src/api/v1/chat/router.py  (function: chat_rag_only)
```

### Flow การทำงาน

```
POST /chat/rag  ← { message, mode, conversation_history }
       │
       ▼
FengShuiRAGService.ask_stream()
       │
       ├── yield ("delta", token, None)   ──►  event: answer_delta
       │                                        data: {"type":"answer_delta","delta":"..."}
       │
       └── yield ("final", answer, docs)  ──►  event: answer
                                                data: {"type":"answer","answer":"...","source_documents":[...]}
```

### SSE Event Format

endpoint นี้ format SSE inline โดยตรง **ไม่ import จาก layout module** เพื่อให้ RAG pipeline เป็น independent module:

```python
def _sse(event: str, **data) -> str:
    payload = json.dumps({"type": event, **data})
    return f"event: {event}\ndata: {payload}\n\n"
```

| Event | เมื่อไร | Fields ใน data |
|-------|---------|----------------|
| `answer_delta` | ทุก token chunk ที่ stream มา | `type`, `delta` |
| `answer` | ตอบสุดท้ายหลัง stream จบ | `type`, `answer`, `source_documents` |

### ข้อแตกต่างจาก `/chat/stream`

| | `/chat/rag` | `/chat/stream` |
|--|-------------|----------------|
| Intent routing | ไม่มี — ตอบตรงทันที | ผ่าน RouterAgent ก่อน |
| Layout pipeline | ไม่เกี่ยวข้อง | trigger ได้ถ้า intent = new_layout |
| SSE events | `answer_delta`, `answer` เท่านั้น | มี event type ครบ (pipeline, steps, modifier ฯลฯ) |
| ใช้สำหรับ | หน้า Chatbot ฮวงจุ้ย | หน้า Room Builder |

---

## คำถามที่พบบ่อย

**Q: เปลี่ยน LLM ต้องแก้ไฟล์ไหน?**
A: แก้แค่ `.env` บรรทัด `LLM_MODEL=provider/model-name` ไม่ต้องแก้โค้ด

**Q: เพิ่ม keyword ใหม่ใน scope ต้องทำอะไร?**
A: เพิ่มใน `rag_constants.py` ที่ `DOMAIN_KEYWORDS` — ไม่ต้อง rebuild vectorstore

**Q: คำถาม X ถูก reject ทั้งที่ควรตอบได้ — debug ยังไง?**
A: ดู log ที่ terminal:
  - `Keyword check: Not found` → เพิ่มคำใน `DOMAIN_KEYWORDS`
  - `Similarity score: 1.2 (threshold: 0.35)` → เพิ่ม `RELEVANCE_THRESHOLD` ใน `.env` หรือ rebuild vectorstore ด้วยข้อมูลที่ครอบคลุมกว่า

**Q: Rebuild vectorstore นานแค่ไหน?**
A: ขึ้นกับ method และ hardware:
  - `--method standard` (CPU): ~1 นาทีต่อ 1000 chunks
  - `--method contextual` (CPU): ~2 นาทีต่อ 1000 chunks (embedding เท่ากัน ต่างกันที่เตรียมข้อมูล)
  - `--method contextual --llm-context` (+ Ollama): นานกว่ามาก (เรียก LLM ทุก chunk)
  - GPU: เร็วกว่า CPU ~5-10x ในขั้นตอน embedding

**Q: ทำไม vectorstore ที่ rebuild แล้วยังตอบผิด?**
A: ตรวจสอบด้วย `python check_vectordb.py` → ดู source distribution — ถ้าไฟล์ใดไฟล์หนึ่งมี chunk > 50% อาจทำให้ L2 distance bias ไปทาง topic นั้น
