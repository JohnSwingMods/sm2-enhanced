"""VISTA 3D DELLA CITTÀ (menu in gioco > Mondo > Viaggio, Y; idea di John 2026-10-19: "navigare in 3D nella mappa con la
levetta destra, cambiando angolazione e zoom"; poi: "come un sostituto della mappa: la vedi dall'alto e poi ti sposti,
giri e zoommi").

Con la mappa grande del gioco aperta, la sua telecamera (struttura trovata da mappa_citta.trova_struttura: +0x00 centro,
+0x0C punto guardato) si può INCLINARE: spostando il punto guardato in orizzontale il gioco disegna la città 3D vera
(palazzi, fiume, skyline, cielo) da qualsiasi angolo (provato il 2026-10-19, foto in mappa3d\\mosaico.jpg). Il "su" e il
bersaglio della vista li passa l'aggancio Gecko teletrasporto.codice_su3d (senza, girando oltre 90° si capovolgeva).
La telecamera gira attorno al punto guardato T (a terra, y = 0): direzione `a` (avanti = (cos a, sin a); a = pi/2 = come la
mappa piatta: x a destra, z in su), inclinazione `p` (sotto l'orizzonte, 90° = dall'alto), distanza `d`.
Si parte DALL'ALTO, come una mappa. Comandi (come l'esploratore della mappa piatta): levetta sinistra muove, levetta destra
x gira / y zoom, LT/RT inclinano (RT verso l'orizzonte), L3/R3 tornano dall'alto. Tutto ammorbidito (prima: a scatti).
IL GIOCO TIRA IL CENTRO DELLA MAPPA VERSO SPIDEY quando è a più di ~400 m (misurato: ~100 m/s, era lo "scivolamento" e gli
scatti della prima prova, Spidey sotto il punto guardato e la telecamera inclinata lontana): Spidey va sotto la TELECAMERA.
Icone e cornici della mappa via col byte hud_ram.FOTO. Uscendo si rimette tutto com'era (Spidey, icone, "su")."""
import json
import math
import os
import struct

import app_core as core
import cam_ps4
import hud_ram
import mappa_citta
import teletrasporto as tp

P_MIN, P_MAX = math.radians(20), math.radians(86)  # inclinazione: verso l'orizzonte .. dall'alto (dritta in giù la
# direzione dello schermo non sarebbe definita)
# ALBA E TRAMONTO: col sole basso sull'orizzonte, inclinando la vista fino a vederlo il gioco (mappa + bagliore del sole)
# manda a Dolphin comandi sbagliati e si pianta ("GFX FIFO: opcode sconosciuto"; provato 2026-10-22 alle 17:36, di notte
# niente). In quelle ore l'inclinazione si ferma a P_MIN_SOLE: il bordo alto dell'immagine resta sotto l'orizzonte (FOV
# verticale ~63°, metà ~32°).
P_MIN_SOLE = math.radians(40)
ORE_SOLE_BASSO = ((4.5, 9.5), (14.5, 19.75))
D_MIN, D_MAX = 40.0, 2600.0
QUOTA_MIN = 170.0  # sotto ~140 m il gioco toglie i modelli semplificati della mappa e mette quelli veri, che sono caricati
# solo intorno a dove sei: lontano i palazzi sparivano zoomando (John; misurato: 160 ok, 140 iniziano a sparire, 120 quasi tutti)
QUOTA_MAX = 1700.0  # sopra, col campo visivo normale, il gioco carica tutta la città (si pianta a ~4000 col FOV normale)
D_INIZIO = 900.0
SEGUI = 150.0  # metri: Spidey spostato sotto la telecamera quando se ne allontana di più (il gioco tira il centro della
# mappa verso di lui oltre ~400 m)
VEL_MUOVI = 0.75  # x distanza al secondo (levetta tutta)
GIRO_SENZA = math.radians(35)  # senza l'aggancio del "su" nel gioco la direzione resta entro questo dall'inizio
VEL_GIRA, VEL_INCL, VEL_ZOOM = 1.6, 0.9, 1.3  # rad/s, rad/s, e-volte/s
MORBIDO = 10.0  # 1/s: quanto in fretta la telecamera raggiunge dove la porti
D_POSTO = 450.0  # andando a un posto salvato (Y) la telecamera scende fin qui (sotto ~500 m compaiono anche i dettagli)
ANTEPRIMA = core.CONF_DIR / "mappa3d.jpg"  # foto dall'alto all'apertura: anteprima nella pagina Viaggio
ANTEPRIMA_DATI = core.CONF_DIR / "mappa3d.json"  # telecamera di quella foto (per mettere "tu" dove sei adesso)
ICONA = core.CONF_DIR / "icona_spidey_mappa.png"  # l'icona di Spidey della mappa del gioco, ritagliata da una foto (per la
# freccia sul bordo quando sei fuori dallo schermo: John la voleva uguale all'icona, non la scritta "Tu")
# DISTANZE DELLA CITTÀ VISTA DA LONTANO (0x80236BB0, uguale ITA/USA: disegna i 93 "gruppi" di palazzi, quadrati di 280 m;
# con la mappa aperta i modelli veri non si disegnano mai). Per ogni gruppo il quadrato della distanza dalla telecamera:
# oltre r13-0x76E4 (3000 m, se la telecamera è sopra r13-0x76E8 = 50 m; se no r13-0x76E0, 1700 m) non si disegna; con la
# mappa aperta il limite sparisce solo con la telecamera sopra 1000 m (0x8046AD68). Oltre r13-0x76DC (900 m) il gruppo è
# "lontano" (versione semplificata). Nella vista 3D la telecamera sta quasi sempre sotto i 1000 m: inclinando o zoomando
# interi quartieri lontani comparivano e sparivano (John). Mentre la vista è aperta: niente limite di distanza (come fa il
# gioco sopra i 1000 m); uscendo si rimettono i valori di prima. Variabili del gioco (non codice): si scrivono dal vivo.
# MAI la soglia dei 900 m: con tutti i gruppi "vicini" il gioco disegnava tutta la città dettagliata e allontanando la
# telecamera Dolphin si piantava ("GFX FIFO: opcode sconosciuto", provato 2026-10-22).
DISTANZE = (-0x76E4, -0x76E0)
SENZA_LIMITE = 1e32
R13 = {"GK2I52": 0x805732E0}
R13_ALTRE = 0x80573260
VISTA = {"GK2I52": 0x805732E0 - 0x5ACC}  # r13 - 0x5ACC: puntatore alla vista DISEGNATA (+8 occhio, +0x14 su, +0x20
VISTA_ALTRE = 0x80573260 - 0x5ACC  # avanti); le altre versioni hanno r13 = 0x80573260


DISTANZE_FILE = core.CONF_DIR / "mappa3d_distanze.json"


def rimetti_distanze(dme, valori):
    """Rimette i limiti di distanza della città (scritti da Vista3D._distanze_via) se ci sono ancora i nostri."""
    for a, v in valori.items():
        a = int(a)
        if dme.read_bytes(a, 4) == struct.pack(">f", SENZA_LIMITE):  # (confronto dei byte: 1e32 a 32 bit non è 1e32)
            dme.write_bytes(a, struct.pack(">f", float(v)))
    try:
        DISTANZE_FILE.unlink()
    except OSError:
        pass


def vista_disegnata(dme, gid):
    """Telecamera dell'ultimo fotogramma disegnato (occhio, su, avanti) o None."""
    pv = dme.read_word(VISTA.get(gid, VISTA_ALTRE))
    if not 0x80000000 <= pv < 0x81800000:
        return None
    f = struct.unpack(">9f", dme.read_bytes(pv + 8, 36))
    return f[0:3], f[3:6], f[6:9]


def proietta(cam, fov, aspetto, x, y, z):
    """Punto del mondo -> (nx, ny) in -1..1 (destra, su) con la telecamera cam = (occhio, su, avanti), FOV orizzontale,
    aspetto = larghezza / altezza della parte disegnata; None se dietro."""
    (ex, ey, ez), (ux, uy, uz), (fx, fy, fz) = cam
    rx, ry, rz = uy * fz - uz * fy, uz * fx - ux * fz, ux * fy - uy * fx  # destra = su x avanti
    n = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
    rx, ry, rz = rx / n, ry / n, rz / n
    sx, sy, sz = fy * rz - fz * ry, fz * rx - fx * rz, fx * ry - fy * rx  # su dello schermo = avanti x destra
    dx, dy, dz = x - ex, y - ey, z - ez
    zc = dx * fx + dy * fy + dz * fz
    if zc < 5:
        return None
    th = math.tan(fov / 2)
    return (dx * rx + dy * ry + dz * rz) / zc / th, (dx * sx + dy * sy + dz * sz) / zc / (th / aspetto)


def proietta_anteprima(x, y, z):
    """Dove sta (x, y, z) nella foto dell'anteprima: (u, v) 0..1 (anche fuori), o None (niente dati / dietro)."""
    try:
        d = json.loads(ANTEPRIMA_DATI.read_text(encoding="utf-8"))
        n = proietta((d["occhio"], d["su"], d["avanti"]), d["fov"], d["aspetto"], x, y, z)
    except Exception:  # noqa: BLE001
        return None
    return None if n is None else ((n[0] + 1) / 2, (1 - n[1]) / 2)


class Vista3D:
    def __init__(self, viaggio):
        self.v = viaggio
        self.gid = viaggio.gid
        self.P = None

    def entra(self):
        """Mappa del gioco GIÀ aperta. Trova la telecamera, ricorda tutto e parte dall'alto sopra il centro della mappa."""
        self.pos0 = self.v.posizione()
        mappa_citta.Giro(self.gid, ".")._aspetta_ferma()
        with core.DME_LOCK:
            dme = self.v._dme()
            self.P = mappa_citta.trova_struttura(dme, self.gid)
            if not self.P:
                raise RuntimeError("telecamera")
            self.v0 = struct.unpack(">6f", dme.read_bytes(self.P, 24))
            self.fov = struct.unpack(">f", dme.read_bytes(mappa_citta.fov_ind(self.gid), 4))[0]
            rx, _, rz = struct.unpack(">3f", dme.read_bytes(self.P + 0x24, 12))
            self.modo = tp.su3d_versione(dme, self.gid)  # 2 = il gioco calcola il movimento a ogni fotogramma
            # icone via; nel modo 2 resta l'icona di Spidey del gioco (ferma sul punto, Spidey non si sposta più)
            dme.write_byte(hud_ram.FOTO, 2 if self.modo == 2 else 1)
            self.su3d = self.modo >= 1
            dme.write_bytes(tp.SU3D_VETTORE, struct.pack(">3f", 0.0, 1.0, 0.0))
            self.distanze = self._distanze_via(dme)
        n = math.hypot(rx, rz) or 1.0
        a_mappa = math.atan2(rx / n, -rz / n)  # su dello schermo della mappa del gioco: (-rz, rx)
        # con l'aggancio: orientata come la mappa piatta (x a destra); senza: come la mappa del gioco (non si può girare)
        self.a0 = math.pi / 2 if self.su3d else a_mappa
        ora = core.ora_leggi(self.gid)
        h = ora[0] / 3600 if ora else 12.0
        self.p_min = P_MIN_SOLE if any(a <= h <= b for a, b in ORE_SOLE_BASSO) else P_MIN
        self.voluta = {"a": self.a0, "p": P_MAX, "d": D_INIZIO, "x": self.v0[3], "z": self.v0[5]}
        self.ora = dict(self.voluta)
        self.spidey = (self.pos0[0], self.pos0[2])
        self.box = None  # parte disegnata della finestra del gioco (senza bande nere), dalla prima foto
        self.copia = 0
        if self.modo == 2:
            with core.DME_LOCK:
                dme = self.v._dme()
                self.scrivi_est(dme.read_word(cam_ps4.VERSIONI[self.gid]["vi"]), self.occhio(), (self.tx, 0.0, self.tz))
                dme.write_word(tp.SU3D_ATTIVA, 2)
        else:
            self.scrivi()
            if self.su3d:
                with core.DME_LOCK:
                    self.v._dme().write_word(tp.SU3D_ATTIVA, 1)

    def _distanze_via(self, dme):
        """Toglie i limiti di distanza della città (DISTANZE) e ritorna {indirizzo: valore di prima} per rimetterli."""
        if os.environ.get("SPIDEY_M3_LIMITI"):  # (prove: come il gioco)
            return {}
        base = R13.get(self.gid, R13_ALTRE)
        prima = {}
        for o in DISTANZE:
            a = base + o
            v = struct.unpack(">f", dme.read_bytes(a, 4))[0]
            if 1e4 <= v < 1e20:  # (solo se c'è il valore del gioco: quadrati di distanze di centinaia/migliaia di metri)
                prima[a] = v
                dme.write_bytes(a, struct.pack(">f", SENZA_LIMITE))
        try:  # anche su disco: se l'app si chiude a metà, all'avvio dopo li rimette (_sorveglia_ora)
            core.scrivi_sicuro(DISTANZE_FILE, json.dumps({"gid": self.gid, "valori": {str(k): v for k, v in prima.items()}}))
        except Exception:  # noqa: BLE001
            pass
        return prima

    def distanze_rimetti(self):
        rimetti_distanze(self.v._dme(), getattr(self, "distanze", {}))
        self.distanze = {}

    def foto(self):
        """Foto della finestra del gioco (vista 3D com'è adesso, senza menu né segnalini): salva l'anteprima della pagina
        Viaggio e ricorda dove sta la parte disegnata (per i segnalini). True = fatta."""
        import time
        g = core.finestra_gioco()
        with core.DME_LOCK:
            dme = self.v._dme()
            prima = dme.read_byte(hud_ram.FOTO)
            dme.write_byte(hud_ram.FOTO, 1)  # nella foto niente icona di Spidey: dove sei la mette la pagina (pallino "tu")
        time.sleep(0.08)
        with core.DME_LOCK:
            cam = vista_disegnata(self.v._dme(), self.gid)
        try:
            im = core.foto_finestra(g, immagine=True) if g else None
        finally:
            with core.DME_LOCK:
                self.v._dme().write_byte(hud_ram.FOTO, prima)
        if im is None:
            return False
        im = im.convert("RGB")
        self.box, self.foto_dim = mappa_citta.contenuto(im), im.size
        a = im.crop(self.box)
        a.thumbnail((720, 720))
        tmp = ANTEPRIMA.with_suffix(".tmp")
        a.save(tmp, "JPEG", quality=85)
        tmp.replace(ANTEPRIMA)
        if cam:
            b = self.box
            ANTEPRIMA_DATI.write_text(json.dumps({"occhio": cam[0], "su": cam[1], "avanti": cam[2], "fov": self.fov,
                                                  "aspetto": (b[2] - b[0]) / max(1, b[3] - b[1])}), encoding="utf-8")
        return True

    def icona_spidey(self):
        """Ritaglia l'icona di Spidey disegnata dal gioco: due foto, con l'icona (FOTO 2) e senza (FOTO 1), e la differenza
        attorno a dove sta Spidey sullo schermo. Salvata in ICONA (RGBA). Da fare sotto il velo (le icone spariscono un
        attimo). True = fatta."""
        import time
        from PIL import Image, ImageChops
        if self.modo != 2 or not self.box:
            return False
        g = core.finestra_gioco()
        if not g:
            return False
        foto = []
        for f in (2, 1):
            with core.DME_LOCK:
                self.v._dme().write_byte(hud_ram.FOTO, f)
            time.sleep(0.12)
            with core.DME_LOCK:
                cam = vista_disegnata(self.v._dme(), self.gid)
            foto.append(core.foto_finestra(g, immagine=True))
        with core.DME_LOCK:
            self.v._dme().write_byte(hud_ram.FOTO, 2)
        a, b = foto
        if a is None or b is None or a.size != b.size or not cam:
            return False
        b0, b1, b2, b3 = self.box
        n = proietta(cam, self.fov, (b2 - b0) / max(1, b3 - b1), *self.pos0)
        if n is None:
            return False
        px, py = b0 + (n[0] + 1) / 2 * (b2 - b0), b1 + (1 - n[1]) / 2 * (b3 - b1)
        r = int(max(60, (b2 - b0) * 0.06))
        rq = (int(px - r), int(py - r), int(px + r), int(py + r))
        ca, cb = a.convert("RGB").crop(rq), b.convert("RGB").crop(rq)
        d = ImageChops.difference(ca, cb).convert("L")  # (l'acqua che si muove cambia poco: l'icona tanto)
        bb = d.point(lambda v: 255 if v > 28 else 0).getbbox()
        if not bb or bb[2] - bb[0] < 8 or bb[3] - bb[1] < 8 or bb[2] - bb[0] > 1.8 * r or                 not 0.55 < (bb[2] - bb[0]) / (bb[3] - bb[1]) < 1.9:
            return False
        # l'icona è un ovale (cerchio stirato dal 16:9): trasparenza = l'ovale che contiene i pixel cambiati (dalla sola
        # differenza veniva bucata dove il fondo assomiglia all'icona), bordo liscio disegnato 4 volte più grande
        from PIL import ImageDraw
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        alfa = Image.new("L", (w * 4, h * 4), 0)
        ImageDraw.Draw(alfa).ellipse((2, 2, w * 4 - 3, h * 4 - 3), fill=255)
        ic = ca.crop(bb).convert("RGBA")
        ic.putalpha(alfa.resize((w, h), Image.LANCZOS))
        tmp = ICONA.with_suffix(".tmp")
        ic.save(tmp, "PNG")
        tmp.replace(ICONA)
        return True

    def schermo(self, x, y, z, rett, cam=None):
        """Punto del mondo -> pixel dello schermo (rett = origine e misure della parte interna della finestra del gioco),
        o None se dietro / fuori. cam = telecamera DISEGNATA (vista_disegnata: i segnalini seguono il fotogramma che si
        vede, non il mio stato), se no la mia. FOV del gioco = orizzontale sulla parte disegnata (come nel giro
        fotografico)."""
        if not self.box or not self.su3d:
            return None
        if cam is None:
            e = self.occhio()
            f = (self.tx - e[0], -e[1], self.tz - e[2])
            n = math.sqrt(sum(c * c for c in f))
            cam = (e, (0.0, 1.0, 0.0), tuple(c / n for c in f))
        b0, b1, b2, b3 = self.box
        cw, ch = b2 - b0, b3 - b1
        n = proietta(cam, self.fov, cw / ch, x, y, z)
        if n is None or abs(n[0]) > 1.02 or abs(n[1]) > 1.02:
            return None
        ox, oy, sx, sy = rett  # pixel veri: origine della parte interna della finestra e scala foto -> schermo
        return ox + (b0 + (n[0] + 1) / 2 * cw) * sx, oy + (b1 + (1 - n[1]) / 2 * ch) * sy

    def bordo(self, x, y, z, rett, cam=None, margine=46):
        """Punto fuori dallo schermo -> (pixel sul bordo della parte disegnata, angolo verso di lui), per la freccia "tu"
        (John: andando lontano non si capiva più dove fosse Spidey). None se non si può (senza foto / senza aggancio)."""
        if not self.box or not self.su3d:
            return None
        if cam is None:
            e = self.occhio()
            f = (self.tx - e[0], -e[1], self.tz - e[2])
            n = math.sqrt(sum(c * c for c in f))
            cam = (e, (0.0, 1.0, 0.0), tuple(c / n for c in f))
        (ex, ey, ez), (ux, uy, uz), (fx, fy, fz) = cam
        rx, ry, rz = uy * fz - uz * fy, uz * fx - ux * fz, ux * fy - uy * fx  # destra = su x avanti (come proietta)
        n = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
        rx, ry, rz = rx / n, ry / n, rz / n
        sx_, sy_, sz_ = fy * rz - fz * ry, fz * rx - fx * rz, fx * ry - fy * rx
        dx, dy, dz = x - ex, y - ey, z - ez
        vr, vu = dx * rx + dy * ry + dz * rz, dx * sx_ + dy * sy_ + dz * sz_  # a destra / in su sullo schermo
        if abs(vr) + abs(vu) < 1e-6:
            return None
        b0, b1, b2, b3 = self.box
        ox, oy, kx, ky = rett
        w, h = (b2 - b0) * kx, (b3 - b1) * ky
        cx, cy = ox + (b0 * kx) + w / 2, oy + (b1 * ky) + h / 2
        px, py = vr, -vu  # y dello schermo in giù
        k = min((w / 2 - margine) / max(1e-6, abs(px)), (h / 2 - margine) / max(1e-6, abs(py)))
        return (cx + px * k, cy + py * k), math.atan2(py, px)

    def vola_a(self, x, z):
        """La telecamera va (morbida) sopra (x, z), un po' più in basso se era alta."""
        self.voluta["x"], self.voluta["z"] = x, z
        self.voluta["d"] = min(self.voluta["d"], max(D_POSTO, QUOTA_MIN / math.sin(self.voluta["p"])))

    # punto guardato adesso (ammorbidito)
    @property
    def tx(self):
        return self.ora["x"]

    @property
    def tz(self):
        return self.ora["z"]

    def occhio(self, s=None):
        s = s or self.ora
        cp = math.cos(s["p"])
        return (s["x"] - s["d"] * cp * math.cos(s["a"]), s["d"] * math.sin(s["p"]), s["z"] - s["d"] * cp * math.sin(s["a"]))

    def passo(self, dt, sx, sy, dx, dy, incl=0, dall_alto=False):
        """Levette (-1..1, su = negativo): (sx, sy) muovi, dx gira, dy zoom (su = vicino); incl -1 (LT, verso l'alto) ..
        1 (RT, verso l'orizzonte); dall_alto = di nuovo dall'alto, orientata come all'inizio."""
        f = lambda x: math.copysign(min(1.0, x * x), x) if abs(x) > 0.18 else 0.0  # zona morta + curva morbida
        w = self.voluta
        if dall_alto:
            w["p"], w["a"] = P_MAX, self.a0 + round((w["a"] - self.a0) / (2 * math.pi)) * 2 * math.pi
        # gira: levetta a destra = la vista gira a destra (l'avanti va verso la destra: a cala)
        w["a"] -= f(dx) * VEL_GIRA * dt
        if not self.su3d:
            w["a"] = max(self.a0 - GIRO_SENZA, min(self.a0 + GIRO_SENZA, w["a"]))
        w["d"] *= math.exp(f(dy) * VEL_ZOOM * dt)
        w["p"] = max(getattr(self, "p_min", P_MIN), min(P_MAX, w["p"] - incl * VEL_INCL * dt))
        sp = math.sin(w["p"])
        w["d"] = max(D_MIN, QUOTA_MIN / sp, min(D_MAX, w["d"], QUOTA_MAX / sp))
        mx, my = f(sx), -f(sy)
        if mx or my:
            v = w["d"] * VEL_MUOVI * dt
            ax, az = math.cos(w["a"]), math.sin(w["a"])  # avanti
            rx, rz = az, -ax  # destra dello schermo (misurato: con avanti (-rz, rx) la destra è r)
            lim = mappa_citta.LIMITI
            w["x"] = max(lim[0] - 300, min(lim[2] + 300, w["x"] + (rx * mx + ax * my) * v))
            w["z"] = max(lim[1] - 300, min(lim[3] + 300, w["z"] + (rz * mx + az * my) * v))
        k = 1 - math.exp(-MORBIDO * dt)
        for c in self.ora:
            self.ora[c] += (w[c] - self.ora[c]) * k

    def segui(self):
        if self.modo == 2:  # il gioco calcola il movimento: non serve, e Spidey (e la sua icona) restano dove sei
            return
        ex, _, ez = self.occhio()
        if math.hypot(ex - self.spidey[0], ez - self.spidey[1]) > SEGUI:
            self.spidey = (ex, ez)
            self.v.metti((ex, 520.0, ez))

    def prevedi(self, dt, *levette):
        """Occhio e bersaglio dopo un altro passo con le stesse levette, senza cambiare lo stato."""
        w, o = dict(self.voluta), dict(self.ora)
        self.passo(dt, *levette)
        e, t = self.occhio(), (self.tx, 0.0, self.tz)
        self.voluta, self.ora = w, o
        return e, t

    def scrivi_est(self, n, e1, t1):
        """Modo 2: stato per lo scatto n del contatore video + quanto cambia in uno scatto (fino a e1 / t1) nella copia
        libera, poi la copia diventa quella valida (teletrasporto.EST). Anche la struttura della telecamera della mappa
        (il gioco la usa per il dettaglio della città)."""
        e0, t0 = self.occhio(), (self.tx, 0.0, self.tz)
        ve = [b - a for a, b in zip(e0, e1)]
        vt = [b - a for a, b in zip(t0, t1)]
        self.copia ^= 0x40
        with core.DME_LOCK:
            dme = self.v._dme()
            dme.write_bytes(tp.EST + self.copia, struct.pack(">12fI", *e0, *t0, *ve, *vt, n & 0xFFFFFFFF))
            dme.write_word(tp.EST + 0x80, self.copia)
            dme.write_bytes(self.P, struct.pack(">6f", *e0, *t0))

    def scrivi(self):
        ex, ey, ez = self.occhio()
        with core.DME_LOCK:
            dme = self.v._dme()
            dme.write_bytes(self.P, struct.pack(">6f", ex, ey, ez, self.tx, 0.0, self.tz))
            dme.write_bytes(tp.SU3D_BERSAGLIO, struct.pack(">3f", self.tx, 0.0, self.tz))  # per l'aggancio (lookAt)

    def esci(self, rimetti_spidey=True, dopo_tasto=None):
        """Senza rimettere la telecamera della mappa (si vedeva per un attimo la mappa normale con le icone): riaprendo la
        mappa il gioco la rifà da capo. rimetti_spidey (B): Spidey dov'era, mappa chiusa, icone di nuovo visibili. Senza
        (A, poi il viaggio chiude la mappa): le icone restano nascoste, le rimette chi chiama (icone_visibili)."""
        if not self.P or not rimetti_spidey:  # (il "su" del gioco torna in icone_visibili, a mappa chiusa)
            return
        # ogni passo per conto suo: se uno fallisce (memoria del gioco che non risponde per un attimo) gli altri si fanno
        # lo stesso; prima un errore a metà lasciava la mappa aperta e ferma con la telecamera dell'app (video di John)
        for nome, passo in (("metti", lambda: self.v.metti(tuple(self.pos0))),
                            ("chiudi", lambda: self.v.chiudi_mappa(dopo_tasto=dopo_tasto))):
            try:
                passo()
            except Exception as e:  # noqa: BLE001
                core.log_errore(f"vista 3d, uscita ({nome}): {e!r}")
        self.icone_visibili()
        try:
            self.v._tieni(tuple(self.pos0), 1.0)
        except Exception:  # noqa: BLE001
            pass

    def icone_visibili(self, tentativi=50):
        """Icone di nuovo visibili e il "su"/movimento della telecamera ridati al gioco; riprova per ~5 s se la memoria non
        risponde. True = fatto."""
        import time
        for _ in range(tentativi):
            try:
                with core.DME_LOCK:
                    dme = self.v._dme()
                    dme.write_word(tp.SU3D_ATTIVA, 0)
                    dme.write_byte(hud_ram.FOTO, 0)
                    rimetti_distanze(dme, getattr(self, "distanze", {}))
                    self.distanze = {}
                return True
            except Exception:  # noqa: BLE001
                time.sleep(0.1)
        core.log_errore("vista 3d: icone e telecamera della mappa non rimesse (il gioco non risponde)")
        return False
