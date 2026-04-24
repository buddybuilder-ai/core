# BuddyBuilder Core — Layout Engine Documentation

เอกสารภายในสำหรับ layout pipeline ของ BuddyBuilder backend

## สารบัญ

1. [01 — Overview & Architecture](./01-overview.md) — ภาพรวมระบบ, flow จาก user prompt จนถึง 3D scene
2. [02 — Chat Router & Intent Dispatch](./02-chat-router.md) — endpoint `/api/chat/stream`, intent classifier, clarification gate
3. [03 — Pipeline (new_layout)](./03-pipeline.md) — 5-step pipeline สำหรับสร้าง layout ใหม่
4. [04 — Modifier & Rearrange Agents](./04-modifier-rearrange.md) — flow สำหรับแก้ไขชิ้นเดียว / จัดใหม่ทั้งหมด
5. [05 — Spatial Resolver](./05-spatial-resolver.md) — semantic → physical coordinates, bump-out, pair placement
6. [06 — Wall Assigner](./06-wall-assigner.md) — deterministic wall assignment + Kua
7. [07 — Collision & Repair](./07-collision-repair.md) — AABB, shift/rotate algorithms, clearance constants
8. [08 — Feng Shui Rules & Scoring](./08-feng-shui.md) — rule checker logic, scoring formula
9. [09 — Coordinate System](./09-coordinates.md) — Three.js centre-origin, rotation, dimension swap
10. [10 — LLM Prompts & Schemas](./10-llm-prompts.md) — RouterAgent + FengShuiLLMAgent
11. [11 — Data Entities & Catalog](./11-entities-catalog.md) — Room, Placement, FurnitureCatalog
12. [12 — SSE Events Reference](./12-sse-events.md) — event types ทั้งหมดและ payload
13. [13 — Constants Reference](./13-constants.md) — magic numbers ทั้งหมดในที่เดียว

## ใช้ยังไง

- เริ่มที่ [01-overview.md](./01-overview.md) ถ้ายังไม่รู้จักระบบ
- ถ้าจะดีบั๊ก collision → [07-collision-repair.md](./07-collision-repair.md) + [09-coordinates.md](./09-coordinates.md)
- ถ้าจะปรับ LLM behavior → [10-llm-prompts.md](./10-llm-prompts.md)
- ถ้าจะเพิ่ม feng shui rule → [08-feng-shui.md](./08-feng-shui.md)

## หมายเหตุ

- เอกสารนี้ไม่ครอบคลุม RAG system — ดูที่ [core/rag_pipeline/](../rag_pipeline/) แทน
- ใช้ `bd` command สำหรับ task tracking (ไม่ใช้ markdown TODO)
- ค่า path อ้างอิงจาก repo root `/Users/crybabys/Documents/GitHub/BuddyBuilder/`
