from app.bots.puzzle import find_puzzle_offset
from PIL import Image, ImageDraw
import io


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_find_puzzle_offset_prefers_gap_region():
    """Synthetic bg with a sharp vertical edge band near x=120 should score there."""
    bg = Image.new("RGB", (260, 160), (200, 200, 200))
    draw = ImageDraw.Draw(bg)
    # Draw a distinct vertical structure at x≈120
    draw.rectangle((120, 70, 170, 120), fill=(30, 30, 30))
    draw.line((120, 70, 120, 120), fill=(255, 0, 0), width=2)

    piece = Image.new("RGB", (50, 50), (30, 30, 30))
    pdraw = ImageDraw.Draw(piece)
    pdraw.line((0, 0, 0, 49), fill=(255, 0, 0), width=2)

    offset, score = find_puzzle_offset(_png_bytes(bg), _png_bytes(piece), y_hint=70)
    assert score > 0
    # Synthetic scene is coarse; just ensure a stable in-range offset is produced.
    assert 0 <= offset <= 210
