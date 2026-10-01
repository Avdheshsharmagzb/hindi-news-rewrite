"""AI image generation + watermarking for गाजियाबाद टाइम्स.

- If a source photo exists, re-render it with Gemini Nano Banana (image edit) so
  the output is an original, transformed, copyright-safe image.
- If no source photo, generate a fresh editorial image from the Hindi headline.
- A light, centered semi-transparent "गाजियाबाद टाइम्स" watermark is burned onto
  every generated image. Output is saved under generated_media/ and served via
  GET /api/media/{name}.
"""
import os
import io
import base64
import uuid
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

BRAND = "गाजियाबाद टाइम्स"
NANO_MODEL = "gemini-3.1-flash-image-preview"
UA = "Mozilla/5.0 (compatible; EditorialNewsroomBot/1.0)"

ROOT = Path(__file__).parent
MEDIA_DIR = ROOT / "generated_media"
MEDIA_DIR.mkdir(exist_ok=True)
FONT_PATH = ROOT / "assets" / "NotoSerifDevanagari-Bold.ttf"

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")


def _api_key():
    return os.environ.get("EMERGENT_LLM_KEY")


def _headline_prompt(headline, category):
    return (
        "Create a realistic, high-quality editorial news photograph suitable for a "
        f"newspaper article in the '{category}' section. The scene should visually "
        f"represent this Hindi news headline: \"{headline}\". "
        "Photojournalistic style, natural lighting, sharp focus, 16:9 framing. "
        "Do NOT render any text, caption, watermark, logo or source branding in the image."
    )


EDIT_PROMPT = (
    "Re-render this news photo as a brand-new, original, high-quality photojournalistic image. "
    "Keep the same general subject and scene, but change the composition, camera angle, lighting "
    "and fine details enough that it is clearly a new, transformed image (not a copy). "
    "Do NOT include any text, caption, watermark, logo or source branding."
)


async def _nano_banana(prompt, ref_bytes=None):
    chat = LlmChat(
        api_key=_api_key(),
        session_id=f"img-{uuid.uuid4()}",
        system_message="You are a professional photo editor for a news agency.",
    ).with_model("gemini", NANO_MODEL).with_params(modalities=["image", "text"])

    if ref_bytes:
        b64 = base64.b64encode(ref_bytes).decode("utf-8")
        msg = UserMessage(text=prompt, file_contents=[ImageContent(b64)])
    else:
        msg = UserMessage(text=prompt)

    _, images = await chat.send_message_multimodal_response(msg)
    if not images:
        raise RuntimeError("No image returned from Nano Banana")
    return base64.b64decode(images[0]["data"])


async def _download(url):
    async with httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": UA}) as c:
        r = await c.get(url, timeout=25.0)
        r.raise_for_status()
        return r.content


def _add_watermark(img_bytes, position="center", opacity=30):
    base = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    W, H = base.size
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    opacity = max(5, min(100, int(opacity)))
    alpha = int(opacity / 100 * 255)

    if position == "center":
        font_size = max(30, W // 11)
        font = ImageFont.truetype(str(FONT_PATH), font_size, layout_engine=ImageFont.Layout.RAQM)
        tmp = ImageDraw.Draw(overlay)
        bbox = tmp.textbbox((0, 0), BRAND, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = font_size // 2
        txt_img = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
        td = ImageDraw.Draw(txt_img)
        td.text((pad + 2, pad + 2), BRAND, font=font, fill=(0, 0, 0, max(20, alpha // 2)))
        td.text((pad, pad), BRAND, font=font, fill=(255, 255, 255, alpha))
        txt_img = txt_img.rotate(28, expand=1)
        overlay.alpha_composite(txt_img, ((W - txt_img.width) // 2, (H - txt_img.height) // 2))
    else:
        font_size = max(20, W // 24)
        font = ImageFont.truetype(str(FONT_PATH), font_size, layout_engine=ImageFont.Layout.RAQM)
        cd = ImageDraw.Draw(overlay)
        cbbox = cd.textbbox((0, 0), BRAND, font=font)
        cw, ch = cbbox[2] - cbbox[0], cbbox[3] - cbbox[1]
        margin = max(14, W // 55)
        if position == "bottom-left":
            x0 = margin
        else:  # bottom-right (default corner)
            x0 = W - cw - margin * 3
        y0 = H - ch - margin * 3
        cd.rectangle([x0 - margin, y0 - margin, x0 + cw + margin, y0 + ch + margin + ch // 3],
                     fill=(0, 0, 0, min(140, alpha + 40)))
        cd.text((x0, y0), BRAND, font=font, fill=(255, 255, 255, min(255, alpha + 120)))

    out = Image.alpha_composite(base, overlay).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=88)
    return buf.getvalue()


async def create_watermarked_image(headline, category, original_image_url=None, position="center", opacity=30):
    """Returns the API path (e.g. /api/media/xxxx.jpg) of the watermarked image."""
    raw = None
    if original_image_url:
        try:
            ref = await _download(original_image_url)
            raw = await _nano_banana(EDIT_PROMPT, ref_bytes=ref)
        except Exception:
            raw = None
    if raw is None:
        raw = await _nano_banana(_headline_prompt(headline, category))

    watermarked = _add_watermark(raw, position=position, opacity=opacity)
    name = f"{uuid.uuid4().hex}.jpg"
    (MEDIA_DIR / name).write_bytes(watermarked)
    return f"/api/media/{name}"
