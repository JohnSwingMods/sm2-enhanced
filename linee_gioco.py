"""Linee e scritte della schermata Opzioni > Controller del gioco, ridisegnate dal vivo nella memoria di Dolphin.

Il gioco disegna le linee gialle come rettangolini larghi 1 (coordinate dello schermo virtuale 640x448): ogni vertice è
un record (x, y, u, v, colore) di 0x14 byte, e i 4 vertici di una linea stanno a coppie di record consecutivi: una coppia
per il lato in x0 ((x0, y0), (x0, y1)) e una per il lato in x1 (a volte le due coppie sono in posti diversi della
memoria). Le scritte hanno (x, y) seguiti da 1.0 x4 e dal loro colore; il testo si legge dal puntatore 0x18 byte prima.
Gli elementi esistono solo col menu di pausa aperto e ogni volta in un posto diverso: li cerco per POSIZIONE (le
coordinate originali del gioco sono sempre quelle), poi li sposto dove serve per il controller scelto.

Coordinate: x_virtuale = 0.393 * x_texture + 219.9, y_virtuale = 0.414 * y_texture + 157.4 (texture 512x512)."""
import struct

GIALLO = 0xE6D03FFF
ZONA = (0x80500000, 0x80B00000)  # dove stanno gli elementi dell'interfaccia (sotto i buffer di disegno 0x811x-0x812x)
TX, TY = (0.393, 219.9), (0.414, 157.4)  # texture (512) -> schermo virtuale


def virt(p):
    return (TX[0] * p[0] + TX[1], TY[0] * p[1] + TY[1])


# Le 12 linee della configurazione A, coi rettangoli ORIGINALI dei loro pezzi (x0, x1, y0, y1) e la riga della scritta.
# lato: s = scritta a sinistra (x 80, la linea parte da lì), d = a destra (x 560).
ORIGINALI = {
    "scatto":    {"lato": "s", "riga": 209, "pezzi": [(80, 255, 209, 210), (254, 255.25, 209, 227)]},
    "muovi":     {"lato": "s", "riga": 259, "pezzi": [(80, 263, 259, 260), (262, 263, 259, 268)]},
    "riflessi":  {"lato": "s", "riga": 279, "pezzi": [(80, 288, 279, 280), (287, 288, 279, 300)]},
    "blocca":    {"lato": "s", "riga": 319, "pezzi": [(80, 288, 319, 320)]},
    "start":     {"lato": "s", "riga": 359, "pezzi": [(80, 320, 359, 360), (319, 320.25, 266, 360)]},
    "attacco":   {"lato": "d", "riga": 169, "pezzi": [(354, 560, 169, 170), (354, 355.25, 169, 271)]},
    "ragnatela": {"lato": "d", "riga": 189, "pezzi": [(369, 560, 189, 190), (369, 370.25, 189, 240)]},
    "oscilla":   {"lato": "d", "riga": 209, "pezzi": [(376, 560, 209, 210), (376, 377, 209, 213)]},
    "centra":    {"lato": "d", "riga": 239, "pezzi": [(386, 560, 239, 240), (386, 387, 226, 240)]},
    "schiva":    {"lato": "d", "riga": 269, "pezzi": [(405, 560, 269, 270)]},
    "salto":     {"lato": "d", "riga": 299, "pezzi": [(376, 560, 299, 300), (376, 377, 276, 300)]},
    "guarda":    {"lato": "d", "riga": 319, "pezzi": [(352, 560, 319, 320), (352, 353, 315, 320)]},
}


def leggi_zona(dme):
    a, b = ZONA
    return dme.read_bytes(a, b - a)


def _record(buf, o):
    x, y, u, v, c = struct.unpack_from(">4fI", buf, o)
    return x, y, c


def trova_lati(buf, rettangoli):
    """Per ogni rettangolo (x0, x1, y0, y1): gli indirizzi delle due coppie di record (lato x0 e lato x1).
    {rettangolo: [(indirizzo_coppia, x_del_lato), ...]}"""
    cerca = {}
    for r in rettangoli:
        x0, x1, y0, y1 = r
        for xs in (x0, x1):
            cerca.setdefault((round(xs, 2), round(y0, 2), round(y1, 2)), []).append(r)
    trovati = {r: [] for r in rettangoli}
    col = struct.pack(">I", GIALLO)
    i = buf.find(col)
    while i >= 0:
        o = i - 0x10  # inizio del record (x, y, u, v, colore)
        if o >= 0 and o % 4 == 0 and o + 0x28 <= len(buf):
            xa, ya, ca = _record(buf, o)
            xb, yb, cb = _record(buf, o + 0x14)
            if abs(xa - xb) < 1e-3 and abs(ya - yb) >= 0.9:  # il colore del 2o vertice a volte è sovrascritto (non serve)
                k = (round(xa, 2), round(min(ya, yb), 2), round(max(ya, yb), 2))
                for r in cerca.get(k, []):
                    trovati[r].append((ZONA[0] + o, xa))
        i = buf.find(col, i + 4)
    return trovati


def trova_scritte(buf, lato_x=(80.0, 560.0)):
    """Posizioni delle scritte: (x, y) seguiti da 1.0 x4. {(x, y): [indirizzo della x, ...]}"""
    out = {}
    uno = struct.pack(">4f", 1, 1, 1, 1)
    i = buf.find(uno)
    while i >= 0:
        o = i - 8
        if o >= 0 and o % 4 == 0:
            x, y = struct.unpack_from(">2f", buf, o)
            if x in lato_x and 100 <= y <= 420 and y == int(y):
                out.setdefault((x, y), []).append(ZONA[0] + o)
        i = buf.find(uno, i + 4)
    return out


def sposta_rettangolo(dme, lati, vecchio, nuovo):
    """Riscrive i record dei due lati di un rettangolo: ogni vertice va nel punto corrispondente del rettangolo nuovo."""
    x0, x1, y0, y1 = vecchio
    n0, n1, m0, m1 = nuovo
    for indirizzo, xs in lati:
        nx = n0 if abs(xs - x0) < abs(xs - x1) else n1
        for k in range(2):
            a = indirizzo + k * 0x14
            y = dme.read_float(a + 4)
            ny = m0 if abs(y - y0) < abs(y - y1) else m1
            dme.write_float(a, nx)
            dme.write_float(a + 4, ny)


def testo_scritta(dme, indirizzo):
    """Testo di una scritta (puntatore 0x18 byte prima della sua x), None se non è una scritta vera."""
    try:
        p = dme.read_word(indirizzo - 0x18)
        if not 0x80000000 <= p < 0x81800000:
            return None
        s = dme.read_bytes(p, 64).split(b"\0")[0]
        return s.decode("latin1") if s and all(32 <= c < 256 or c == 10 for c in s) else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- disposizione per un controller
# A quale tasto va ogni linea (stessi nomi di contenuti/Controller/tasti.json).
TASTO = {"scatto": "lb", "muovi": "ls", "riflessi": "dpad_su", "blocca": "dpad_giu", "start": "start", "attacco": "x",
         "ragnatela": "y", "oscilla": "rb", "centra": "back", "schiva": "b", "salto": "a", "guarda": "rs"}
LETTERA = 8.6  # larghezza media di una lettera delle scritte (schermo virtuale)
ALTO_TESTO = 13  # le scritte stanno sopra la loro linea (la y della scritta = y della linea)
PASSO = 18  # distanza minima tra due righe dello stesso lato
RIGHE = (166, 370)  # dove possono stare le righe
X_SX, X_DX = 80, 560
ALLINEA = {"s": 0x1415, "d": 0x1445}  # campo +0x20 della scritta: allineata a sinistra / a destra
SU_COMPAGNA = 12  # le scritte su due righe sono due elementi: la riga sopra sta 12 più in alto


def _incrocia(a, b):
    """Due rettangoli-linea (x0, x1, y0, y1) si toccano/incrociano?"""
    return a[0] < b[1] - 0.01 and b[0] < a[1] - 0.01 and a[2] < b[3] - 0.01 and b[2] < a[3] - 0.01


def _su_cerchio(r, c, raggio):
    px, py = min(max(c[0], r[0]), r[1]), min(max(c[1], r[2]), r[3])
    return (px - c[0]) ** 2 + (py - c[1]) ** 2 < raggio * raggio


def percorso(nome, lato, riga, tasto):
    """Pezzi (rettangoli) della linea dalla scritta al tasto: dritta se la riga è all'altezza del tasto, se no a L
    (orizzontale fino sopra/sotto il tasto, poi verticale). None se con i pezzi che ha non si può."""
    (tx, ty), rx, ry = tasto["p"], tasto["rx"], tasto["ry"]
    x0 = X_SX if lato == "s" else X_DX
    if abs(riga - ty) < 0.75:  # dritta: si ferma sul bordo del tasto
        xe = tx - rx if lato == "s" else tx + rx
        if (lato == "s" and xe <= x0 + 10) or (lato == "d" and xe >= x0 - 10):
            return None
        return [(min(x0, xe), max(x0, xe), riga, riga + 1)]
    if len(ORIGINALI[nome]["pezzi"]) < 2:
        return None
    if "n" not in tasto["lati"] and riga < ty or "s" not in tasto["lati"] and riga > ty:
        return None
    cx = tx
    h = (min(x0, cx), max(x0, cx) + 1, riga, riga + 1)
    ye = ty - ry if riga < ty else ty + ry
    v = (cx, cx + 1, min(riga, ye), max(riga + 1, ye))
    if v[3] - v[2] < 3:
        return None
    return [h, v]


def _scatola(lato, riga, larg, righe=1):
    """Dove sta la scritta (sopra la sua linea; le scritte su più righe salgono)."""
    x0 = X_SX if lato == "s" else X_DX - larg
    return (x0, x0 + larg, riga - ALTO_TESTO * righe - 2 * (righe - 1), riga - 1)


def _sul_controller(r, sagoma):
    """Quanta parte di un pezzo passa sopra il controller."""
    if r[3] - r[2] <= 1.01:  # orizzontale
        s = sagoma.get(int(r[2]))
        return max(0.0, min(r[1], s[1]) - max(r[0], s[0])) if s else 0.0
    return sum(1 for y in range(int(r[2]), int(r[3]) + 1) if (s := sagoma.get(y)) and s[0] <= r[0] <= s[1])


def costo_linea(nome, lato, riga, larg, tasti, sagoma, righe=1):
    """Costo di una linea da sola: lunghezza, curva, tasti sorvolati, tratti sopra il controller, scritta sopra il
    controller, linea che non esce da sotto la sua scritta, scritta spostata sull'altro lato. None se impossibile."""
    t = tasti[TASTO[nome]]
    p = percorso(nome, lato, riga, t)
    if p is None:
        return None, None
    c = sum((r[1] - r[0]) + (r[3] - r[2]) for r in p) * 0.5 + (30 if len(p) > 1 else 0)
    c += sum(_sul_controller(r, sagoma) for r in p) * 0.6
    sc = _scatola(lato, riga, larg, righe)
    if sc[2] < RIGHE[0] - ALTO_TESTO - 2:
        return None, None  # la scritta uscirebbe in alto
    fine_testo = sc[1] if lato == "s" else sc[0]
    angolo = p[0][1] if lato == "s" else p[0][0]  # dove finisce l'orizzontale
    sotto = (fine_testo + 8 - angolo) if lato == "s" else (angolo - fine_testo + 8)
    if sotto > 0:
        c += 40 * sotto  # la linea finirebbe sotto la scritta
    for n, altro in tasti.items():
        if n == TASTO[nome] or (n in ("croce", "dpad_su", "dpad_giu") and TASTO[nome].startswith("dpad")) or not altro.get("ingombro"):
            continue
        for r in p:
            if _su_cerchio(r, altro["p"], altro["ingombro"]):
                c += 900
    for y in range(int(sc[2]), int(sc[3]) + 1):  # scritta sopra il controller
        s = sagoma.get(y)
        if s and sc[0] < s[1] + 3 and s[0] - 3 < sc[1]:
            c += 12 * (min(sc[1], s[1] + 3) - max(sc[0], s[0] - 3)) ** 0.5
    if lato != ORIGINALI[nome]["lato"]:
        c += 20
    return c, p


def _conflitti(a, b):
    """Costo di due linee insieme: incroci tra pezzi, linea che passa sulla scritta dell'altra, scritte sovrapposte."""
    c = 0
    for r in a["p"]:
        for s in b["p"]:
            if _incrocia(r, s):
                c += 3000
    for r in a["p"]:
        if _incrocia(r, b["scatola"]):
            c += 3000
    for s in b["p"]:
        if _incrocia(s, a["scatola"]):
            c += 3000
    if a["lato"] == b["lato"]:  # due scritte dello stesso lato: almeno 5 di spazio tra l'una e l'altra
        sa, sb = a["scatola"], b["scatola"]
        if sa[2] < sb[3] + 5 + 1 and sb[2] < sa[3] + 5 + 1:
            c += 10000
    return c


def disponi(tasti, larghezze, sagoma, fascio=400, righe_testo=None):
    """Lato, riga e linea per ogni scritta. tasti: {nome: {"p": (x, y), "rx", "ry", "lati", "ingombro"}} in coordinate
    virtuali; larghezze: {linea: larghezza della scritta}; sagoma: {y intero: (xmin, xmax)} del controller.
    Ritorna ({linea: {"lato", "riga", "pezzi"}}, costo)."""
    opzioni = {}
    for nome in ORIGINALI:
        t = tasti[TASTO[nome]]
        cand = {round(t["p"][1])} | set(range(RIGHE[0], RIGHE[1] + 1, 3))
        ops = []
        for lato in ("s", "d"):
            for riga in sorted(cand):  # righe intere (le scritte si ritrovano per posizione esatta)
                nr = (righe_testo or {}).get(nome, 1)
                c, p = costo_linea(nome, lato, riga, larghezze.get(nome, 100), tasti, sagoma, nr)
                if p is not None:
                    ops.append({"nome": nome, "lato": lato, "riga": riga, "p": p, "c": c,
                                "scatola": _scatola(lato, riga, larghezze.get(nome, 100), nr)})
        ops.sort(key=lambda x: x["c"])
        opzioni[nome] = ops[:50]
    ordine = sorted(opzioni, key=lambda n: len(opzioni[n]))
    stati = [(0.0, [])]
    for nome in ordine:
        nuovi = []
        for c, scelti in stati:
            for op in opzioni[nome]:
                k = c + op["c"] + sum(_conflitti(op, s) for s in scelti)
                nuovi.append((k, scelti + [op]))
        nuovi.sort(key=lambda x: x[0])
        stati = nuovi[:fascio]
    c, scelti = stati[0]
    return {s["nome"]: {"riga": s["riga"], "pezzi": s["p"], "lato": s["lato"]} for s in scelti}, c


def disposizione(tasti, larghezze, sagoma, righe_testo=None):
    return disponi(tasti, larghezze, sagoma, fascio=160, righe_testo=righe_testo)[0]


def disposizione_originale():
    return {n: {"lato": v["lato"], "riga": v["riga"], "pezzi": list(v["pezzi"])} for n, v in ORIGINALI.items()}


# ---------------------------------------------------------------- applicare nel gioco
class Applicatore:
    """Tiene a mente dove stanno linee e scritte della schermata (finché il menu resta aperto) e le mette al posto
    deciso per il controller. applica() si può chiamare spesso: se è già tutto a posto non scrive niente.
    file_stato: dove ricordarsi l'ultima disposizione scritta (il pannello del gioco resta in memoria anche chiudendo
    e riaprendo il menu, quindi alla volta dopo le linee vanno cercate lì e non nella posizione originale)."""

    def __init__(self, file_stato=None):
        self.file = file_stato
        self.pezzi = None  # {(linea, i): [rettangolo attuale, [(indirizzo coppia, x lato), ...]]}
        self.scritte = None  # {linea: [indirizzo della x, ...]}
        self.compagne = {}  # {linea: [indirizzo della x, ...]} riga sopra delle scritte su due righe ("CAMERA" / "RE-CENTER")
        self.chiave = None  # disposizione già scritta (id del disegno o "originale")
        self.righe_testo = {}

    # -------------------------------------------------------- dove sono adesso
    def _salvata(self):
        import json
        try:
            d = json.loads(open(self.file, encoding="utf-8").read()) if self.file else None
            return d if d and "pezzi" in d and "scritte" in d else None
        except (OSError, ValueError):
            return None

    def _salva(self, scritte_pos):
        import json
        if not self.file:
            return
        try:
            d = {"pezzi": {f"{n}|{i}": list(r) for (n, i), (r, _) in self.pezzi.items()}, "scritte": scritte_pos}
            open(self.file, "w", encoding="utf-8").write(json.dumps(d))
        except OSError:
            pass

    def _cerca(self, dme):
        """Trova tutte le linee e le scritte: nella posizione originale del gioco o in quella che ho scritto io l'ultima
        volta. Tutte nella stessa (se no non tocco niente: non è la schermata che conosco)."""
        buf = leggi_zona(dme)
        sc = trova_scritte(buf)
        modi = [({(n, i): tuple(r) for n, v in ORIGINALI.items() for i, r in enumerate(v["pezzi"])},
                 {n: (v["lato"], v["riga"]) for n, v in ORIGINALI.items()})]
        s = self._salvata()
        if s:
            try:
                modi.append(({(n, int(i)): tuple(r) for k, r in s["pezzi"].items() for n, i in [k.split("|")]},
                             {n: tuple(v) for n, v in s["scritte"].items()}))
            except (ValueError, TypeError):
                pass
        for rett, pos in modi:
            if set(rett) != {(n, i) for n, v in ORIGINALI.items() for i in range(len(v["pezzi"]))} or set(pos) != set(ORIGINALI):
                continue
            lati = trova_lati(buf, list(set(rett.values())))
            pezzi, usati = {}, {}
            for k, r in rett.items():
                if len({round(x, 2) for _, x in lati[r]}) < 2:
                    break
                if any(usati.get(a, r) != r for a, _ in lati[r]):  # stessi vertici per due pezzi: non so di chi sono
                    break
                usati.update({a: r for a, _ in lati[r]})
                pezzi[k] = [r, lati[r]]
            else:
                scritte, compagne = {}, {}
                for n, (lato, riga) in pos.items():
                    x = float(X_SX if lato == "s" else X_DX)
                    ads = [a for a in sc.get((x, float(riga)), []) if testo_scritta(dme, a)]
                    if not ads:
                        break
                    scritte[n] = ads
                    compagne[n] = [a for a in sc.get((x, float(riga) - SU_COMPAGNA), []) if testo_scritta(dme, a)]
                else:
                    self.pezzi, self.scritte, self.compagne, self.chiave = pezzi, scritte, compagne, None
                    return True
        return False

    def _ancora_li(self, dme):
        """Le linee che conosco sono ancora dove le ho messe (stesso pannello)?"""
        try:
            for r, lati in self.pezzi.values():
                for a, xs in lati:
                    y = dme.read_float(a + 4)
                    if abs(dme.read_float(a) - xs) > 0.01 or not (abs(y - r[2]) < 0.01 or abs(y - r[3]) < 0.01):
                        return False
            return True
        except Exception:  # noqa: BLE001
            return False

    def larghezze(self, dme):
        """Larghezza (riga più lunga) e numero di righe delle scritte (di tutte le configurazioni A/B/C)."""
        out, self.righe_testo = {}, {}
        for nome, ads in self.scritte.items():
            testi = [testo_scritta(dme, a) or "" for a in ads + self.compagne.get(nome, [])]
            out[nome] = max(len(r) for t in testi for r in t.split("\n")) * LETTERA + 4
            self.righe_testo[nome] = max(t.count("\n") + 1 for t in testi) + (1 if self.compagne.get(nome) else 0)
        return out

    # -------------------------------------------------------- scrivere
    def trova(self, dme):
        """Linee e scritte trovate (e ancora lì)? Veloce se le conosco già."""
        if self.pezzi is None or not self._ancora_li(dme):
            self.pezzi = None
            return self._cerca(dme)
        return True

    def applica(self, dme, chiave, tasti=None, sagoma=None):
        """Tutto in una volta (per le prove): trova, calcola, scrive. tasti None = come l'originale del gioco."""
        if not self.trova(dme):
            return False
        if self.chiave != chiave:
            disp = disposizione_originale() if tasti is None else \
                disposizione(tasti, self.larghezze(dme), sagoma or {}, self.righe_testo)
            self.scrivi(dme, chiave, disp)
        return True

    def scrivi(self, dme, chiave, disp):
        """Sposta linee e scritte dove dice la disposizione (va chiamata dopo trova())."""
        pos = {}
        for nome, d in disp.items():
            nuovi = [tuple(r) for r in d["pezzi"]]
            while len(nuovi) < len(ORIGINALI[nome]["pezzi"]):
                # linea dritta: il pezzo in più diventa un quadratino nascosto in fondo alla linea (rettangolo diverso
                # dagli altri, così alla volta dopo si ritrova)
                h = nuovi[0]
                x = h[1] - 3 if d["lato"] == "s" else h[0] + 2  # senza lati in comune con la linea (si confonderebbero)
                nuovi.append((x, x + 1, h[2], h[3]))
            for i, n in enumerate(nuovi):
                vecchio, lati = self.pezzi[(nome, i)]
                if vecchio != n:
                    sposta_rettangolo(dme, lati, vecchio, n)
                    self.pezzi[(nome, i)] = [n, [(a, n[0] if abs(xs - vecchio[0]) < abs(xs - vecchio[1]) else n[1]) for a, xs in lati]]
            x = float(X_SX if d["lato"] == "s" else X_DX)
            for ads, dy in ((self.scritte[nome], 0), (self.compagne.get(nome, []), -SU_COMPAGNA)):
                for a in ads:
                    dme.write_word(a + 0x20, ALLINEA[d["lato"]])
                    dme.write_float(a, x)
                    dme.write_float(a + 4, float(d["riga"]) + dy)
            pos[nome] = [d["lato"], d["riga"]]
        self.chiave = chiave
        self._salva(pos)
        return True


# ---------------------------------------------------------------- anteprima (app e generatore)
# Le scritte come le scrive il gioco (italiano dal gioco; le altre lingue sono approssimate: servono solo all'anteprima,
# nel gioco la disposizione usa le scritte vere lette dalla memoria).
SCRITTE = {
    "it": {"scatto": "SCATTO/MODIFICATORE", "muovi": "MUOVI", "riflessi": "RIFLESSI DI RAGNO", "blocca": "BLOCCA VISUALE",
           "start": "START/PAUSA", "attacco": "ATTACCO/AZIONE", "ragnatela": "RAGNATELA", "oscilla": "OSCILLA",
           "centra": "CENTRA", "schiva": "SCHIVA/AFFERRA", "salto": "SALTO", "guarda": "GUARDA"},
    "en": {"scatto": "SPRINT/MODIFIER", "muovi": "MOVE", "riflessi": "SPIDER REFLEXES", "blocca": "LOCK CAMERA",
           "start": "START/PAUSE", "attacco": "ATTACK/ACTION", "ragnatela": "WEB", "oscilla": "SWING",
           "centra": "RECENTER", "schiva": "DODGE/GRAB", "salto": "JUMP", "guarda": "LOOK"},
    "de": {"scatto": "SPRINT/MODIFIKATOR", "muovi": "BEWEGEN", "riflessi": "SPINNENREFLEXE", "blocca": "KAMERA SPERREN",
           "start": "START/PAUSE", "attacco": "ANGRIFF/AKTION", "ragnatela": "NETZ", "oscilla": "SCHWINGEN",
           "centra": "ZENTRIEREN", "schiva": "AUSWEICHEN/GREIFEN", "salto": "SPRINGEN", "guarda": "UMSEHEN"},
    "fr": {"scatto": "SPRINT/MODIFICATEUR", "muovi": "DÉPLACEMENT", "riflessi": "RÉFLEXES ARACHNÉENS",
           "blocca": "BLOQUER CAMÉRA", "start": "START/PAUSE", "attacco": "ATTAQUE/ACTION", "ragnatela": "TOILE",
           "oscilla": "BALANCER", "centra": "CENTRER", "schiva": "ESQUIVE/SAISIE", "salto": "SAUT", "guarda": "REGARDER"},
    "es": {"scatto": "SPRINT/MODIFICADOR", "muovi": "MOVER", "riflessi": "REFLEJOS ARÁCNIDOS", "blocca": "FIJAR CÁMARA",
           "start": "START/PAUSA", "attacco": "ATAQUE/ACCIÓN", "ragnatela": "TELARAÑA", "oscilla": "BALANCEO",
           "centra": "CENTRAR", "schiva": "ESQUIVAR/AGARRAR", "salto": "SALTAR", "guarda": "MIRAR"},
}


def larghezze_testi(scritte):
    return {n: len(t) * LETTERA + 4 for n, t in scritte.items()}


def anteprima(texture, dati, scritte, k=2.0, fondo=(26, 34, 56, 255)):
    """Come appare Opzioni > Controller nel gioco: pagina scura, texture nel suo riquadro (stirata come nel gioco,
    widescreen), scritte e linee della disposizione calcolata. texture = immagine PIL RGBA. -> (immagine, costo)"""
    from PIL import Image, ImageDraw, ImageFont
    kx = k * 4 / 3
    x0, y0 = virt((0, 0))
    x1, y1 = virt((512, 512))
    # ritaglio della pagina utile (dalle scritte più alte a quelle più basse, con margine)
    W, H = int(640 * kx), int(448 * k)
    sf = Image.new("RGBA", (W, H), fondo)
    sf.alpha_composite(texture.convert("RGBA").resize((int((x1 - x0) * kx), int((y1 - y0) * k)), Image.LANCZOS),
                       (int(x0 * kx), int(y0 * k)))
    d = ImageDraw.Draw(sf)
    sag = {int(a): b for a, b in dati.get("sagoma", {}).items()}
    disp, costo = disponi(dati["tasti"], larghezze_testi(scritte), sag)
    font = None
    for nome in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(nome, int(12 * k))
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    for n, v in disp.items():
        for r in v["pezzi"]:
            d.rectangle((r[0] * kx, r[2] * k, r[1] * kx, r[3] * k), fill=(230, 208, 63, 255))
        t = scritte[n]
        tw = d.textlength(t, font=font)
        tx = X_SX * kx if v["lato"] == "s" else X_DX * kx - tw
        d.text((tx, (v["riga"] - ALTO_TESTO) * k), t, font=font, fill=(205, 205, 205, 255))
    righe = [v["riga"] for v in disp.values()]
    alto = int((min(min(righe) - ALTO_TESTO - 12, y0 + 4)) * k)
    basso = int((max(max(righe) + 12, max(int(y) for y in sag) + 6 if sag else 0)) * k)
    return sf.crop((int(55 * kx), max(0, alto), int(585 * kx), min(H, basso))), costo
