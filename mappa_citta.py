"""MAPPA DI TUTTA LA CITTÀ (menu in gioco > Mondo > Viaggio, idea di John 2026-10-19: "scegliere direttamente dalla
finestrella dove teletrasportarti in tutta la mappa": la mappa del gioco si sposta solo nei dintorni di Spidey).

Niente del gioco dentro l'app: la mappa la FOTOGRAFA l'app dal gioco dell'utente, una volta sola ("giro fotografico",
~20-30 s col gioco aperto), e la salva in AppData (mappa_citta.jpg + mappa_citta.json).

COME (provato su ITA e USA, 2026-10-19):
- Telecamera della mappa grande (gioco con la mappa aperta): struttura nell'heap (ITA 0x81476380; cercata per firma: il
  centro è uguale alla copia teletrasporto.centro_mappa): +0x00 centro (x, quota, z), +0x0C punto guardato, +0x24 vettore
  DESTRA dello schermo nel mondo (x, 0, z). Scrivendo centro e punto guardato la mappa va dove vuoi, ma resta entro ~400 m
  da Spidey -> per ogni foto sposto anche Spidey (con la mappa aperta il gioco è fermo: resta lì).
- LA ROTAZIONE NON È FISSA: il gioco la sceglie aprendo la mappa (da dove guarda la camera; scrivere +0x24 non la cambia).
  La prima versione la dava fissa (-13,58°, misurata sul mio Dolphin di prova): sul PC di John era girata di ~135° e la
  mappa è venuta a pezzi sparsi. Ora la leggo da +0x24 a ogni giro: destra = r = (rx, rz), giù = q = (rz, -rx).
- Quota 4500 col campo visivo del gioco (FOV, radianti, ORIZZONTALE) a 0.5 = quasi dall'alto e piatta: metà larghezza
  visibile = 4500 tan(0.25) = ~1150 m, metà altezza = quella / aspetto del gioco (16:9 -> ~650 m). Oltre ~5000 m la città
  non si disegna (piano lontano); con FOV normale e quota alta il gioco carica tutto e SI PIANTA: sempre PRIMA il FOV
  stretto e POI la quota, e al ritorno prima giù (500) e POI il FOV.
- Icone, scritte e cornici della mappa: fuori dallo schermo col byte hud_ram.FOTO (programma dell'HUD 16:9).
- Geometria (misurata al decimo di pixel su due PC): pixel = C + J.(mondo - bersaglio), C = centro dell'immagine del gioco
  (senza bande nere), bersaglio = punto guardato (x, 0, z + AVANTI), J = [[sx rx, sx rz], [sy rz, -sy rx]],
  sx = (larghezza / 2) / (QUOTA tan(FOV / 2)), sy = sx * aspetto * altezza / larghezza.
- Griglia di foto allineata allo SCHERMO (lungo r e q) che copre il rettangolo LIMITI: funziona con qualsiasi rotazione.
- Ogni foto ridimensionata a pixel quadrati (PX_M per metro in x e y) e incollata con una maschera rettangolare (metà
  passo + sfumatura); poi la tela intera è RUOTATA in un orientamento fisso (ORIENTA: Manhattan orizzontale, nord a
  sinistra) e ritagliata su LIMITI. Solo Pillow (niente numpy nell'exe).
Sulla tela finale: pixel = J . (x, z) + O (in mappa_citta.json)."""
import json
import math
import os
import struct
import time
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

QUOTA = 4500.0  # col campo visivo dimezzato (FOV_FOTO) stessa area e stesso dettaglio di 2250 m / 0.5, ma i palazzi alti
# "pendono" la metà (John: foto vicine con prospettive diverse). Oltre ~5000 m il gioco non disegna più la città.
FOV_FOTO = 0.25
AVANTI = 25.0  # il punto guardato è un po' avanti in z: la telecamera ha un "su" e il centro dello schermo è lui
# la terra (misurata sulla prima mappa intera): Manhattan da x ~-2500 (sopra Central Park) a ~2950 (Battery), z da ~-1000
# a ~1400 (Roosevelt Island), Ellis/Liberty Island fino a x ~3900: la mappa copre e salva questo rettangolo (+ margine)
LIMITI = (-2750.0, -1250.0, 4250.0, 1650.0)
SOVRAPP_U, SOVRAPP_V = 0.85, 0.80  # passo della griglia = 2 * metà visibile * questo (il resto è sovrapposizione:
# deve bastare per la sfumatura e per gli angoli in alto tolti dalle foto)
BORDO = 0.88  # i centri estremi a questa frazione della metà visibile dal bordo del rettangolo
SFUMA = 90.0  # (mappe vecchie) metri di sfumatura tra due foto: i palazzi alti venivano doppi = sfocati
CUCITURA = 6.0  # metri oltre la metà strada tra due foto vicine (giuntura stretta: niente palazzi doppi)
SFUMA_PX = 2.5  # bordo morbido della giuntura (pixel della foto)
ACQUA_NOTTE = 34  # maschera dell'acqua sulla mappa di notte: blu - rosso almeno così (acqua ~48, strade ~25, tetti <= 20)
ACQUA_AZZURRA = (64, 112, 158)  # l'acqua della mappa di giorno va un po' verso questo colore
ACQUA_NOTTE_ONDE = 16  # ...oppure almeno così se ci sono le onde (da 4500 m l'acqua di notte a est è solo ~31)
ACQUA_DETTAGLIO = 8  # dettaglio fine minimo delle onde (sulla foto di giorno a metà risoluzione)
ACQUA_GIORNO = 4  # (solo se manca quella di notte) di giorno: blu - rosso almeno così (acqua ~13, tetti e strade < 0)
PX_M = 1.5  # pixel per metro della mappa salvata (= quanto vede il gioco a 2250 m in una finestra larga ~1900 px)
TASSELLO = 1024  # la mappa grande è salvata a quadrati (l'esploratore carica solo quelli che servono)
PANORAMICA = 3200  # larghezza dell'immagine intera rimpicciolita (esploratore da lontano)
ORIENTA = (1.0, 0.0)  # direzione del mondo che va a DESTRA nella mappa salvata: la griglia delle strade del gioco è
# lungo gli assi del mondo (misurato), così la mappa è dritta (John: "storta"); nord (-x) a sinistra
VERSIONE = 3
# pezzi del gioco fuori dalla città da togliere (rettangoli nel mondo x0, z0, x1, z1): il moncone del ponte verso il
# Queens finisce in mezzo all'acqua e il bordo della mappa lo tagliava (John: "difetto grafico")
TOGLI = ((-430.0, 1480.0, -340.0, 1700.0),)
BANDA_MARE = 200  # pixel: verso il bordo della mappa l'acqua sfuma nel mare "ripetibile" (oltre il bordo l'esploratore
# continua con quello: niente bordo netto)
MARE_P, MARE_X = 896, 128  # periodo del mare ripetibile e sfumatura tra una ripetizione e l'altra
NOTTE_CHIARI = (130, 0.55)  # di notte il gioco disegna il terreno beige chiaro (John: "bruciato"): sopra 130 x 0.55
LAVORATORI = 0  # thread della cucitura (0 = secondo i processori); Pillow lavora fuori dal GIL: ~3 volte più veloce
FOV = {"GK2I52": 0x8046A7C0}  # le altre (stesso programma USA) 0x8046A740
STRUTTURA_ZONE = ((0x81000000, 0x800000), (0x80400000, 0xC00000))


def fov_ind(gid):
    return FOV.get(gid, 0x8046A740)


def trova_struttura(dme, gid):
    """Indirizzo della telecamera della mappa (mappa aperta): dove il centro (copia in teletrasporto.centro_mappa) è
    seguito da un punto guardato vicino in x/z e più in basso."""
    import teletrasporto as tp
    c = dme.read_bytes(tp.centro_mappa(gid), 12)
    cx, cy, cz = struct.unpack(">3f", c)
    for base, n in STRUTTURA_ZONE:
        ram = b"".join(dme.read_bytes(base + k, 0x100000) for k in range(0, n, 0x100000))
        i = ram.find(c)
        while i >= 0:
            if i % 4 == 0 and i + 48 <= len(ram):
                tx, ty, tz = struct.unpack(">3f", ram[i + 12:i + 24])
                if abs(tx - cx) < 50 and abs(tz - cz) < 50 and ty < cy - 1 and base + i != tp.centro_mappa(gid):
                    return base + i
            i = ram.find(c, i + 1)
    return None


def _metà(aspetto):
    hu = QUOTA * math.tan(FOV_FOTO / 2)
    return hu, hu / aspetto


def _valori(a, b, metà, passo):
    """Centri lungo un asse da a a b (i bordi coperti): equidistanti, passo <= passo."""
    m0, m1 = a + metà * BORDO, b - metà * BORDO
    if m1 <= m0:
        return [(a + b) / 2]
    n = math.ceil((m1 - m0) / passo) + 1
    return [m0 + (m1 - m0) * k / (n - 1) for k in range(n)]


def griglia(r, aspetto):
    """[(u, v, i, j)] centri della griglia allineata allo schermo (u lungo r, v lungo q) che copre LIMITI."""
    rx, rz = r
    hu, hv = _metà(aspetto)
    us, vs = [], []
    for wx in (LIMITI[0], LIMITI[2]):
        for wz in (LIMITI[1], LIMITI[3]):
            us.append(wx * rx + wz * rz)
            vs.append(wx * rz - wz * rx)
    U = _valori(min(us), max(us), hu, 2 * hu * SOVRAPP_U)
    Vv = _valori(min(vs), max(vs), hv, 2 * hv * SOVRAPP_V)
    tutte = [(u, v, i, j) for j, v in enumerate(Vv) for i, u in enumerate(U)]
    return [c for c in tutte if _tocca(r, c[0], c[1], hu, hv)], len(U), len(Vv)


def _tocca(r, u, v, hu, hv):
    """La foto (rettangolo ruotato attorno a (u, v)) tocca il rettangolo LIMITI? (assi separatori: x, z, r, q)"""
    rx, rz = r
    q = (rz, -rx)
    cx, cz = mondo(r, u, v)
    lx, lz = (LIMITI[0] + LIMITI[2]) / 2, (LIMITI[1] + LIMITI[3]) / 2
    mx, mz = (LIMITI[2] - LIMITI[0]) / 2, (LIMITI[3] - LIMITI[1]) / 2
    for nx, nz in ((1, 0), (0, 1), (rx, rz), q):
        d = abs((cx - lx) * nx + (cz - lz) * nz)
        if d > hu * abs(rx * nx + rz * nz) + hv * abs(q[0] * nx + q[1] * nz) + mx * abs(nx) + mz * abs(nz):
            return False
    return True


def mondo(r, u, v):
    rx, rz = r
    return u * rx + v * rz, u * rz - v * rx


class Giro:
    """Giro fotografico (mappa del gioco GIÀ aperta da almeno ~1 s). progresso(n, tot) a ogni foto."""

    def __init__(self, gid, cartella, progresso=None):
        import app_core as core
        self.core, self.gid, self.cartella = core, gid, Path(cartella)
        self.v = core.Viaggio(gid)
        self.progresso = progresso or (lambda n, tot: None)
        self.fermato = False
        self.r = None

    def _dme(self):
        return self.v._dme()

    def aspetto(self):
        import hud_wide
        with self.core.DME_LOCK:
            a = struct.unpack(">f", self._dme().read_bytes(hud_wide.VERSIONI[self.gid]["aspetto"], 4))[0]
        return a if 1.2 < a < 2.6 else 4 / 3

    def _aspetta_ferma(self, massimo=10.0):
        """Aprendo la mappa la telecamera VOLA da un punto fuori città fino a Spidey (quota che cambia): finché vola il gioco
        riscrive la sua struttura e le nostre posizioni non tengono (sul PC di John, più lento: "telecamera", rifai con X
        fallito). Aspetto quota della mappa (>= 499) e centro fermo per ~0,6 s."""
        import teletrasporto as tp
        L, t0, fermi, prima = self.core.DME_LOCK, time.time(), 0, None
        while time.time() - t0 < massimo:
            with L:
                c = struct.unpack(">3f", self._dme().read_bytes(tp.centro_mappa(self.gid), 12))
            if c[1] >= 499 and prima and max(abs(c[k] - prima[k]) for k in range(3)) < 0.2:
                fermi += 1
                if fermi >= 6:
                    return True
            else:
                fermi = 0
            prima = c
            time.sleep(0.1)
        return False

    def esegui(self, punti=None):
        """Fa le foto e ritorna (elenco [(u, v, i, j, file)], r, aspetto, ni, nj); rimette sempre tutto com'era.
        punti = [(x, z)]: invece della griglia, una foto centrata su ognuno di questi punti (campioni di luce)."""
        import hud_ram
        core = self.core
        L = core.DME_LOCK
        self._aspetta_ferma()
        with L:
            dme = self._dme()
            P = trova_struttura(dme, self.gid)
            if not P:
                raise RuntimeError("struttura")
            v0 = struct.unpack(">6f", dme.read_bytes(P, 24))
            dx, dy, dz = struct.unpack(">3f", dme.read_bytes(P + 0x24, 12))
            f0 = struct.unpack(">f", dme.read_bytes(fov_ind(self.gid), 4))[0]
        n = math.hypot(dx, dz)
        if not (0.9 < n < 1.1 and abs(dy) < 0.1):
            raise RuntimeError(f"direzione {dx:.3f} {dy:.3f} {dz:.3f}")
        self.r = r = (dx / n, dz / n)
        aspetto = self.aspetto()
        lista, ni, nj = griglia(r, aspetto)
        if punti:
            lista = [(x * r[0] + z * r[1], x * r[1] - z * r[0], k, 0) for k, (x, z) in enumerate(punti)]
        pos0 = self.v.posizione()
        g = core.finestra_gioco()
        import ctypes
        if g and ctypes.windll.user32.IsIconic(g):  # ridotto a icona: la foto della finestra verrebbe vuota
            ctypes.windll.user32.ShowWindow(g, 9)
            time.sleep(1.0)
        self.cartella.mkdir(parents=True, exist_ok=True)
        fatti = []
        try:
            with L:
                dme = self._dme()
                dme.write_byte(hud_ram.FOTO, 1)
                dme.write_bytes(fov_ind(self.gid), struct.pack(">f", FOV_FOTO))  # PRIMA il campo visivo stretto...
            time.sleep(0.3)
            for k, (u, v, i, j) in enumerate(lista):
                if self.fermato or not self.v.mappa_aperta():
                    raise RuntimeError("interrotto")
                tx, tz = mondo(r, u, v)  # punto al centro dello schermo
                x, z = tx, tz - AVANTI  # telecamera
                self.v.metti((x, 520.0, z))
                riga = struct.pack(">6f", x, QUOTA, z, x, 0.0, z + AVANTI)
                with L:  # ...POI la quota
                    self._dme().write_bytes(P, riga)
                time.sleep(0.15)
                ok = False
                for prova in range(45):  # la telecamera è arrivata? (il gioco la tiene vicino a Spidey)
                    with L:
                        c = struct.unpack(">3f", self._dme().read_bytes(P, 12))
                    if abs(c[0] - x) < 1 and abs(c[2] - z) < 1 and abs(c[1] - QUOTA) < 1:
                        ok = True
                        break
                    if prova == 25:  # non risponde: forse era una copia (struttura ritrovata)
                        with L:
                            P2 = trova_struttura(self._dme(), self.gid)
                        P = P2 or P
                    with L:
                        self._dme().write_bytes(P, riga)
                    time.sleep(0.1)
                if not ok:
                    raise RuntimeError("telecamera")
                time.sleep(0.35)  # due-tre fotogrammi col disegno nuovo
                im = core.foto_finestra(g, immagine=True)
                if im is None and g and ctypes.windll.user32.IsIconic(g):  # ridotto a icona a metà giro: lo rimetto
                    ctypes.windll.user32.ShowWindow(g, 9)
                    time.sleep(1.0)
                    im = core.foto_finestra(g, immagine=True)
                if im is None:
                    raise RuntimeError("foto")
                f = self.cartella / f"t_{j}_{i}.jpg"
                im.save(f, "JPEG", quality=95)
                fatti.append((u, v, i, j, str(f)))
                self.progresso(k + 1, len(lista))
        finally:
            with L:
                dme = self._dme()
                dme.write_bytes(P, struct.pack(">6f", v0[0], 500.0, v0[2], v0[3], v0[4], v0[5]))  # PRIMA giù...
            time.sleep(0.6)
            with L:
                dme = self._dme()
                dme.write_bytes(fov_ind(self.gid), struct.pack(">f", f0))  # ...POI il campo visivo
                dme.write_byte(hud_ram.FOTO, 0)
            self.v.metti(tuple(pos0))
        return fatti, r, aspetto, ni, nj


def contenuto(im):
    """Riquadro dell'immagine del gioco senza le bande nere. Dolphin la centra: misuro il bordo sinistro e quello in alto
    e prendo gli altri uguali (a destra in alto Dolphin può scrivere gli FPS: con getbbox il riquadro veniva più largo
    e la mappa stirata, foto sfalsate)."""
    b = im.convert("L").point(lambda v: 255 if v > 8 else 0).getbbox()
    if not b:
        return (0, 0, im.width, im.height)
    return (b[0], b[1], im.width - b[0], im.height - b[1])


def _passi(valori):
    return [valori[k + 1] - valori[k] for k in range(len(valori) - 1)]


def _geometria(r):
    """Pixel della mappa salvata = J . (x, z) + O, grandezza W x H. J ha sempre la prima riga lungo ORIENTA (non dipende
    dalla rotazione r della mappa del gioco: le mappe di giorno e di notte coincidono pixel per pixel anche se il gioco
    le ha aperte girate in modo diverso)."""
    rx, rz = r
    ex, ez = ORIENTA
    n = math.hypot(ex, ez)
    ex, ez = ex / n, ez / n
    a = math.atan2(ex * rz - ez * rx, ex * rx + ez * rz)
    ca, sa = math.cos(a), math.sin(a)
    B = [[PX_M * rx, PX_M * rz], [PX_M * rz, -PX_M * rx]]
    J = [[ca * B[0][0] + sa * B[1][0], ca * B[0][1] + sa * B[1][1]],
         [-sa * B[0][0] + ca * B[1][0], -sa * B[0][1] + ca * B[1][1]]]
    xs, ys = [], []
    for wx in (LIMITI[0], LIMITI[2]):
        for wz in (LIMITI[1], LIMITI[3]):
            xs.append(J[0][0] * wx + J[0][1] * wz)
            ys.append(J[1][0] * wx + J[1][1] * wz)
    return J, [-min(xs), -min(ys)], round(max(xs) - min(xs)), round(max(ys) - min(ys)), a


def _rettangolo(fatti, k, cuc=None):
    """Parte della foto k che resta nella cucitura (metri dal centro lungo r e q): fino a metà strada dalle vicine +
    CUCITURA; dove non c'è una vicina, tutta. È anche la regola di occhio() (che foto si vede in un punto)."""
    us = sorted({f[0] for f in fatti})
    vs = sorted({f[1] for f in fatti})
    ci = {(round(f[0], 3), round(f[1], 3)) for f in fatti}
    u, v = fatti[k][0], fatti[k][1]
    iu, iv = us.index(u), vs.index(v)
    c = lambda a, b: (round(a, 3), round(b, 3)) in ci
    cuc = CUCITURA if cuc is None else cuc
    a0 = -1e6 if iu == 0 or not c(us[iu - 1], v) else -((u - us[iu - 1]) / 2 + cuc)
    a1 = 1e6 if iu == len(us) - 1 or not c(us[iu + 1], v) else (us[iu + 1] - u) / 2 + cuc
    b0 = -1e6 if iv == 0 or not c(u, vs[iv - 1]) else -((v - vs[iv - 1]) / 2 + cuc)
    b1 = 1e6 if iv == len(vs) - 1 or not c(u, vs[iv + 1]) else (vs[iv + 1] - v) / 2 + cuc
    return a0, a1, b0, b1


def _tela(fatti, r, aspetto, J, O, W, H, a, progresso):
    """Incolla le foto di un giro nella tela finale. Ogni foto: ritaglio senza bande nere, maschera (rettangolo della
    cucitura con bordo morbido di pochi pixel, angoli in alto via), poi UNA sola trasformazione (scala a PX_M pixel per
    metro + rotazione nell'orientamento finale: prima erano due ricampionamenti = più sfocata)."""
    prima = Image.open(fatti[0][4])
    box = contenuto(prima)
    cw, ch = box[2] - box[0], box[3] - box[1]
    sx = (cw / 2) / (QUOTA * math.tan(FOV_FOTO / 2))  # pixel della foto per metro
    sy = sx * aspetto * ch / cw
    tw, th = cw * PX_M / sx, ch * PX_M / sy  # foto a pixel quadrati (PX_M per metro)
    kx, ky = cw / tw, ch / th
    t = -a  # stessa convenzione di Image.rotate(gradi(a)): uscita -> ingresso = rotazione di -a
    c, s = math.cos(t), math.sin(t)
    Wo = math.ceil(abs(tw * math.cos(a)) + abs(th * math.sin(a)))
    Ho = math.ceil(abs(tw * math.sin(a)) + abs(th * math.cos(a)))
    coeff = (kx * c, kx * s, cw / 2 - kx * (c * Wo / 2 + s * Ho / 2),
             -ky * s, ky * c, ch / 2 - ky * (-s * Wo / 2 + c * Ho / 2))
    tela = Image.new("RGB", (W, H), (0, 0, 0))
    coperta = Image.new("L", (W, H), 0)  # dove c'è una foto (il resto si riempie col colore dell'acqua)

    def trasforma(k):  # (in un thread) foto k ritagliata, mascherata e portata nell'orientamento finale
        a0, a1, b0, b1 = _rettangolo(fatti, k)
        im = Image.open(fatti[k][4]).convert("RGB").crop(box)
        m = Image.new("L", (cw, ch), 0)
        dm = ImageDraw.Draw(m)
        dm.rectangle((cw / 2 + a0 * sx, ch / 2 + b0 * sy, cw / 2 + a1 * sx, ch / 2 + b1 * sy), fill=255)
        # angoli in alto: lì Dolphin scrive FPS e messaggi (le foto vicine coprono quel pezzo)
        dm.rectangle((0, 0, cw * 0.3, ch * 0.09), fill=0)
        dm.rectangle((cw * 0.7, 0, cw, ch * 0.09), fill=0)
        m = m.filter(ImageFilter.GaussianBlur(SFUMA_PX))
        im.putalpha(m)
        return im.convert("RGBa").transform((Wo, Ho), Image.AFFINE, coeff, resample=Image.BICUBIC).convert("RGBA")
    # incollate nell'ordine (nella sovrapposizione vince quella dopo: vedi occhio())
    for k, im in enumerate(_in_parallelo(trasforma, range(len(fatti)))):
        u, v = fatti[k][0], fatti[k][1]
        tx, tz = mondo(r, u, v)  # centro della foto = punto guardato
        px = J[0][0] * tx + J[0][1] * tz + O[0]
        py = J[1][0] * tx + J[1][1] * tz + O[1]
        tela.paste(im, (round(px - Wo / 2), round(py - Ho / 2)), im)
        coperta.paste(255, (round(px - Wo / 2), round(py - Ho / 2)), im.getchannel("A"))
        progresso()
    return tela, coperta


def _dilata(m, r):
    """Maschera bianco/nero: MaxFilter(2r+1) fatto con sfocatura + soglia (il filtro di Pillow blocca gli altri thread)."""
    return m.filter(ImageFilter.BoxBlur(r)).point(lambda v: 255 if v > 0 else 0)


def _erodi(m, r):
    """Maschera bianco/nero: MinFilter(2r+1) (vedi _dilata)."""
    return m.filter(ImageFilter.BoxBlur(r)).point(lambda v: 255 if v >= 250 else 0)


def maschera_acqua(im, notte, soglia=None):
    """Pixel d'acqua (L, 255 = acqua). Misurato: di NOTTE l'acqua è molto blu (blu - rosso ~45-50) e tetti/strade molto
    meno (<= 25); di GIORNO l'acqua è chiara e grigio-azzurra (blu - rosso > 0) e tetti/strade/parchi sono caldi (< 0).
    La si calcola sulla mappa di notte (più sicura) e vale per tutte e due (stessi pixel). L'acqua ha le onde: niente
    controllo di "liscio"; via i puntini isolati (apertura) e bordo morbido."""
    from PIL import ImageMath
    grande = im.size
    im = im.resize((max(1, grande[0] // 2), max(1, grande[1] // 2)), Image.BILINEAR)  # a metà: 4 volte più veloce
    im = im.filter(ImageFilter.BoxBlur(3))  # le creste chiare delle onde (verso est sono tante) si confondono col mare
    r, g, b = im.split()
    if notte:
        sg = ACQUA_NOTTE if soglia is None else soglia
        m = ImageMath.lambda_eval(lambda x: (x["b"] - x["r"]) > sg, r=r, g=g, b=b)
    else:
        m = ImageMath.lambda_eval(lambda x: ((x["b"] - x["r"]) > ACQUA_GIORNO) & ((x["r"] + x["g"] + x["b"]) > 270),
                                  r=r, g=g, b=b)
    m = m.convert("L").point(lambda v: 255 if v else 0)
    # le creste delle onde non passano il controllo: chiusura (riempie i buchi fino a ~8 pixel) e poi via i puntini sparsi
    m = _erodi(_dilata(m, 2), 2)
    m = _dilata(_erodi(m, 1), 1)
    return m.resize(grande, Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.2))


def _onde(im):
    """Dove l'immagine ha il dettaglio fine delle onde (L, 255 = sì): l'acqua increspata ne ha tanto, i tetti lisci poco."""
    g = im.convert("L")
    g = g.resize((max(1, g.width // 2), max(1, g.height // 2)), Image.BILINEAR)
    det = ImageChops.difference(g, g.filter(ImageFilter.BoxBlur(2))).filter(ImageFilter.BoxBlur(6))
    m = _erodi(_dilata(det.point(lambda v: 255 if v > ACQUA_DETTAGLIO else 0), 2), 2)
    return m.resize(im.size, Image.BILINEAR)


def _acqua_uniforme(im, colore, m):
    """Acqua (maschera m) -> colore unico + solo la grana fine di prima (la differenza dall'immagine sfocata): restano le
    onde, spariscono i chiaroscuri dei riflessi che facevano vedere i riquadri delle foto."""
    grana = ImageChops.subtract(im, im.filter(ImageFilter.BoxBlur(6)), 2.5, 128)  # (/2.5: onde leggere)
    piatta = ImageChops.add(Image.new("RGB", im.size, colore), grana, 1, -128)
    return Image.composite(piatta, im, m)


def _bilancio(tela, acqua):
    """Mappa di giorno: la luce del gioco tira al verde-giallo (strade e piazze verdognole). Guadagni per canale che
    rendono grigi neutri i pixel poco saturi e chiari della TERRA (strade, piazze, marciapiedi; l'acqua di giorno è
    grigio-verde e falsava tutto): uguali per tutta la mappa."""
    p = tela.resize(acqua.size, Image.BILINEAR)
    neutri = [c for c, a in zip(p.getdata(), acqua.getdata()) if a < 60 and max(c) - min(c) < 25 and sum(c) > 200]
    if len(neutri) < 200:
        return None
    m = [sum(c[k] for c in neutri) / len(neutri) for k in range(3)]
    g = sum(m) / 3
    return [max(0.9, min(1.12, 1 + 0.6 * (g / x - 1))) for x in m]  # al 60%: tutto pieno tirava al rosa


def _ritocco(im, notte, guadagni=None, chiari=False):
    """Bilanciamento del bianco (giorno), colori più vivi e un po' di nitidezza (la mappa del gioco vista da lontano è
    spenta e morbida). chiari = (mappa di notte) i toni chiari compressi: il terreno beige del gioco sembrava bruciato."""
    from PIL import ImageEnhance
    if guadagni:
        im = im.point([min(255, round(v * guadagni[k])) for k in range(3) for v in range(256)])
    if chiari:
        s0, k0 = NOTTE_CHIARI
        im = im.point([v if v <= s0 else round(s0 + (v - s0) * k0) for _ in range(3) for v in range(256)])
    im = ImageEnhance.Color(im).enhance(1.12 if notte else 1.25)
    im = ImageEnhance.Contrast(im).enhance(1.04 if notte else 1.08)
    if not notte:
        im = ImageEnhance.Brightness(im).enhance(1.04)
    return im.filter(ImageFilter.UnsharpMask(radius=1.1, percent=70, threshold=2))


def _colore_acqua(tela, maschera_piccola):
    """Colore dell'acqua = mediana dei pixel d'acqua (tela rimpicciolita come la maschera)."""
    p = tela.resize(maschera_piccola.size, Image.BILINEAR)
    sel = [c for c, m in zip(p.getdata(), maschera_piccola.getdata()) if m > 200]
    if len(sel) < 50:
        return None
    return tuple(sorted(x[k] for x in sel)[len(sel) // 2] for k in range(3))


def _piastrella(img, ox, oy, size):
    """Pezzo grande size di img ripetuta all'infinito, a partire dal punto assoluto (ox, oy) (giunture continue)."""
    w, h = img.size
    out = Image.new(img.mode, size)
    for y in range(-(oy % h), size[1], h):
        for x in range(-(ox % w), size[0], w):
            out.paste(img, (x, y))
    return out


def _luce(file_giorno, file_altra):
    """Come il gioco cambia i colori della mappa da giorno a un'altra ora: matrice 3x4 (RGB -> RGB) dai minimi quadrati sui
    pixel di terra di due foto fatte dallo stesso punto, e colore dell'acqua nell'altra foto. Ritorna (matrice, colore)."""
    a = Image.open(file_giorno).convert("RGB")
    b = Image.open(file_altra).convert("RGB")
    box = contenuto(a)
    a = a.crop(box).resize((240, 132), Image.BILINEAR)
    b = b.crop(box).resize((240, 132), Image.BILINEAR)
    acqua = maschera_acqua(a, False).resize(a.size)
    terra_px, mare_px = [], []
    for ca, cb, m in zip(a.getdata(), b.getdata(), acqua.getdata()):
        (mare_px if m > 200 else terra_px if m < 40 else []).append((ca, cb))
    if len(terra_px) < 500:
        raise RuntimeError("campione senza terra")
    matrice = []
    for c in range(3):  # x_c = r*A + g*B + b*C + D
        N = [[0.0] * 5 for _ in range(4)]
        for ca, cb in terra_px:
            v = (ca[0], ca[1], ca[2], 1.0)
            for i in range(4):
                for j in range(4):
                    N[i][j] += v[i] * v[j]
                N[i][4] += v[i] * cb[c]
        for i in range(4):  # eliminazione di Gauss
            piv = max(range(i, 4), key=lambda r: abs(N[r][i]))
            N[i], N[piv] = N[piv], N[i]
            for r in range(4):
                if r != i and N[i][i]:
                    f = N[r][i] / N[i][i]
                    N[r] = [x - f * y for x, y in zip(N[r], N[i])]
        matrice += [N[i][4] / N[i][i] for i in range(4)]
    colore = None
    if len(mare_px) > 50:
        colore = tuple(sorted(cb[k] for _, cb in mare_px)[len(mare_px) // 2] for k in range(3))
    return tuple(matrice), colore


_FINE = object()


def _in_parallelo(fn, elementi):
    """fn(elemento) per tutti, in più thread, risultati NELL'ORDINE (al massimo 2 x thread in sospeso: memoria
    limitata). Pillow fa il grosso fuori dal GIL (decodifica, filtri, ridimensioni, trasformazioni, JPEG)."""
    from concurrent.futures import ThreadPoolExecutor
    n = LAVORATORI or max(2, min(6, (os.cpu_count() or 4) - 2))
    it = iter(elementi)
    with ThreadPoolExecutor(n) as ex:
        coda = deque()
        for _ in range(2 * n):
            x = next(it, _FINE)
            if x is _FINE:
                break
            coda.append(ex.submit(fn, x))
        while coda:
            ris = coda.popleft().result()
            x = next(it, _FINE)
            if x is not _FINE:
                coda.append(ex.submit(fn, x))
            yield ris


def _ripetibile(g):
    """g grande MARE_P + MARE_X -> MARE_P ripetibile: le ultime MARE_X righe/colonne sfumano sulle prime."""
    P, X = MARE_P, MARE_X
    sf = Image.new("L", (X, 1))
    sf.putdata([round(255 * (i + 0.5) / X) for i in range(X)])  # 0 -> 255 (quanto resta della striscia di partenza)
    a = g.crop((0, 0, P, P + X))
    b = g.crop((P, 0, P + X, P + X))
    a.paste(Image.composite(a.crop((0, 0, X, P + X)), b, sf.resize((X, P + X))), (0, 0))
    c = a.crop((0, 0, P, P))
    d = a.crop((0, P, P, P + X))
    sv = Image.new("L", (1, X))
    sv.putdata(list(sf.getdata()))
    c.paste(Image.composite(c.crop((0, 0, P, X)), d, sv.resize((P, X))), (0, 0))
    return c


def _banda(x0, y0, w, h, W, H, larga):
    """L grande w x h (in alto a sinistra al pixel x0, y0 della mappa): 255 sul bordo della mappa, 0 a `larga` pixel
    dentro (sfumatura lineare)."""
    f = lambda d: max(0, min(255, round(255 * (1 - d / larga))))
    riga = Image.new("L", (w, 1))
    riga.putdata([f(min(x, W - x)) for x in range(x0, x0 + w)])
    col = Image.new("L", (1, h))
    col.putdata([f(min(y, H - y)) for y in range(y0, y0 + h)])
    return ImageChops.lighter(riga.resize((w, h), Image.NEAREST), col.resize((w, h), Image.NEAREST))


def cuci(giri, aspetto, cartella, progresso=None, campioni=None):
    """giri = [(fatti, r) di giorno, (fatti, r) di notte o None] (vedi Giro.esegui). Salva in `cartella`, per ogni strato
    (giorno "t", notte "n"): quadrati <s>_<x>_<y>.jpg (TASSELLO px, piena risoluzione), panoramica(_n).jpg (PANORAMICA px)
    e piccola(_n).jpg (1280 px); poi acqua.png (maschera dell'acqua, grande come la piccola) e mappa.json (pixel della
    mappa intera = J . (x, z) + O).
    Due passaggi: 1) ogni strato incollato e salvato a quadrati "grezzi" (con un bordo) in una cartella di lavoro, così in
    memoria c'è una tela sola alla volta; 2) maschera dell'acqua = acqua di giorno E di notte (di notte alcuni tetti sono
    blu quasi come l'acqua, di giorno grigi caldi), poi ritocco, acqua uniforme e quadrati finali."""
    progresso = progresso or (lambda n, tot: None)
    giri = [g for g in giri if g]
    fatti0, r0 = giri[0]
    J, O, W, H, _ = _geometria(r0)
    nx, ny = math.ceil(W / TASSELLO), math.ceil(H / TASSELLO)
    tot = sum(len(f) for f, _ in giri) + (2 * len(giri) + 1 + (2 if campioni else 0)) * nx * ny
    fatto = [0]

    def avanti(n=1):
        fatto[0] += n
        progresso(min(fatto[0], tot), tot)

    cartella = Path(cartella)
    grezzi = cartella / "_grezzi"
    grezzi.mkdir(parents=True, exist_ok=True)
    kp = PANORAMICA / W
    picc = (1280, round(H * 1280 / W))
    M = 8  # bordo dei quadrati grezzi (filtri senza giunture)
    strati = list(zip(("t", "n"), giri))
    piccole = {}
    quadrati = [(tx, ty) for ty in range(ny) for tx in range(nx)]
    togli = []  # TOGLI in pixel della mappa
    for x0w, z0w, x1w, z1w in TOGLI:
        xs = [J[0][0] * x + J[0][1] * z + O[0] for x in (x0w, x1w) for z in (z0w, z1w)]
        ys = [J[1][0] * x + J[1][1] * z + O[1] for x in (x0w, x1w) for z in (z0w, z1w)]
        togli.append((min(xs), min(ys), max(xs), max(ys)))

    def maschera_togli(tx, ty, size):  # L (255 = da togliere) per il quadrato grezzo tx, ty, o None
        ox, oy = tx * TASSELLO - M, ty * TASSELLO - M
        dentro = [(a - ox, b - oy, c - ox, d - oy) for a, b, c, d in togli
                  if c + 90 > ox and a - 90 < ox + size[0] and d + 90 > oy and b - 90 < oy + size[1]]
        if not dentro:
            return None
        m = Image.new("L", size, 0)
        for x0, y0, x1, y1 in dentro:  # un po' più grande e molto sfumato: niente rettangolo visibile
            ImageDraw.Draw(m).rectangle((x0 - 30, y0 - 30, x1 + 30, y1 + 30), fill=255)
        return m.filter(ImageFilter.GaussianBlur(24))

    def grezzo(strato, tx, ty):
        q = Image.open(grezzi / f"{strato}_{tx}_{ty}.jpg").convert("RGB")
        f = grezzi / f"{strato}_{tx}_{ty}_c.png"
        return q, (Image.open(f).convert("L") if f.is_file() else None)

    # 1) tele -> quadrati grezzi
    for strato, (fatti, r) in strati:
        _, _, _, _, ar = _geometria(r)
        tela, coperta = _tela(fatti, r, aspetto, J, O, W, H, ar, avanti)
        piccole[strato] = tela.resize(picc, Image.BILINEAR)

        def salva(k, strato=strato, tela=tela, coperta=coperta):
            tx, ty = k
            x0, y0 = tx * TASSELLO, ty * TASSELLO
            b = (x0 - M, y0 - M, min(W, x0 + TASSELLO) + M, min(H, y0 + TASSELLO) + M)
            tela.crop(b).save(grezzi / f"{strato}_{tx}_{ty}.jpg", "JPEG", quality=97)
            c = coperta.crop(b)
            if c.getextrema()[0] < 255:
                c.save(grezzi / f"{strato}_{tx}_{ty}_c.png")
        for _ in _in_parallelo(salva, quadrati):
            avanti()
        del tela, coperta
    # 2) maschera dell'acqua (giorno E notte)
    maschere, mari = {}, {}
    acqua_piccola = Image.new("L", picc, 0)
    kx, ky = picc[0] / W, picc[1] / H

    def maschera(k):
        tx, ty = k
        q, cop = grezzo("t", tx, ty)
        m = maschera_acqua(q, False)
        if len(strati) > 1:  # di notte: molto blu, oppure abbastanza blu E con le onde (i tetti blu sono lisci)
            qn = grezzo("n", tx, ty)[0]
            notte = ImageChops.lighter(maschera_acqua(qn, True),
                                       ImageChops.multiply(maschera_acqua(qn, True, ACQUA_NOTTE_ONDE), _onde(q)))
            m = ImageChops.multiply(m, notte)
        tg = maschera_togli(tx, ty, q.size)
        if tg:  # pezzi da togliere: acqua
            m = ImageChops.lighter(m, tg)
        # dove va il mare "ripetibile": bordi senza foto, pezzi tolti, e l'acqua vicino al bordo della mappa (sfuma)
        ox, oy = tx * TASSELLO - M, ty * TASSELLO - M
        mare = ImageChops.multiply(m, _banda(ox, oy, q.width, q.height, W, H, BANDA_MARE))
        # sugli ultimi pixel tutto mare comunque (lì i filtri vedono il nero fuori dalla mappa: righina chiara)
        mare = ImageChops.lighter(mare, _banda(ox, oy, q.width, q.height, W, H, 24))
        if cop:  # bordi senza foto: sono mare (fuori da Manhattan)
            m = ImageChops.lighter(m, ImageChops.invert(cop))
            mare = ImageChops.lighter(mare, ImageChops.invert(cop))
        if tg:
            mare = ImageChops.lighter(mare, tg)
        mm = m.crop((M, M, m.width - M, m.height - M))
        x0, y0 = round(tx * TASSELLO * kx), round(ty * TASSELLO * ky)
        x1, y1 = round((tx * TASSELLO + mm.width) * kx), round((ty * TASSELLO + mm.height) * ky)
        return k, m, (mare if mare.getextrema()[1] else None), mm.resize((max(1, x1 - x0), max(1, y1 - y0)),
                                                                           Image.BILINEAR), (x0, y0)
    for k, m, mare, piccolo, dove in _in_parallelo(maschera, quadrati):
        maschere[k], mari[k] = m, mare
        acqua_piccola.paste(piccolo, dove)
        avanti()
    acqua_piccola.save(cartella / "acqua.png")
    # 3) per ogni strato finale: ritocco, acqua uniforme, bordi senza foto col mare (onde vere ripetute), quadrati.
    #    Alba e tramonto NON sono fotografati per intero: dai campioni (stesso punto di giorno / all'alba / al tramonto)
    #    si ricava come il gioco cambia i colori (matrice 3x4) e la si applica alla mappa di giorno.
    luci = {}
    for st in ("a", "s"):
        if campioni and campioni.get("t") and campioni.get(st):
            try:
                luci[st] = _luce(campioni["t"], campioni[st])
            except Exception:  # noqa: BLE001 (campione rovinato: niente alba/tramonto, si usano giorno e notte)
                pass
    uscite = [(st, st, None) for st, _ in strati] + [(st, "t", luci[st]) for st in ("a", "s") if st in luci]
    tot = sum(len(f) for f, _ in giri) + len(strati) * nx * ny + nx * ny + len(uscite) * nx * ny
    fondo = (16, 28, 44)
    for uscita, sorgente, luce in uscite:
        notte = uscita != "t"
        if luce:
            colore = luce[1]
            guadagni = None
        else:
            colore = _colore_acqua(piccole[sorgente], acqua_piccola)
            guadagni = None if notte else _bilancio(piccole[sorgente], acqua_piccola)
            if colore and not notte:  # l'acqua di giorno nel gioco è grigio cemento: verso un azzurro
                colore = tuple(round(colore[k] * 0.45 + ACQUA_AZZURRA[k] * 0.55) for k in range(3))
        chiari = uscita == "n"
        riempi = _ritocco(Image.new("RGB", (1, 1), colore or fondo), notte, guadagni, chiari).getpixel((0, 0))
        if uscita == "t":
            fondo = riempi  # sfondo dell'esploratore

        def lavora(q, tx, ty):
            if luce:
                q = q.convert("RGB", luce[0])
            q = _ritocco(q, notte, guadagni, chiari)
            if colore:
                q = _acqua_uniforme(q, riempi, maschere[tx, ty])
            return q
        # onde del mare "ripetibile" (bordi, pezzi tolti, fuori dalla mappa): dal quadrato più "tutto mare" (senza bordi),
        # stessi colori e stessa grana dell'acqua vera (/2.5 una volta sola), ripetibili con periodo MARE_P (l'ultima
        # striscia sfuma sulla prima: niente specchi, che facevano un disegno a V)
        grana = None
        cand = [(sum(m.resize((32, 32)).getdata()), k) for k, m in maschere.items() if not grezzo(sorgente, *k)[1]]
        if cand and colore:
            k = max(cand)[1]
            q = grezzo(sorgente, *k)[0]
            if luce:
                q = q.convert("RGB", luce[0])
            q = _ritocco(q, notte, guadagni, chiari)
            g = ImageChops.subtract(q, q.filter(ImageFilter.BoxBlur(6)), 2.5, 128)
            grana = _ripetibile(g.crop((M, M, M + MARE_P + MARE_X, M + MARE_P + MARE_X)))
        pan = Image.new("RGB", (PANORAMICA, round(H * kp)), riempi)
        suff = "" if uscita == "t" else "_" + uscita
        if grana:  # il mare ripetibile (periodo 1024, fase assoluta = come nei quadrati): l'esploratore lo usa fuori
            ImageChops.add(Image.new("RGB", grana.size, riempi), grana, 1, -128).save(
                cartella / f"mare{suff}.jpg", "JPEG", quality=90)

        def finale(k, uscita=uscita, sorgente=sorgente, lavora=lavora, grana=grana, riempi=riempi):
            tx, ty = k
            q, _ = grezzo(sorgente, tx, ty)
            q = lavora(q, tx, ty)
            if mari[k]:  # bordi senza foto, pezzi tolti e acqua vicino al bordo: mare ripetibile
                mare = Image.new("RGB", q.size, riempi)
                if grana:
                    mare = ImageChops.add(mare, _piastrella(grana, tx * TASSELLO - M, ty * TASSELLO - M, q.size), 1, -128)
                q = Image.composite(mare, q, mari[k])
            q = q.crop((M, M, q.width - M, q.height - M))
            q.save(cartella / f"{uscita}_{tx}_{ty}.jpg", "JPEG", quality=92)
            # nella panoramica dal pixel arrotondato dell'inizio a quello della fine (prima: larghezza arrotondata a
            # parte = una colonna vuota ogni tanto, John: "riga azzurra")
            x0, y0 = round(tx * TASSELLO * kp), round(ty * TASSELLO * kp)
            x1, y1 = round((tx * TASSELLO + q.width) * kp), round((ty * TASSELLO + q.height) * kp)
            return q.resize((max(1, x1 - x0), max(1, y1 - y0)), Image.LANCZOS), (x0, y0)
        for piccolo, dove in _in_parallelo(finale, quadrati):
            pan.paste(piccolo, dove)
            avanti()
        pan.save(cartella / f"panoramica{suff}.jpg", "JPEG", quality=90)
        pan.resize(picc, Image.LANCZOS).save(cartella / f"piccola{suff}.jpg", "JPEG", quality=86)
    import shutil
    shutil.rmtree(grezzi, ignore_errors=True)
    hu = QUOTA * math.tan(FOV_FOTO / 2)
    us = sorted({f[0] for f in fatti0})
    vs = sorted({f[1] for f in fatti0})
    geo = {"versione": VERSIONE, "J": J, "O": O, "W": W, "H": H, "px_m": PX_M, "tassello": TASSELLO,
           "panoramica": [PANORAMICA, round(H * kp)], "anteprima": list(picc), "fondo": "#%02x%02x%02x" % tuple(fondo),
           "quando": time.strftime("%Y-%m-%d %H:%M"), "notte": len(giri) > 1, "strati": [u for u, _, _ in uscite],
           # da dove è stata fatta ogni foto (occhio): il punto scelto sulla mappa è un RAGGIO da lì (vedi occhio())
           "r": list(r0), "quota": QUOTA, "avanti": AVANTI, "foto": [[u, v] for u, v, *_ in fatti0],
           "passo": [min(_passi(us) or [1e6]), min(_passi(vs) or [1e6])], "mezzo": [hu, hu / aspetto],
           "cucitura": CUCITURA, "mare": MARE_P}
    (cartella / "mappa.json").write_text(json.dumps(geo), encoding="utf-8")
    return geo


def terra(cartella, geo, x, z):
    """Sulla mappa salvata il punto (x, z) è terra (strade, palazzi, parchi) o acqua? Guardo un intorno di ~60 m nella
    maschera dell'acqua (acqua.png; nelle mappe vecchie la luminosità della piccola). None = non so."""
    cartella = Path(cartella)
    try:
        m = Image.open(cartella / "acqua.png").convert("L")
        acqua = True
    except OSError:
        try:
            m = Image.open(cartella / "piccola.jpg").convert("L")
            acqua = False
        except OSError:
            return None
    k = m.width / geo["W"]
    px, py = mondo_pixel(geo, x, z)
    px, py = px * k, py * k
    raggio = max(2, round(30 * geo["px_m"] * k))
    if not (0 <= px < m.width and 0 <= py < m.height):
        return None
    si = tot = 0
    for dy in range(-raggio, raggio + 1):
        for dx in range(-raggio, raggio + 1):
            xx, yy = round(px + dx), round(py + dy)
            if 0 <= xx < m.width and 0 <= yy < m.height:
                tot += 1
                v = m.getpixel((xx, yy))
                si += v < 128 if acqua else v > 60
    return si >= max(2, tot * (0.15 if acqua else 0.08))


def mondo_pixel(geo, x, z):
    J, O = geo["J"], geo["O"]
    return J[0][0] * x + J[0][1] * z + O[0], J[1][0] * x + J[1][1] * z + O[1]


def pixel_mondo(geo, px, py):
    J, O = geo["J"], geo["O"]
    a, b, c, d = J[0][0], J[0][1], J[1][0], J[1][1]
    det = a * d - b * c
    u, v = px - O[0], py - O[1]
    return (d * u - b * v) / det, (-c * u + a * v) / det


def occhio(geo, x, z):
    """Le foto della mappa sono in PROSPETTIVA (da QUOTA m): un tetto alto compare spostato verso l'esterno della foto
    rispetto a dov'è davvero (un palazzo di 300 m a 600 m dal centro della foto: ~90 m, cioè la strada accanto). Il punto
    (x, z) letto sulla mappa (piano del suolo) è quindi un RAGGIO: dall'occhio della foto che ha dato quel pixel fino a
    (x, 0, z); la prima cosa che il raggio tocca è quello che vedevi. Ritorna l'occhio (x, y, z) o None (mappe vecchie).
    La foto è quella che si vede in quel punto della cucitura: l'ULTIMA incollata il cui rettangolo (metà passo + SFUMA,
    senza gli angoli in alto) contiene il punto. (Prima prendevo la più vicina: nella fascia di sovrapposizione vince
    quella incollata dopo, e il raggio passava accanto al palazzo.)"""
    foto, r = geo.get("foto"), geo.get("r")
    if not foto or not r:
        return None
    rx, rz = r
    u, v = x * rx + z * rz, x * rz - z * rx
    hu, hv = geo.get("mezzo") or (1e9, 1e9)
    scelta = None
    for k in range(len(foto) - 1, -1, -1):
        uc, vc = foto[k][:2]
        a0, a1, b0, b1 = _rettangolo(foto, k, geo.get("cucitura", SFUMA))
        du, dv = u - uc, v - vc
        if not (max(a0, -hu) <= du <= min(a1, hu) and max(b0, -hv) <= dv <= min(b1, hv)):
            continue
        if dv < -hv * 0.82 and abs(du) > hu * 0.4:  # angoli in alto tolti dalle maschere (FPS e messaggi di Dolphin)
            continue
        scelta = (uc, vc)
        break
    if scelta is None:
        su, sv = geo.get("passo") or [1.0, 1.0]
        scelta = min((f[:2] for f in foto), key=lambda f: max(abs(u - f[0]) / su, abs(v - f[1]) / sv))
    lx, lz = mondo(r, *scelta)
    return lx, float(geo.get("quota", QUOTA)), lz - float(geo.get("avanti", AVANTI))
