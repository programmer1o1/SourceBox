from __future__ import annotations

import math
from typing import Iterable, Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional dependency at runtime
    PIL_AVAILABLE = False
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]
else:
    PIL_AVAILABLE = True


def _normalize_rgba(color: Iterable[int]) -> tuple[int, int, int, int]:
    values = list(color)
    if len(values) == 3:
        r, g, b = values
        return int(r), int(g), int(b), 255
    if len(values) == 4:
        r, g, b, a = values
        return int(r), int(g), int(b), int(a)
    raise ValueError("color must be an RGB or RGBA iterable")


def pil_load_image_rgba(path: str, *, flip_y: bool = False) -> Optional[tuple[bytes, int, int]]:
    if not PIL_AVAILABLE:
        return None

    try:
        img = Image.open(path).convert("RGBA")
        if flip_y:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        return img.tobytes(), img.width, img.height
    except Exception:
        return None


def _load_pil_font(font_path: Optional[str], font_size: int):
    if not PIL_AVAILABLE:
        return None

    try:
        if font_path:
            return ImageFont.truetype(font_path, font_size)
    except Exception:
        pass

    try:
        return ImageFont.truetype("DejaVuSans.ttf", font_size)
    except Exception:
        return ImageFont.load_default()


def pil_render_text_rgba(
    text: str,
    *,
    font_path: Optional[str],
    font_size: int,
    color: Iterable[int],
    letter_spacing: int = 0,
    bold: bool = False,
    flip_y: bool = False,
) -> Optional[tuple[bytes, int, int]]:
    if not PIL_AVAILABLE or not text:
        return None

    try:
        font = _load_pil_font(font_path, font_size)
        if font is None:
            return None

        fill = _normalize_rgba(color)

        if letter_spacing and len(text) > 1:
            dummy = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
            draw_dummy = ImageDraw.Draw(dummy)

            if hasattr(font, "getmetrics"):
                ascent, descent = font.getmetrics()
                height = max(1, int(ascent + descent))
            else:
                bbox = draw_dummy.textbbox((0, 0), text, font=font)
                height = max(1, int(bbox[3] - bbox[1]))

            widths: list[int] = []
            for ch in text:
                if hasattr(draw_dummy, "textlength"):
                    w = int(math.ceil(draw_dummy.textlength(ch, font=font)))
                else:
                    bbox = draw_dummy.textbbox((0, 0), ch, font=font)
                    w = int(bbox[2] - bbox[0])
                widths.append(max(1, w))

            width = sum(widths) + int(letter_spacing) * (len(text) - 1)
            if bold:
                width += 1

            img = Image.new("RGBA", (max(1, int(width)), height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            x = 0
            for ch, ch_w in zip(text, widths):
                draw.text((x, 0), ch, font=font, fill=fill)
                if bold:
                    draw.text((x + 1, 0), ch, font=font, fill=fill)
                x += ch_w + int(letter_spacing)
        else:
            dummy = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
            draw_dummy = ImageDraw.Draw(dummy)
            bbox = draw_dummy.textbbox((0, 0), text, font=font)

            width = max(1, int(bbox[2] - bbox[0]) + (1 if bold else 0))
            height = max(1, int(bbox[3] - bbox[1]))

            img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            x = -int(bbox[0])
            y = -int(bbox[1])
            draw.text((x, y), text, font=font, fill=fill)
            if bold:
                draw.text((x + 1, y), text, font=font, fill=fill)

        if flip_y:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)

        return img.tobytes(), img.width, img.height
    except Exception:
        return None
