"""Gera src/limpameta/assets/icon.png e icon.ico (escudo com check sobre gradiente)."""
import os

from PIL import Image, ImageDraw

S = 1024
OUT = os.path.join(os.path.dirname(__file__), "..", "src", "limpameta", "assets")


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make() -> Image.Image:
    top, bottom = (91, 140, 255), (124, 77, 255)
    grad = Image.new("RGB", (S, S))
    px = grad.load()
    for y in range(S):
        for x in range(S):
            px[x, y] = lerp(top, bottom, (x * 0.35 + y * 0.65) / S)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # escudo
    cx = S / 2
    shield = [(cx, 215), (cx + 255, 300), (cx + 255, 520), (cx + 205, 680), (cx, 815),
              (cx - 205, 680), (cx - 255, 520), (cx - 255, 300)]
    sh = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sh).polygon(shield, fill=255)
    from PIL import ImageFilter
    sh = sh.filter(ImageFilter.GaussianBlur(10)).point(lambda v: 255 if v > 128 else 0)
    img.paste((255, 255, 255, 255), (0, 0), sh)
    # check
    d = ImageDraw.Draw(img)
    pts = [(cx - 120, 515), (cx - 30, 605), (cx + 135, 420)]
    d.line(pts, fill=(98, 110, 255, 255), width=78, joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - 39, p[1] - 39, p[0] + 39, p[1] + 39), fill=(98, 110, 255, 255))
    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    big = make()
    big.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "icon.png"))
    big.save(os.path.join(OUT, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("ok")
