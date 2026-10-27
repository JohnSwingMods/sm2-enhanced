"""Grafica di Spider-Cam disegnata con Pillow (nessun file immagine da portarsi dietro):
ragno-emblema, icona dell'app, ragnatela di sfondo per l'intestazione."""
import math

from PIL import Image, ImageDraw, ImageFilter

ROSSO = (225, 29, 46)
BLU_NOTTE = (11, 14, 26)


def _p(x, y, s):
    """Coordinate unitarie (-1..1, y in giù) -> pixel di un'immagine s x s."""
    return (s / 2 + x * s / 2, s / 2 + y * s / 2)


def ragno(size, colore=ROSSO, ss=4):
    """Emblema del ragno (stile costume classico), sfondo trasparente."""
    s = size * ss
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = colore + (255,) if len(colore) == 3 else colore
    w = max(2, int(s * 0.058))
    # zampe (lato destro; il sinistro è specchiato): attacco al torace -> ginocchio -> punta
    zampe = [((0.06, -0.26), (0.30, -0.52), (0.36, -0.92)),
             ((0.09, -0.17), (0.44, -0.30), (0.62, -0.62)),
             ((0.09, -0.07), (0.44, 0.06), (0.60, 0.42)),
             ((0.06, 0.02), (0.30, 0.36), (0.38, 0.88))]
    for lato in (1, -1):
        for zampa in zampe:
            punti = [_p(lato * x, y, s) for x, y in zampa]
            d.line(punti, fill=c, width=w, joint="curve")
            for (px, py), r in zip(punti, (w * 0.6, w * 0.5, w * 0.35)):
                d.ellipse((px - r, py - r, px + r, py + r), fill=c)
    # testa, torace, addome a goccia
    d.ellipse([*_p(-0.075, -0.50, s), *_p(0.075, -0.36, s)], fill=c)
    d.ellipse([*_p(-0.13, -0.38, s), *_p(0.13, 0.02, s)], fill=c)
    goccia = [_p(0.15 * math.sin(t) * (1 - 0.5 * (t / math.pi) ** 1.4), -0.02 + 0.56 * t / math.pi, s)
              for t in [k * math.pi / 40 for k in range(41)]]
    goccia += [(s - x, y) for x, y in reversed(goccia)]
    d.polygon(goccia, fill=c)
    return img.resize((size, size), Image.LANCZOS)


def ragnatela(larg, alt, centro, colore=(40, 48, 80), raggi=14, anelli=9, passo=38, ss=2):
    """Ragnatela che parte da `centro` (pixel, anche fuori dall'immagine): raggi + anelli un po' "cadenti"."""
    W, H = larg * ss, alt * ss
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = centro[0] * ss, centro[1] * ss
    angoli = [2 * math.pi * k / raggi + 0.13 for k in range(raggi)]
    lung = 2 * max(W, H)
    for a in angoli:
        d.line([(cx, cy), (cx + lung * math.cos(a), cy + lung * math.sin(a))], fill=colore + (255,), width=ss)
    for n in range(1, anelli + 1):
        r = n * passo * ss * (1 + n * 0.12)
        for k in range(raggi):
            a1, a2 = angoli[k], angoli[(k + 1) % raggi] + (2 * math.pi if k == raggi - 1 else 0)
            punti = []
            for j in range(9):  # arco tra due raggi che "cede" verso il centro
                t = j / 8
                a = a1 + (a2 - a1) * t
                rr = r * (1 - 0.10 * math.sin(math.pi * t))
                punti.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
            d.line(punti, fill=colore + (255,), width=ss)
    return img.resize((larg, alt), Image.LANCZOS)


def intestazione(larg, alt, sfondo=BLU_NOTTE):
    """Sfondo dell'intestazione: notte blu con ragnatela in alto a destra e sfumatura rossa in basso."""
    img = Image.new("RGBA", (larg, alt), sfondo + (255,))
    # bagliore rosso dietro all'emblema (a sinistra)
    bagliore = Image.new("RGBA", (larg, alt), (0, 0, 0, 0))
    ImageDraw.Draw(bagliore).ellipse((alt * 0.05, alt * 0.05, alt * 1.05, alt * 0.95), fill=ROSSO + (110,))
    img = Image.alpha_composite(img, bagliore.filter(ImageFilter.GaussianBlur(alt * 0.3)))
    img = Image.alpha_composite(img, ragnatela(larg, alt, (larg - 70, -10), raggi=16, anelli=12, passo=14))
    # linea rossa in fondo
    ImageDraw.Draw(img).rectangle((0, alt - 3, larg, alt), fill=ROSSO + (255,))
    return img


def icona(size=256):
    """Icona dell'app: cerchio blu notte con ragnatela, bordo rosso e ragno rosso."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    maschera = Image.new("L", (s, s), 0)
    ImageDraw.Draw(maschera).ellipse((0, 0, s - 1, s - 1), fill=255)
    fondo = Image.new("RGBA", (s, s), BLU_NOTTE + (255,))
    fondo = Image.alpha_composite(fondo, ragnatela(s, s, (s / 2, s / 2), colore=(52, 62, 104), raggi=12,
                                                   anelli=6, passo=s // 14, ss=1))
    img.paste(fondo, (0, 0), maschera)
    ImageDraw.Draw(img).ellipse((0, 0, s - 1, s - 1), outline=ROSSO + (255,), width=s // 22)
    r = ragno(int(s * 0.78))
    img.alpha_composite(r, ((s - r.width) // 2, (s - r.height) // 2 + s // 40))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":  # anteprima + icona per PyInstaller
    import sys
    icona(256).save("spidercam.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                            (256, 256)])
    if len(sys.argv) > 1:
        icona(256).save(sys.argv[1] + "_icona.png")
        intestazione(1200, 96).save(sys.argv[1] + "_testa.png")
        ragno(200).save(sys.argv[1] + "_ragno.png")
