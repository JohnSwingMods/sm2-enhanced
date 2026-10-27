"""Stati salvati coi codici Gecko VECCHI: li aggiorno nel FILE, prima che Dolphin li carichi.

Uno stato salvato di Dolphin è la RAM del gioco in quel momento, compresi i codici Gecko di allora (zona
0x80001800-0x80003000: gestore dei codici + elenco) e gli agganci C2 già scritti nel codice del gioco (salti nella
zona). Partendo da uno stato fatto prima di un aggiornamento giravano i codici vecchi (John: menu di pausa rovinato
dall'HUD 16:9 vecchio). Riscriverli in memoria dopo il caricamento NON si può: il JIT di Dolphin tiene tradotto il
codice vecchio (pannelli del menu spariti, gioco piantato). Nel file invece sì: caricando, Dolphin riparte da zero.

Formato del file (Dolphin 2409+, provato su 2609): intestazione di 0x40 byte (ID del gioco, cookie 0xBAADBABE + formato,
"Dolphin xxxx", ..., +0x34 grandezza decompressa u64, +0x3C grandezza compressa u32) + un blocco LZ4 (blocco semplice,
non "frame"). La RAM (24 MB) sta dentro i dati decompressi: la trovo dall'intestazione del disco copiata a 0x80000000
(ID del gioco e, a +0x1C, il numero magico dei dischi GameCube 0xC2339F3D).

Cosa riscrivo: la zona dei codici (presa dal gioco appena partito, cioè i codici dell'INI di adesso) e, nei punti
agganciati (dai codici nuovi o da quelli vecchi), la parola che c'è nel gioco appena partito: il salto ai codici
nuovi, oppure l'istruzione originale del gioco se il codice nuovo lì non si aggancia più."""
import struct

ZONA, LUNGA = 0x80001800, 0x1800
RAM_LUNGA = 0x1800000
MAGICO_GC = bytes.fromhex("c2339f3d")


def _leggi(percorso):
    b = open(percorso, "rb").read()
    if len(b) < 0x40:
        return None
    nonc = struct.unpack("<Q", b[0x34:0x3C])[0]
    comp = struct.unpack("<I", b[0x3C:0x40])[0]
    if comp != len(b) - 0x40 or not 0 < nonc < 0x20000000:
        return None  # formato diverso (stato non compresso o di un'altra versione di Dolphin): non lo tocco
    import lz4.block
    try:
        dati = lz4.block.decompress(b[0x40:], uncompressed_size=nonc)
    except Exception:  # noqa: BLE001
        return None
    return b[:0x40], bytearray(dati)


def _ram(dati, gid):
    i = -1
    while True:
        i = dati.find(gid.encode("ascii"), i + 1)
        if i < 0 or i + RAM_LUNGA > len(dati):
            return None
        if dati[i + 0x1C:i + 0x20] == MAGICO_GC:
            return i


def ganci(zona, parola):
    """Punti del gioco agganciati dai codici C2 della zona: righe C2/C3 il cui punto contiene un salto dentro la zona
    (parola(a) = la parola a quell'indirizzo, dalla RAM viva o da quella dello stato)."""
    w = struct.unpack(f">{len(zona) // 4}I", zona)
    out = set()
    for i in range(len(w) - 1):
        if (w[i] >> 24) not in (0xC2, 0xC3) or not 0 < w[i + 1] < 0x200:
            continue
        a = 0x80000000 | (w[i] & 0x01FFFFFC)
        if not 0x80003100 <= a < 0x80400000:
            continue
        x = parola(a)
        if x is not None and x >> 26 == 18:
            d = x & 0x03FFFFFC
            d = d - 0x04000000 if d & 0x02000000 else d
            if ZONA <= a + d < ZONA + LUNGA:
                out.add(a)
    return out


def punti_conosciuti(gid):
    """Dove si agganciano i nostri codici Gecko (camera: inizio e fine dell'aggiornamento, vista; HUD 16:9: pezzi,
    scritte, minimappa): se nel gioco appena partito lì non c'è un aggancio, c'è l'istruzione originale."""
    import cam_ps4
    import hud_wide
    v, h = cam_ps4.VERSIONI.get(gid), hud_wide.VERSIONI.get(gid)
    if not v or not h:
        return set()
    punti = {v["inizio"], v["fine"], cam_ps4.VISTA, h["quad"], h["testo"], h["mappa"]}
    # + ogni aggancio C2 dei codici Gecko del database (tuffo, muri, web zip, momentum, R3 senza lock...): prima mancavano
    try:
        import app_core
        for c in app_core.carica_codici_db():
            for r in (c.get("versioni") or {}).get(gid) or []:
                if r[:2].upper() == "C2":
                    punti.add(0x80000000 | (int(r[2:8], 16) & 0x1FFFFFF))
    except Exception:  # noqa: BLE001
        pass
    return punti


def foto_codici(dme, conosciuti):
    """Dal gioco appena partito: la zona dei codici e le parole nei punti agganciati adesso + in quelli conosciuti
    (dove si agganciano i nostri codici, anche quelli che adesso sono spenti: lì c'è l'istruzione originale)."""
    zona = dme.read_bytes(ZONA, LUNGA)

    def parola(a):
        try:
            return struct.unpack(">I", dme.read_bytes(a, 4))[0]
        except Exception:  # noqa: BLE001
            return None
    punti = ganci(zona, parola) | set(conosciuti)
    parole = {a: parola(a) for a in punti}
    return {"zona": zona, "parole": {a: w for a, w in parole.items() if w is not None}}


def stato_vecchio(percorso, gid, foto):
    """True se lo stato ha codici diversi da quelli della foto, False se uguali, None se non lo so leggere."""
    letto = _leggi(percorso)
    if not letto:
        return None
    _, dati = letto
    r = _ram(dati, gid)
    if r is None:
        return None
    return bytes(dati[r + ZONA - 0x80000000:r + ZONA - 0x80000000 + LUNGA]) != foto["zona"]


def aggiorna(percorso, gid, foto):
    """Riscrive nel file la zona dei codici e le parole nei punti agganciati. Ritorna "uguale" (niente da fare),
    "aggiornato", oppure il motivo per cui non l'ho toccato ("formato", "ram", "ganci_ignoti")."""
    letto = _leggi(percorso)
    if not letto:
        return "formato"
    testa, dati = letto
    r = _ram(dati, gid)
    if r is None:
        return "ram"
    off = r - 0x80000000
    vecchia = bytes(dati[off + ZONA:off + ZONA + LUNGA])
    if vecchia == foto["zona"]:
        return "uguale"

    def parola(a):
        return struct.unpack(">I", dati[off + a:off + a + 4])[0]
    ignoti = ganci(vecchia, parola) - set(foto["parole"])
    if ignoti:  # un codice vecchio si agganciava dove non so cosa rimettere: lo stato resta com'è
        return "ganci_ignoti"
    dati[off + ZONA:off + ZONA + LUNGA] = foto["zona"]
    for a, w in foto["parole"].items():
        dati[off + a:off + a + 4] = struct.pack(">I", w)
    import lz4.block
    comp = lz4.block.compress(bytes(dati), store_size=False)
    testa = bytearray(testa)
    testa[0x3C:0x40] = struct.pack("<I", len(comp))
    import os
    import tempfile
    st = os.stat(percorso)
    d = os.path.dirname(os.path.abspath(percorso))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        f.write(bytes(testa) + comp)
    os.utime(tmp, (st.st_atime, st.st_mtime))  # stessa data: foto e dati dell'app restano validi, ordine invariato
    os.replace(tmp, percorso)
    return "aggiornato"
