"""One-shot helper to (re)generate the multi-resolution .ico/.icns
icons used by the PyInstaller builds.  Re-run this any time
``assets/sprites/logo1.png`` changes.

The source PNG is a pixel-art-style logo with transparent margins.
We:
  1. Crop transparent borders so the artwork fills the canvas;
  2. Square-pad with a tiny breathing margin;
  3. For small ICO entries (≤64 px) downsample with a *box* filter then
     sharpen — LANCZOS alone makes pixel art look soft;
  4. For large entries (≥128 px) use LANCZOS for smooth strokes;
  5. Save every ICO sub-image as a 32-bit PNG entry (Vista+ format,
     small + lossless), and the master at the natural source size.

Windows Explorer aggressively caches per-file icons, so after a
rebuild you may need to either rename the new .exe, run
``ie4uinit.exe -show``, or reboot to see the change.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "sprites" / "logo1.png"
ICO = ROOT / "assets" / "icon.ico"
ICNS = ROOT / "assets" / "icon.icns"

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def _crop_to_content(img: Image.Image, alpha_threshold: int = 8) -> Image.Image:
    """Trim transparent borders so the visible artwork fills the frame."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    alpha = img.split()[-1]
    mask = alpha.point(lambda v: 255 if v > alpha_threshold else 0)
    bbox = mask.getbbox()
    return img.crop(bbox) if bbox else img


def _square_pad(img: Image.Image, margin_frac: float = 0.02) -> Image.Image:
    """Centre the image on a transparent square canvas."""
    w, h = img.size
    side = max(w, h)
    margin = int(side * margin_frac)
    side += margin * 2
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
    return canvas


def _high_quality_resize(img: Image.Image, size: int) -> Image.Image:
    """Per-size pipeline tuned for pixel-art-style logos.

    Small sizes (≤64) use LANCZOS + an unsharp pass to keep edges
    crisp; large sizes (≥128) use plain LANCZOS — they have enough
    pixels that softening artifacts disappear.
    """
    out = img.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 64:
        out = out.filter(
            ImageFilter.UnsharpMask(radius=0.6, percent=140, threshold=0)
        )
    return out


def main() -> None:
    src = Image.open(SRC).convert("RGBA")
    print(f"source: {src.size}")
    cropped = _crop_to_content(src)
    print(f"cropped to content: {cropped.size}")
    sq = _square_pad(cropped)
    print(f"square-padded: {sq.size}")

    # Build per-size variants with the right pipeline for each.
    ico_variants = [_high_quality_resize(sq, s) for s in ICO_SIZES]

    # Write the ICO with PNG-encoded sub-images.  PNG-in-ICO is the
    # standard format since Vista; it's smaller, supports proper alpha,
    # and Pillow's BMP entries can corrupt the alpha channel.
    biggest = ico_variants[-1]
    biggest.save(
        ICO,
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        bitmap_format="png",
        append_images=ico_variants[:-1],
    )
    print(f"wrote {ICO} ({ICO.stat().st_size} bytes)")

    # macOS .icns wants a 1024×1024 master.
    try:
        master = _high_quality_resize(sq, ICNS_SIZES[-1])
        master.save(ICNS, format="ICNS")
        print(f"wrote {ICNS} ({ICNS.stat().st_size} bytes)")
    except Exception as e:  # pragma: no cover - format support varies
        print(f"could not write {ICNS}: {e}")

    # Side-by-side preview PNG so you can eyeball the result without
    # opening every size in an image viewer.
    preview_path = ROOT / "assets" / "icon_preview.png"
    pad = 8
    total_w = sum(s for s in ICO_SIZES) + pad * (len(ICO_SIZES) + 1)
    total_h = max(ICO_SIZES) + pad * 2
    preview = Image.new("RGBA", (total_w, total_h), (40, 40, 48, 255))
    x = pad
    for v, s in zip(ico_variants, ICO_SIZES):
        preview.paste(v, (x, pad + (max(ICO_SIZES) - s) // 2), v)
        x += s + pad
    preview.save(preview_path)
    print(f"preview: {preview_path}")


if __name__ == "__main__":
    main()


