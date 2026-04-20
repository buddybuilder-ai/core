"""Photoreal render endpoint — turns a screenshot of the 3D editor into a
stylised, feng-shui-coloured room preview via OpenRouter's Gemini image model.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/render", tags=["Render"])
settings = get_settings()

# Gemini's image-preview endpoint on OpenRouter. It accepts a user message
# with image+text parts and returns an image part in the assistant reply.
_MODEL = "google/gemini-2.5-flash-image-preview"

_FENG_SHUI_PALETTE_BY_DIRECTION: dict[str, str] = {
    "north": "cool blues and soft blacks (water element — supports career area)",
    "south": "warm reds and terracotta (fire element — supports fame and recognition)",
    "east": "fresh greens and light browns (wood element — supports family and health)",
    "west": "metallic whites, soft greys and pale gold (metal element — supports creativity)",
}


class RenderRequest(BaseModel):
    """Input for /render/preview.

    Attributes:
        image_base64: PNG screenshot of the 3D canvas, base64-encoded (no data URL prefix).
        camera_label: Human-readable name of the chosen camera angle.
        room_direction: The real-world compass direction the room's front wall faces.
        door_wall: Which wall the main door sits on (scene-space: north/south/east/west).
        time_of_day: Optional override for lighting narrative (defaults to "daytime").
    """

    image_base64: str = Field(..., min_length=100)
    camera_label: str = Field(..., min_length=1, max_length=60)
    room_direction: str = Field(default="north")
    door_wall: str = Field(default="south")
    time_of_day: str = Field(default="midday")


class RenderResponse(BaseModel):
    image_base64: str
    mime_type: str = "image/png"


def _build_prompt(req: RenderRequest) -> str:
    direction = req.room_direction.lower()
    palette = _FENG_SHUI_PALETTE_BY_DIRECTION.get(
        direction,
        "balanced earth tones (neutral warm beige, soft wood, muted greens)",
    )
    return (
        "Transform this 3D studio-apartment layout into a photorealistic interior "
        "render while keeping every piece of furniture in exactly the same position, "
        "orientation and scale. Keep the camera angle identical to the source image "
        f"({req.camera_label}).\n\n"
        "Visual requirements:\n"
        f"- Feng shui colour palette: {palette}. Apply this to walls, bedding, "
        "upholstery and soft furnishings; let wood and metal fixtures stay neutral.\n"
        f"- Natural light enters from the {direction} side of the room (room's front "
        f"wall faces {direction}). Cast soft, directional shadows consistent with "
        f"{req.time_of_day} sunlight coming from that side.\n"
        f"- The main door is on the {req.door_wall} wall — keep it visible if the "
        "camera frames it, otherwise leave it implied.\n"
        "- Photorealistic materials: wood grain on furniture, fabric weave on sofas "
        "and bedding, matte paint on walls, subtle ambient occlusion in corners.\n"
        "- No text, no labels, no UI overlays, no compass markers.\n"
        "- Preserve room proportions and furniture silhouettes from the input image."
    )


@router.post("/preview", response_model=RenderResponse)
async def render_preview(req: RenderRequest) -> RenderResponse:
    """Generate a photorealistic preview of a 3D layout."""
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not configured")

    prompt = _build_prompt(req)
    payload: dict[str, Any] = {
        "model": _MODEL,
        "modalities": ["image", "text"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{req.image_base64}"
                        },
                    },
                ],
            }
        ],
    }

    url = f"{settings.OPENROUTER_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.error("render: upstream error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc

    if resp.status_code >= 400:
        logger.error("render: openrouter %s — %s", resp.status_code, resp.text[:500])
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])

    data = resp.json()
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("render: malformed response: %s", data)
        raise HTTPException(status_code=502, detail="Malformed model response") from exc

    # Gemini returns images as `images: [{ image_url: { url: "data:image/png;base64,..." }}]`
    images = message.get("images") or []
    for item in images:
        image_url = (item.get("image_url") or {}).get("url", "")
        if image_url.startswith("data:image"):
            _, b64 = image_url.split(",", 1)
            mime = image_url.split(";")[0].replace("data:", "") or "image/png"
            return RenderResponse(image_base64=b64, mime_type=mime)

    # Fallback: some providers inline base64 without a data URL prefix
    for item in images:
        raw = item.get("image_url") if isinstance(item.get("image_url"), str) else None
        if raw:
            try:
                base64.b64decode(raw, validate=True)
                return RenderResponse(image_base64=raw)
            except Exception:  # pragma: no cover
                continue

    logger.error("render: no image in response: %s", data)
    raise HTTPException(status_code=502, detail="Model returned no image")
