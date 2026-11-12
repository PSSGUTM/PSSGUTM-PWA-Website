"""Mampatkan gambar muat naik (resit, lesen) supaya storan percuma tahan lama.

Gagal mampat = fail asal disimpan (tak pernah gagalkan muat naik). QR dan logo kekal PNG supaya tajam.
"""
import io

MAX_SIDE = 1600
JPEG_QUALITY = 80
KEEP_PNG_PREFIXES = ("qr_", "payout_", "logo_")   # padanan tepat; "payout_receipt_" TIDAK termasuk (dimampatkan)


def compress(content: bytes, ext: str, prefix: str = "") -> tuple[bytes, str]:
    if ext not in (".jpg", ".png"):
        return content, ext
    try:
        from PIL import Image, ImageOps
        Image.MAX_IMAGE_PIXELS = 40_000_000
        img = Image.open(io.BytesIO(content))
        img.load()
        img = ImageOps.exif_transpose(img)
        resized = max(img.size) > MAX_SIDE
        if resized:
            img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        out = io.BytesIO()
        if ext == ".png" and prefix in KEEP_PNG_PREFIXES:
            img.save(out, "PNG", optimize=True)
            new_ext = ".png"
        else:
            if img.mode in ("RGBA", "LA", "P"):
                rgba = img.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[-1])
                img = bg
            else:
                img = img.convert("RGB")
            img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
            new_ext = ".jpg"
        data = out.getvalue()
        if not resized and len(data) >= len(content) and new_ext == ext:
            return content, ext        # tiada penjimatan
        return data, new_ext
    except Exception:
        return content, ext
