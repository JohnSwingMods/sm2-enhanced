"""Mini assemblatore PowerPC (Gekko) per i codici Gecko: testo -> parole a 32 bit, con etichette per i salti.

Sintassi: un'istruzione per riga, commenti con ';' o '#', etichette 'nome:'. Registri r0-r31 / f0-f31.
Esempio:
    lis r12, 0x817F
    lfs f1, 0x10(r12)
    fcmpu f1, f2
    blt fine
    ...
  fine:
Istruzioni supportate: vedi ISTR. 'chiama ADDR' = lis/ori r12 + mtctr + bctrl (salto assoluto con ritorno)."""
import re
import struct


def _r(x):
    x = x.strip().lower()
    if x.startswith(("r", "f")) and x[1:].isdigit():
        return int(x[1:])
    raise ValueError(f"registro? {x}")


def _n(x):
    x = x.strip().lower()
    neg = x.startswith("-")
    v = int(x.lstrip("-"), 0)
    return -v if neg else v


def _mem(x):  # "0x10(r3)" -> (0x10, 3)
    m = re.fullmatch(r"\s*(-?[0-9a-fx]+)\s*\(\s*(r\d+)\s*\)\s*", x.lower())
    if not m:
        raise ValueError(f"memoria? {x}")
    return _n(m.group(1)) & 0xFFFF, _r(m.group(2))


def D(op, d, a, imm): return op << 26 | d << 21 | a << 16 | (imm & 0xFFFF)
def X(op, d, a, b, xo, rc=0): return op << 26 | d << 21 | a << 16 | b << 11 | xo << 1 | rc
def A(xo, d, a, b, c): return 59 << 26 | d << 21 | a << 16 | b << 11 | c << 6 | xo << 1
def A63(xo, d, a, b, c): return 63 << 26 | d << 21 | a << 16 | b << 11 | c << 6 | xo << 1


CONDIZIONI = {"beq": (12, 2), "bne": (4, 2), "blt": (12, 0), "bge": (4, 0), "bgt": (12, 1), "ble": (4, 1)}


def assembla(testo, base=0, etichette=False):
    """Ritorna la lista di parole (con etichette=True: (parole, {etichetta: indirizzo})). base = indirizzo della prima
    istruzione (serve per 'b' verso indirizzi fissi e per gli indirizzi delle etichette)."""
    righe = []
    for r in testo.splitlines():
        r = re.split(r"[;#]", r, 1)[0].strip()
        if not r:
            continue
        while ":" in r and re.match(r"^\w+:", r):
            nome, r = r.split(":", 1)
            righe.append(("etichetta", nome.strip()))
            r = r.strip()
        if r:
            righe.append(("istr", r))
    # prima passata: posizioni (le pseudo-istruzioni possono valere più parole)
    pos, etich = 0, {}
    for t, r in righe:
        if t == "etichetta":
            etich[r] = pos
        else:
            pos += 4 * _lunghezza(r)
    out = []
    for t, r in righe:
        if t == "istr":
            out += _codifica(r, len(out) * 4, etich)
    if etichette:
        return out, {k: base + v for k, v in etich.items()}
    return out


def _lunghezza(r):
    op = r.split()[0].lower()
    return {"chiama": 4, "li32": 2, "lf": 3}.get(op, 1)


def _codifica(r, qui, etich):
    op, _, resto = r.partition(" ")
    op = op.lower()
    a = [x.strip() for x in resto.split(",")] if resto.strip() else []

    def salto(dest):
        return (etich[dest] if dest in etich else _n(dest)) - qui

    if op == ".word": return [_n(a[0]) & 0xFFFFFFFF]  # parola grezza (es. l'istruzione originale di un C2)
    if op == ".float": return [f32(float(a[0]))]  # costante dentro il codice (si legge con bl + mflr)
    if op == "blrl": return [0x4E800021]
    if op == "li": return [D(14, _r(a[0]), 0, _n(a[1]))]
    if op == "lis": return [D(15, _r(a[0]), 0, _n(a[1]))]
    if op == "addi": return [D(14, _r(a[0]), _r(a[1]), _n(a[2]))]
    if op == "addis": return [D(15, _r(a[0]), _r(a[1]), _n(a[2]))]
    if op == "ori": return [D(24, _r(a[1]), _r(a[0]), _n(a[2]))]
    if op == "li32":  # li32 rX, valore a 32 bit
        v = _n(a[1]) & 0xFFFFFFFF
        return [D(15, _r(a[0]), 0, v >> 16), D(24, _r(a[0]), _r(a[0]), v & 0xFFFF)]
    if op == "lf":  # lf fX, 1.5, rTMP  -> carica una costante float usando rTMP e la zona 817F00F0
        v = struct.unpack(">I", struct.pack(">f", float(a[1])))[0]
        t = _r(a[2])
        raise NotImplementedError("usa costanti in memoria")
    if op in ("lwz", "stw", "lbz", "stb", "lfs", "stfs", "lhz", "sth", "stwu", "lfd", "stfd"):
        opc = {"lwz": 32, "stw": 36, "lbz": 34, "stb": 38, "lfs": 48, "stfs": 52, "lhz": 40, "sth": 44, "stwu": 37,
               "lfd": 50, "stfd": 54}[op]
        off, ra = _mem(a[1])
        return [D(opc, _r(a[0]), ra, off)]
    if op == "andi.": return [D(28, _r(a[1]), _r(a[0]), _n(a[2]))]
    if op == "xori": return [D(26, _r(a[1]), _r(a[0]), _n(a[2]))]
    if op == "extsb": return [X(31, _r(a[1]), _r(a[0]), 0, 954)]
    if op == "xoris": return [D(27, _r(a[1]), _r(a[0]), _n(a[2]))]
    if op == "fsub": return [A63(20, _r(a[0]), _r(a[1]), _r(a[2]), 0)]
    if op == "fadd": return [A63(21, _r(a[0]), _r(a[1]), _r(a[2]), 0)]
    if op == "mr": return [X(31, _r(a[1]), _r(a[0]), _r(a[1]), 444)]
    if op == "add": return [X(31, _r(a[0]), _r(a[1]), _r(a[2]), 266)]
    if op == "subf": return [X(31, _r(a[0]), _r(a[1]), _r(a[2]), 40)]  # rD = rB - rA
    if op == "cmpwi": return [D(11, 0, _r(a[0]), _n(a[1]))]
    if op == "cmplwi": return [D(10, 0, _r(a[0]), _n(a[1]))]
    if op == "cmplw": return [X(31, 0, _r(a[0]), _r(a[1]), 32)]
    if op == "cmpw": return [X(31, 0, _r(a[0]), _r(a[1]), 0)]
    if op == "fcmpu": return [X(63, 0, _r(a[0]), _r(a[1]), 0)]
    if op == "fadds": return [A(21, _r(a[0]), _r(a[1]), _r(a[2]), 0)]
    if op == "fsubs": return [A(20, _r(a[0]), _r(a[1]), _r(a[2]), 0)]
    if op == "fmuls": return [A(25, _r(a[0]), _r(a[1]), 0, _r(a[2]))]
    if op == "fdivs": return [A(18, _r(a[0]), _r(a[1]), _r(a[2]), 0)]
    if op == "fmadds": return [A(29, _r(a[0]), _r(a[1]), _r(a[3]), _r(a[2]))]   # d = a*c + b  (fmadds d,a,c,b)
    if op == "fmsubs": return [A(28, _r(a[0]), _r(a[1]), _r(a[3]), _r(a[2]))]   # d = a*c - b
    if op == "fnmsubs": return [A(30, _r(a[0]), _r(a[1]), _r(a[3]), _r(a[2]))]  # d = -(a*c - b)
    if op == "fres": return [A(24, _r(a[0]), 0, _r(a[1]), 0)]
    if op == "frsqrte": return [A63(26, _r(a[0]), 0, _r(a[1]), 0)]
    if op == "fsel": return [A63(23, _r(a[0]), _r(a[1]), _r(a[3]), _r(a[2]))]  # d = a>=0 ? c : b  (fsel d,a,c,b)
    if op == "fmr": return [X(63, _r(a[0]), 0, _r(a[1]), 72)]
    if op == "fneg": return [X(63, _r(a[0]), 0, _r(a[1]), 40)]
    if op == "fabs": return [X(63, _r(a[0]), 0, _r(a[1]), 264)]
    if op == "frsp": return [X(63, _r(a[0]), 0, _r(a[1]), 12)]
    if op == "mflr": return [31 << 26 | _r(a[0]) << 21 | 0x100 << 11 | 339 << 1]
    if op == "mtlr": return [31 << 26 | _r(a[0]) << 21 | 0x100 << 11 | 467 << 1]
    if op == "mtctr": return [31 << 26 | _r(a[0]) << 21 | 0x120 << 11 | 467 << 1]
    if op == "bctrl": return [0x4E800421]
    if op == "bctr": return [0x4E800420]
    if op == "blr": return [0x4E800020]
    if op == "nop": return [0x60000000]
    if op == "b": return [18 << 26 | (salto(a[0]) & 0x3FFFFFC)]
    if op == "bl": return [18 << 26 | (salto(a[0]) & 0x3FFFFFC) | 1]
    if op == "bdnz": return [16 << 26 | 16 << 21 | (salto(a[0]) & 0xFFFC)]
    if op in CONDIZIONI:
        bo, bi = CONDIZIONI[op]
        return [16 << 26 | bo << 21 | bi << 16 | (salto(a[0]) & 0xFFFC)]
    if op == "chiama":  # salto assoluto con ritorno (usa r12)
        v = _n(a[0]) & 0xFFFFFFFF
        return [D(15, 12, 0, v >> 16), D(24, 12, 12, v & 0xFFFF), 31 << 26 | 12 << 21 | 0x120 << 11 | 467 << 1, 0x4E800421]
    raise ValueError(f"istruzione non supportata: {r}")


def c2(indirizzo, parole):
    """Righe Gecko C2 (inserisci codice): alla fine torna all'istruzione dopo 'indirizzo'."""
    parole = list(parole) + ([0x00000000] if len(parole) % 2 else [0x60000000, 0x00000000])
    righe = [f"C2{indirizzo & 0x1FFFFFF:06X} {len(parole) // 2:08X}"]
    righe += [f"{parole[i]:08X} {parole[i + 1]:08X}" for i in range(0, len(parole), 2)]
    return righe


def c0(parole):
    """Righe Gecko C0 (esegui codice a ogni giro dei codici): deve finire con blr (lo aggiungo io). Usare solo r0, r3,
    r5, r9-r12: il gestore di Dolphin (Sys/codehandler.bin) dopo il blrl fa add r15, r4, r15 (r4 = lunghezza del
    codice) e tiene i suoi stati in r6-r8 e r15-r19."""
    parole = list(parole) + [0x4E800020]
    if len(parole) % 2:
        parole.append(0x00000000)
    righe = [f"C0000000 {len(parole) // 2:08X}"]
    righe += [f"{parole[i]:08X} {parole[i + 1]:08X}" for i in range(0, len(parole), 2)]
    return righe


def f32(x):
    return struct.unpack(">I", struct.pack(">f", x))[0]


def scrivi32(indirizzo, valore):
    """Riga Gecko 04: scrive 32 bit (una volta per frame)."""
    return f"{0x04000000 | (indirizzo & 0x1FFFFFF):08X} {valore & 0xFFFFFFFF:08X}"
