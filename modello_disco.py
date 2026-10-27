"""MODELLO 3D DI SPIDEY DAL DISCO DELL'UTENTE (2026-10-16, per Patreon: l'app non contiene niente del gioco).

Il modello sta in packs/amalga_gc.pak (stesso posto e stessi byte in USA, UK, ITA, DE, FR) come file "GCNM" a BASE:
  - tre parti (corpo, maschera, lenti), ognuna con: vertici di riposo (posizione + normale, s16 o float, in una posa a T),
    comandi di skinning (u16), pesi (u8), lista dei triangoli GX (strisce 0x98, 4 indici u16 per vertice: posizione,
    normale, colore/uv1, uv) e coordinate uv (s16 con 9 o 15 bit di frazione);
  - lo skinning lo fa il gioco con l'interprete a 0x802FADB0 (ITA = USA): comandi 1/2/3 caricano le matrici A/B dell'osso,
    4/5 trasformano n vertici con A/B, 6/0xE mescolano A e B coi pesi, 7/8/9 sommano un'altra influenza a un'uscita già
    salvata (per indice), 0xB/0xC/0xD/0xF muovono i dati a blocchi di 32 byte nella cache bloccata (3 buffer): le uscite
    finiscono dove le mette il salvataggio a blocchi, non in fila -> qui l'emulazione è fedele byte per byte (verificata
    contro la memoria del gioco: errore 0,06 mm).
Nell'app c'è solo la POSA (contenuti/modello_pose.json): per ogni osso una matrice 4x3 che porta la posa a T nella posa
dell'anteprima (ricavata una volta da crea_pose_modello.py). Posizioni, uv e triangoli vengono dal disco."""
import hashlib
import json
import struct
from pathlib import Path

PAK = ("packs", "amalga_gc.pak")
BASE = 0x8148740          # file GCNM del corpo di Spidey dentro amalga_gc.pak
LUNGO = 0xC400            # quanto ne serve (tutte e tre le parti)
MD5 = "7f9600acbbaba2240ac1bfb094852c61"  # di quei LUNGO byte (uguale nelle 5 versioni)
# parti nell'ordine dell'anteprima: struttura di disegno (render) e bit di frazione delle uv
PARTI = [(0xBEB8, 9), (0x17D8, 9), (0xC338, 15)]
NOSSA = 60
ATTR_UV = 0x0D


def _gqr(v):
    return (v >> 24) & 0x3F, (v >> 16) & 7


def _letture(t, s):
    """(formato struct, grandezza) per un tipo GQR."""
    return {0: ("f", 4), 4: ("B", 1), 5: ("H", 2), 6: ("b", 1), 7: ("h", 2)}[t]


def parti(g):
    """g = bytes del file GCNM (da BASE). Per ogni parte: dati per lo skinning e per i triangoli."""
    out = []
    for rs, uvbit in PARTI:
        u = lambda o: struct.unpack_from(">I", g, o)[0]  # noqa: E731
        info = u(rs + 8)
        vert, pesi, cmd, g7, g6 = u(rs + 12), u(rs + 16), u(rs + 20), u(rs + 24), u(rs + 28)
        vd = u(rs + 0x40)
        dl, dl_lungo = u(vd + 0x10), u(vd + 0x14)
        attr = []
        o = vd + 0x20
        while 9 <= g[o] <= 0x15:
            attr.append((g[o], u(o + 4)))
            o += 8
        uv = dict(attr).get(ATTR_UV)
        out.append(dict(vert=vert, pesi=pesi, cmd=cmd, g7=g7, g6=g6, nout=info & 0xFFFF, dl=dl, dl_lungo=dl_lungo,
                        nind=len(attr), uv=uv, uvbit=uvbit, k_uv=[a for a, _ in attr].index(ATTR_UV)))
    return out


def strisce(g, p):
    """Vertici dei triangoli in ordine di disegno: (indice posizione, indice uv) e i triangoli (come le strisce GX)."""
    # indici da 2 byte (parte grande, più di 255 punti) o da 1 (maschera e lenti): vale quello con cui la lista finisce
    # giusta (dopo l'ultima striscia solo zeri fino alla fine)
    fine = p["dl"] + p["dl_lungo"]
    for dim, fmt in ((2, "H"), (1, "B")):
        o = p["dl"]
        vv, tri = [], []
        while o < fine and g[o] == 0x98:
            n = struct.unpack_from(">H", g, o + 1)[0]
            o += 3
            g0 = len(vv)
            for k in range(n):
                ix = struct.unpack_from(f">{p['nind']}{fmt}", g, o)
                o += dim * p["nind"]
                vv.append((ix[0], ix[p["k_uv"]]))
            for k in range(n - 2):
                a = g0 + k
                tri.append((a, a + 1, a + 2) if k % 2 == 0 else (a + 1, a, a + 2))
        if o <= fine and not any(g[o:fine]):
            return vv, tri
    raise ValueError("lista dei triangoli non riconosciuta")


def skinning(g, p, mats=None, simbolico=False):
    """Emulazione fedele dell'interprete del gioco. mats: NOSSA matrici 4x3 (righe: x, y, z, traslazione; vettore riga).
    Ritorna le posizioni di uscita per indice. simbolico=True: per ogni uscita e coordinata il vettore dei coefficienti
    (lungo NOSSA*4) delle colonne delle matrici (per adattare una posa)."""
    s7, t7 = _gqr(p["g7"])
    s6, t6 = _gqr(p["g6"])
    f7, n7 = _letture(t7, s7)
    f6, n6 = _letture(t6, s6)
    rec = 6 * n7                      # posizione + normale
    k7, k6 = 1.0 / (1 << s7), 1.0 / (1 << s6)
    K = NOSSA * 4
    raw = [bytearray(0x4000) for _ in range(3)]
    buf = [{} for _ in range(3)]      # posizione nel buffer (byte) -> uscita
    main = {}
    ia = ib = 0
    r21, pc, pw, r22, r23, r24 = p["vert"], p["cmd"], p["pesi"], 0, 0, 0
    p29 = p31 = 0

    def trasforma(v, o, w):
        if simbolico:
            x = (v[0] * w, v[1] * w, v[2] * w, w)
            r = [dict() for _ in range(3)]
            for j in range(3):
                for i in range(4):
                    r[j][o * 4 + i] = x[i]
            return r
        m = mats[o]
        return [w * (v[0] * m[0][j] + v[1] * m[1][j] + v[2] * m[2][j] + m[3][j]) for j in range(3)]

    def somma(a, b):
        if simbolico:
            out = [dict(x) for x in a]
            for j in range(3):
                for k, c in b[j].items():
                    out[j][k] = out[j].get(k, 0.0) + c
            return out
        return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
    vuoto = ([{}, {}, {}] if simbolico else [0.0, 0.0, 0.0])

    def vin():
        nonlocal p29
        v = [x * k7 for x in struct.unpack_from(">3" + f7, raw[r24], p29)]
        p29 += rec
        return v

    def pesi2():
        nonlocal pw
        w = [x * k6 for x in struct.unpack_from(">2" + f6, g, pw)]
        return w
    while True:
        c = struct.unpack_from(">H", g, pc)[0]
        pc += 2
        if c == 0xA:
            break
        if c == 0xD:
            r24 = (r24 + 1) % 3
            p29 = p31 = 0
            continue
        if c == 0xF:
            pc += 2
            continue
        arg = struct.unpack_from(">H", g, pc)[0]
        pc += 2
        if c == 0xB:
            n = arg * 32
            raw[r23][:n] = g[r21: r21 + n]
            r21 += n
            r23 = (r23 + 1) % 3
        elif c == 0xC:
            n = arg * 32
            for pos, val in buf[r24].items():
                if pos + rec <= n and (r22 + pos) % rec == 0:
                    main[(r22 + pos) // rec] = val
            r22 += n
        elif c in (2, 3):
            if c == 2:
                ia = arg & 0xFF
            else:
                ib = arg & 0xFF
        elif c in (4, 5, 6, 0xE, 7, 8, 9):
            for _ in range(arg):
                if c in (4, 5):
                    buf[r24][p31] = trasforma(vin(), ia if c == 4 else ib, 1.0)
                    p31 += rec
                elif c in (6, 0xE):
                    w = pesi2()
                    pw += 2 * n6
                    v = vin()
                    buf[r24][p31] = somma(trasforma(v, ia, w[0]), trasforma(v, ib, w[1]))
                    p31 += rec
                else:
                    w = pesi2()
                    idx = struct.unpack_from(">H", g, pw + 2 * n6)[0]
                    pw += 2 * n6 + 2
                    v = vin()
                    prima = main.get(idx, vuoto)
                    if c == 7:
                        main[idx] = somma(prima, trasforma(v, ia, w[1]))
                    elif c == 8:
                        main[idx] = somma(prima, trasforma(v, ib, w[1]))
                    else:
                        main[idx] = somma(somma(prima, trasforma(v, ia, w[0])), trasforma(v, ib, w[1]))
        else:
            ia, ib = (arg >> 8) & 0xFF, arg & 0xFF
    return main


def leggi_gcnm(pak):
    """Bytes del modello dal file amalga_gc.pak; None se non è quello giusto."""
    with open(pak, "rb") as f:
        f.seek(BASE)
        g = f.read(LUNGO)
    return g if len(g) == LUNGO and hashlib.md5(g).hexdigest() == MD5 else None


def modello(g, mats):
    """Modello per l'anteprima (stesso formato di prima: {"parti": [{tex, pos, uv, idx}]}) nella posa mats (le stesse
    NOSSA matrici per tutte le parti)."""
    out = []
    for p in parti(g):
        pos = skinning(g, p, mats)
        vv, tri = strisce(g, p)
        bit = 1 << p["uvbit"]
        P, U = [], []
        for ip, iu in vv:
            P += [round(x, 5) for x in pos.get(ip, (0.0, 0.0, 0.0))]
            u, v = struct.unpack_from(">2h", g, p["uv"] + 4 * iu)
            U += [round(u / bit, 5), round(v / bit, 5)]
        out.append({"tex": "corpo", "pos": P, "uv": U, "idx": [i for t in tri for i in t]})
    return {"parti": out}


def crea(pak, cartella, file_pose):
    """Scrive spidey_modello.json e spidey_modello_idle.json in cartella. True se fatto."""
    g = leggi_gcnm(pak)
    if g is None:
        return False
    pose = json.loads(Path(file_pose).read_text(encoding="utf-8"))
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    for nome, chiave in (("spidey_modello.json", "gioco"), ("spidey_modello_idle.json", "idle")):
        tmp = cartella / (nome + ".tmp")
        tmp.write_text(json.dumps(modello(g, pose[chiave]), separators=(",", ":")), encoding="utf-8")
        tmp.replace(cartella / nome)
    return True
