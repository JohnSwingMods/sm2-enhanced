"""Icona dell'app unica (spidey_app.ico): quadrato arrotondato blu scuro "da Spider-Man" con ragnatela sottile, alone
rosso e ragno rosso. Stesso stile della Spider-Cam ma quadrata, per non confonderle.
TONO = "scuro" (scelto) o "piu_scuro" (l'altra che piaceva a John). Prima il fondo era blu notte quasi nero
(backup/spidey_app.ico.prima_rossoblu). Ogni misura è disegnata a parte (anche 16-48 px, non rimpicciolita dalla 256).
Uso: python crea_icona_app.py [anteprima.png]"""
import sys

from PIL import Image, ImageDraw, ImageFilter

from spidercam_grafica import ROSSO, ragnatela, ragno

TONI = {"scuro": ((20, 48, 130), (8, 20, 62), (70, 100, 180)),  # fondo in alto, fondo in basso, linee ragnatela
        "piu_scuro": ((16, 38, 108), (6, 14, 46), (60, 86, 160))}
TONO = "scuro"


def icona(size=256):
    su, giu, linee = TONI[TONO]
    s = size * 4
    r = s // 5  # raggio degli angoli
    maschera = Image.new("L", (s, s), 0)
    ImageDraw.Draw(maschera).rounded_rectangle((0, 0, s - 1, s - 1), r, fill=255)
    fondo = Image.new("RGBA", (s, s))
    d = ImageDraw.Draw(fondo)
    for y in range(s):  # blu scuro del costume, più scuro in basso
        t = y / (s - 1)
        d.line((0, y, s, y), fill=tuple(int(a + (b - a) * t) for a, b in zip(su, giu)) + (255,))
    alone = Image.new("RGBA", (s, s), (0, 0, 0, 0))  # alone rosso dietro al ragno
    ImageDraw.Draw(alone).ellipse((s * 0.18, s * 0.2, s * 0.82, s * 0.84), fill=ROSSO + (110,))
    fondo = Image.alpha_composite(fondo, alone.filter(ImageFilter.GaussianBlur(s // 9)))
    fondo = Image.alpha_composite(fondo, ragnatela(s, s, (s / 2, s / 2), colore=linee, raggi=12, anelli=6, passo=s // 13, ss=1))
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(fondo, (0, 0), maschera)
    ImageDraw.Draw(img).rounded_rectangle((0, 0, s - 1, s - 1), r, outline=ROSSO + (255,), width=s // 26)
    rg = ragno(int(s * 0.74))
    img.alpha_composite(rg, ((s - rg.width) // 2, (s - rg.height) // 2 + s // 40))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    if "--tono" in sys.argv:
        TONO = sys.argv[sys.argv.index("--tono") + 1]
    misure = [16, 24, 32, 48, 64, 128, 256]
    icona(256).save("spidey_app.ico", sizes=[(m, m) for m in misure], append_images=[icona(m) for m in misure[:-1]])
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        icona(256).save(sys.argv[1])
