"""MIRINO sulla mappa del gioco (menu in gioco > Mondo > Viaggio, idea di John 2026-10-18: "nel gioco non c'è un puntino
con cui regolarti"). Con la mappa grande aperta l'app mostra al centro della finestra del gioco un mirino trasparente
(finestra a strati con trasparenza per pixel, non prende clic né fuoco): il centro del mirino è il punto dove arrivi.

Finestra Win32 fatta a mano (ctypes): WS_EX_LAYERED | TRANSPARENT | TOPMOST | TOOLWINDOW | NOACTIVATE, immagine RGBA
disegnata con Pillow e messa con UpdateLayeredWindow. Un filo suo con il ciclo dei messaggi; da fuori solo
mostra(x, y) (centro in pixel veri) e nascondi().
"""
import ctypes
import threading
from ctypes import wintypes

WS_POPUP = 0x80000000
WS_EX = 0x00080000 | 0x00000020 | 0x00000008 | 0x00000080 | 0x08000000  # LAYERED, TRANSPARENT, TOPMOST, TOOLWINDOW, NOACTIVATE
LATO = 220


def _immagine(testo):
    """Mirino: anello, quattro tacche, puntino rosso al centro, scritta sotto (RGBA premoltiplicato, BGRA)."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    s = 4  # disegno grande e rimpicciolisco: bordi lisci
    L, A = LATO * s, (LATO + 40) * s
    im = Image.new("RGBA", (L, A), (0, 0, 0, 0))
    g = ImageDraw.Draw(im)
    c = L // 2
    for colore, spess in (((0, 0, 0, 170), 7 * s), ((255, 255, 255, 235), 3 * s)):
        r = 34 * s
        g.ellipse((c - r, c - r, c + r, c + r), outline=colore, width=spess)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            g.line((c + dx * 16 * s, c + dy * 16 * s, c + dx * 52 * s, c + dy * 52 * s), fill=colore, width=spess)
    alone = Image.new("RGBA", (L, A), (0, 0, 0, 0))
    ImageDraw.Draw(alone).ellipse((c - 14 * s, c - 14 * s, c + 14 * s, c + 14 * s), fill=(255, 59, 71, 150))
    im = Image.alpha_composite(alone.filter(ImageFilter.GaussianBlur(6 * s)), im)
    g = ImageDraw.Draw(im)
    g.ellipse((c - 6 * s, c - 6 * s, c + 6 * s, c + 6 * s), fill=(255, 59, 71, 255), outline=(255, 255, 255, 255), width=2 * s)
    if testo:
        try:
            f = ImageFont.truetype("segoeuib.ttf", 15 * s)
        except OSError:
            f = ImageFont.load_default()
        w = g.textlength(testo, font=f)
        y = c + 64 * s
        g.rounded_rectangle((c - w / 2 - 12 * s, y - 6 * s, c + w / 2 + 12 * s, y + 24 * s), radius=12 * s, fill=(11, 14, 22, 215))
        g.text((c - w / 2, y - 3 * s), testo, font=f, fill=(255, 255, 255, 255))
    im = im.resize((LATO, LATO + 40), Image.LANCZOS)
    r, gg, b, a = im.split()
    from PIL import ImageChops
    pre = [ImageChops.multiply(ch, a) for ch in (b, gg, r)]  # premoltiplicato, ordine BGRA
    return Image.merge("RGBA", (*pre, a)).tobytes(), im.size


def _dll():
    """user32/gdi32/kernel32 PRIVATI (WinDLL nuovi: i tipi messi qui non toccano il resto dell'app) con argtypes/restype
    per ogni chiamata: senza, un handle a 64 bit più grande di 2^31 dava "OverflowError: int too long to convert"
    (SelectObject con la bitmap: il mirino non compariva più, a seconda dei numeri che Windows assegna)."""
    u, g, k = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32"), ctypes.WinDLL("kernel32")
    W = wintypes
    u.SetThreadDpiAwarenessContext.argtypes, u.SetThreadDpiAwarenessContext.restype = [ctypes.c_void_p], ctypes.c_void_p
    u.DefWindowProcW.argtypes, u.DefWindowProcW.restype = [W.HWND, ctypes.c_uint, W.WPARAM, W.LPARAM], ctypes.c_ssize_t
    u.RegisterClassW.argtypes, u.RegisterClassW.restype = [ctypes.c_void_p], W.ATOM
    u.CreateWindowExW.restype = W.HWND
    u.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
    u.GetDC.argtypes, u.GetDC.restype = [W.HWND], W.HDC
    u.ReleaseDC.argtypes, u.ReleaseDC.restype = [W.HWND, W.HDC], ctypes.c_int
    u.UpdateLayeredWindow.argtypes = [W.HWND, W.HDC, ctypes.c_void_p, ctypes.c_void_p, W.HDC, ctypes.c_void_p, W.DWORD,
                                      ctypes.c_void_p, W.DWORD]
    u.UpdateLayeredWindow.restype = W.BOOL
    u.SetWindowPos.argtypes = [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    u.SetWindowPos.restype = W.BOOL
    u.ShowWindow.argtypes, u.ShowWindow.restype = [W.HWND, ctypes.c_int], W.BOOL
    u.GetMessageW.argtypes, u.GetMessageW.restype = [ctypes.c_void_p, W.HWND, ctypes.c_uint, ctypes.c_uint], W.BOOL
    u.TranslateMessage.argtypes = u.DispatchMessageW.argtypes = [ctypes.c_void_p]
    g.CreateCompatibleDC.argtypes, g.CreateCompatibleDC.restype = [W.HDC], W.HDC
    g.CreateDIBSection.restype = W.HBITMAP
    g.CreateDIBSection.argtypes = [W.HDC, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD]
    g.SelectObject.argtypes, g.SelectObject.restype = [W.HDC, W.HGDIOBJ], W.HGDIOBJ
    k.GetModuleHandleW.argtypes, k.GetModuleHandleW.restype = [W.LPCWSTR], W.HMODULE
    return u, g, k


def _bgra(im):
    """Immagine RGBA di Pillow -> byte BGRA premoltiplicati (per UpdateLayeredWindow)."""
    from PIL import Image, ImageChops
    r, gg, b, a = im.split()
    pre = [ImageChops.multiply(ch, a) for ch in (b, gg, r)]
    return Image.merge("RGBA", (*pre, a)).tobytes(), im.size


def _segnalino(testo, colore):
    """Segnalino della vista 3D della città: cerchio col numero (o la scritta) e una punta in basso; il punto del mondo è la
    punta (ancora in basso al centro)."""
    from PIL import Image, ImageDraw, ImageFont
    s = 4
    try:
        f = ImageFont.truetype("segoeuib.ttf", 17 * s)
    except OSError:
        f = ImageFont.load_default()
    prova = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = max(34 * s, int(prova.textlength(testo, font=f)) + 22 * s)
    L, A = w + 8 * s, 52 * s
    im = Image.new("RGBA", (L, A), (0, 0, 0, 0))
    g = ImageDraw.Draw(im)
    c = L // 2
    g.polygon([(c - 7 * s, 30 * s), (c + 7 * s, 30 * s), (c, A - 2 * s)], fill=(255, 255, 255, 255))
    g.rounded_rectangle((4 * s, 2 * s, L - 4 * s, 36 * s), radius=17 * s, fill=colore + (255,), outline=(255, 255, 255, 255), width=3 * s)
    tw = g.textlength(testo, font=f)
    g.text((c - tw / 2, 6 * s), testo, font=f, fill=(255, 255, 255, 255))
    im = im.resize((L // s, A // s), Image.LANCZOS)
    return im


def _freccia(testo, colore, ang):
    """Segnalino sul bordo della vista 3D quando "tu" è fuori dallo schermo: cerchio con la scritta e una punta che
    guarda verso di te (ang in radianti, 0 = destra, y dello schermo in giù). Quadrato: il punto è il CENTRO, quindi va
    mostrato con mostra(x, y + lato / 2)."""
    import math
    from PIL import Image, ImageDraw, ImageFont
    s, L = 4, 74
    try:
        f = ImageFont.truetype("segoeuib.ttf", 13 * s)
    except OSError:
        f = ImageFont.load_default()
    im = Image.new("RGBA", (L * s, L * s), (0, 0, 0, 0))
    g = ImageDraw.Draw(im)
    c, r = L * s / 2, 19 * s
    ca, sa = math.cos(ang), math.sin(ang)
    punta = (c + ca * (r + 15 * s), c + sa * (r + 15 * s))
    lato = lambda k: (c + ca * (r - 2 * s) - sa * k, c + sa * (r - 2 * s) + ca * k)
    g.polygon([punta, lato(11 * s), lato(-11 * s)], fill=(255, 255, 255, 255))
    g.ellipse((c - r, c - r, c + r, c + r), fill=colore + (255,), outline=(255, 255, 255, 255), width=3 * s)
    tw = g.textlength(testo, font=f)
    g.text((c - tw / 2, c - 9 * s), testo, font=f, fill=(255, 255, 255, 255))
    return im.resize((L, L), Image.LANCZOS)


def _freccia_icona(icona, ang, lato=None):
    """Come _freccia ma con l'icona di Spidey della mappa del gioco (ritagliata da una foto: mappa3d.ICONA) al centro e
    una punta che guarda verso di lui. Quadrata: il punto è il CENTRO (mostra(x, y + lato / 2))."""
    import math
    from PIL import Image, ImageDraw, ImageFilter
    s = 4
    ic = icona.convert("RGBA")
    d = max(ic.size)
    k = min(1.0, 52 / d)  # (al massimo ~52 px: con il gioco in 4K l'icona ritagliata è grande)
    ic = ic.resize((max(1, round(ic.width * k * s)), max(1, round(ic.height * k * s))), Image.LANCZOS)
    r = max(ic.size) / 2 + 3 * s
    L = lato or int(2 * (r / s + 17))
    im = Image.new("RGBA", (L * s, L * s), (0, 0, 0, 0))
    c = L * s / 2
    ombra = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(ombra).ellipse((c - r, c - r, c + r, c + r), fill=(0, 0, 0, 120))
    im = Image.alpha_composite(im, ombra.filter(ImageFilter.GaussianBlur(4 * s)))
    g = ImageDraw.Draw(im)
    ca, sa = math.cos(ang), math.sin(ang)
    punta = (c + ca * (r + 13 * s), c + sa * (r + 13 * s))
    lato_p = lambda q: (c + ca * (r - 1 * s) - sa * q, c + sa * (r - 1 * s) + ca * q)
    g.polygon([punta, lato_p(10 * s), lato_p(-10 * s)], fill=(255, 255, 255, 255), outline=(0, 0, 0, 160))
    im.alpha_composite(ic, (int(c - ic.width / 2), int(c - ic.height / 2)))
    return im.resize((L, L), Image.LANCZOS)


class Mirino:
    def __init__(self, testo="", immagine=None):
        """immagine = RGBA di Pillow da mostrare al posto del mirino (segnalini): allora mostra(x, y) mette la sua punta
        (in basso al centro) in (x, y)."""
        self._h = None
        self._testo = testo
        self._img = immagine
        self._pronto = threading.Event()
        self._visibile = False
        self._u = None
        threading.Thread(target=self._filo, daemon=True).start()
        self._pronto.wait(3)

    def _filo(self):
        u, g, k = _dll()
        self._u = u
        u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)
        self._proc = WNDPROC(lambda h, m, w, l: u.DefWindowProcW(h, m, w, l))

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                        ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]
        hinst = k.GetModuleHandleW(None)
        classe = f"SM2EnhancedMirino{id(self)}"  # una classe per finestra (la procedura resta di questo oggetto)
        wc = WNDCLASSW(0, self._proc, 0, 0, hinst, None, None, None, None, classe)
        u.RegisterClassW(ctypes.byref(wc))
        h = u.CreateWindowExW(WS_EX, classe, "SM2 Enhanced mirino", WS_POPUP, 0, 0, 10, 10, None, None, hinst, None)
        dati, (w, a) = _bgra(self._img) if self._img is not None else _immagine(self._testo)
        self._dim = (w, a)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]
        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -a, 1, 32, 0, 0, 0, 0, 0, 0)
        schermo = u.GetDC(None)
        mem = g.CreateCompatibleDC(schermo)
        bits = ctypes.c_void_p()
        bmp = g.CreateDIBSection(schermo, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
        ctypes.memmove(bits, dati, len(dati))
        g.SelectObject(mem, bmp)

        class BLEND(ctypes.Structure):
            _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_ubyte)]
        dim, orig = wintypes.SIZE(w, a), wintypes.POINT(0, 0)
        u.UpdateLayeredWindow(h, schermo, None, ctypes.byref(dim), mem, ctypes.byref(orig), 0, ctypes.byref(BLEND(0, 0, 255, 1)), 2)
        u.ReleaseDC(None, schermo)
        self._h = h
        self._pronto.set()
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u.TranslateMessage(ctypes.byref(msg))
            u.DispatchMessageW(ctypes.byref(msg))

    def mostra(self, x, y):
        """Centro del mirino nel punto (x, y) dello schermo (pixel veri), sopra a tutto."""
        if not self._h:
            return
        w, a = self._dim
        oy = a if self._img is not None else w / 2  # segnalino: la punta in basso; mirino: il centro del cerchio
        pos = (int(x - w / 2), int(y - oy))
        if self._visibile and pos == getattr(self, "_pos", None):
            return
        self._pos = pos
        # ASYNC (0x4000): la finestra è di un altro filo, senza aspettare la sua risposta (con 25 segnalini l'attesa
        # bloccava fino a 100 ms chi li muoveva: la mappa 3D tremava)
        self._u.SetWindowPos(self._h, wintypes.HWND(-1), pos[0], pos[1], 0, 0, 0x0001 | 0x0010 | 0x0040 | 0x4000)  # NOSIZE NOACTIVATE SHOWWINDOW
        self._visibile = True

    def alza(self):
        """Di nuovo sopra a tutto (senza muoverlo), se è visibile."""
        if self._h and self._visibile:
            self._u.SetWindowPos(self._h, wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x4000)  # NOSIZE NOMOVE NOACTIVATE ASYNC

    def nascondi(self):
        if self._h and self._visibile:
            self._u.SetWindowPos(self._h, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0004 | 0x0080 | 0x4000)  # nascondi, ASYNC
            self._visibile = False


if __name__ == "__main__":  # prova: mirino al centro dello schermo per 5 s
    import time
    m = Mirino("LB + RB · Viaggio")
    u = ctypes.windll.user32
    m.mostra(u.GetSystemMetrics(0) // 2, u.GetSystemMetrics(1) // 2)
    time.sleep(5)
