"""Codici AR cambiati DAL VIVO dentro Dolphin (senza riavviare il gioco).

Dolphin legge i codici AR all'avvio del gioco e li tiene in memoria come coppie (indirizzo/comando, valore) di 32 bit
(ActionReplay::AREntry, dentro std::vector<AREntry> di ogni ARCode). A ogni fotogramma li esegue. Se riscrivo quelle
coppie nella memoria del processo Dolphin, il codice cambia subito: è così che la camera del menu in gioco si regola
dal vivo anche col codice camera acceso (scrivere nella memoria del gioco non basta: il codice la riscrive ogni volta).

Il codice nuovo deve avere al massimo le righe di quello in esecuzione: le righe che avanzano diventano scritture
innocue in una zona libera (RIGA_VUOTA). Per questo il codice camera si salva sempre con lo stesso numero di righe.
Solo Windows (ReadProcessMemory / WriteProcessMemory, come dolphin_memory_engine)."""
import ctypes
import struct
from ctypes import wintypes

RIGA_VUOTA = "057F0040 00000000"  # scrive 0 a 817F0040 (zona sempre libera): riga che non fa niente

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p), ("AllocationProtect", wintypes.DWORD),
                ("PartitionId", wintypes.WORD), ("RegionSize", ctypes.c_size_t), ("State", wintypes.DWORD),
                ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD)]


_k32.OpenProcess.restype = wintypes.HANDLE
_k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]
_k32.VirtualQueryEx.restype = ctypes.c_size_t
_k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_k32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


def righe_in_byte(righe):
    """["0446A740 3FEDCD7C", ...] -> coppie little-endian come le tiene Dolphin."""
    out = b""
    for r in righe:
        a, b = r.split()
        out += struct.pack("<II", int(a, 16), int(b, 16))
    return out


class Processo:
    def __init__(self, pid):
        self.h = _k32.OpenProcess(0x0008 | 0x0010 | 0x0020 | 0x0400, False, pid)
        if not self.h:
            raise OSError(ctypes.get_last_error(), "OpenProcess")

    def chiudi(self):
        if self.h:
            _k32.CloseHandle(self.h)
            self.h = None

    def regioni(self, max_dim=512 << 20):
        """Memoria privata leggibile e scrivibile (lo heap di Dolphin; non la RAM emulata, che è mappata)."""
        mbi, ind = _MBI(), 0
        while _k32.VirtualQueryEx(self.h, ctypes.c_void_p(ind), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            base, dim = mbi.BaseAddress or 0, mbi.RegionSize
            if mbi.State == 0x1000 and mbi.Type == 0x20000 and mbi.Protect == 0x04 and dim <= max_dim:
                yield base, dim
            ind = base + dim
            if ind >= 0x7FFFFFFF0000:
                break

    def leggi(self, ind, n):
        buf = ctypes.create_string_buffer(n)
        letti = ctypes.c_size_t()
        if not _k32.ReadProcessMemory(self.h, ctypes.c_void_p(ind), buf, n, ctypes.byref(letti)):
            return None
        return buf.raw[:letti.value]

    def scrivi(self, ind, dati):
        scritti = ctypes.c_size_t()
        return bool(_k32.WriteProcessMemory(self.h, ctypes.c_void_p(ind), dati, len(dati), ctypes.byref(scritti))) and scritti.value == len(dati)

    def cerca(self, cosa, allineamento=8, pezzo=8 << 20, max_dim=512 << 20):
        """Tutte le posizioni (allineate) di `cosa` nella memoria privata."""
        trovati = []
        for base, dim in self.regioni(max_dim):
            off = 0
            while off < dim:
                n = min(pezzo + len(cosa), dim - off)
                b = self.leggi(base + off, n)
                if b:
                    i = b.find(cosa)
                    while i >= 0:
                        if (base + off + i) % allineamento == 0:
                            trovati.append(base + off + i)
                        i = b.find(cosa, i + 1)
                off += pezzo
        return sorted(set(trovati))

    def cerca_puntatori(self, indirizzi, pezzo=8 << 20, max_dim=512 << 20):
        """Dove sono salvati i puntatori a quegli indirizzi (8 byte, allineati): {indirizzo: [posizioni]}."""
        voluti = {struct.pack("<Q", a): a for a in indirizzi}
        out = {a: [] for a in indirizzi}
        for base, dim in self.regioni(max_dim):
            off = 0
            while off < dim:
                b = self.leggi(base + off, min(pezzo, dim - off))
                if b:
                    for k, a in voluti.items():  # bytes.find è molto più veloce di una regex
                        i = b.find(k)
                        while i >= 0:
                            if (base + off + i) % 8 == 0:
                                out[a].append(base + off + i)
                            i = b.find(k, i + 1)
                off += pezzo
        return out


def trova_codice(proc, righe_testa):
    """I codici in esecuzione che iniziano con quelle righe: [(indirizzo delle coppie, numero di righe)].
    Il numero di righe lo leggo dal std::vector che le contiene (inizio, fine, capacità subito dopo il puntatore)."""
    testa = righe_in_byte(righe_testa)
    for max_dim in (24 << 20, 512 << 20):  # prima solo i pezzi di heap piccoli (dove stanno i codici): 1-2 s invece di 15
        out = _trova(proc, testa, max_dim)
        if out:
            return out
    return []


def _trova(proc, testa, max_dim):
    pos = proc.cerca(testa, max_dim=max_dim)
    if not pos:
        return []
    out = []
    for buf, dove in proc.cerca_puntatori(pos, max_dim=max_dim).items():
        for p in dove:
            x = proc.leggi(p, 24)
            if not x or len(x) < 24:
                continue
            inizio, fine, cap = struct.unpack("<QQQ", x)
            if inizio == buf and fine > inizio and (fine - inizio) % 8 == 0 and cap >= fine and (fine - inizio) // 8 < 4096:
                out.append((buf, (fine - inizio) // 8))
                break
    return out


def metti_codice(proc, dove, righe):
    """Riscrive il codice in esecuzione con `righe` (senza il nome). False se il nuovo ha più righe di quello che c'è."""
    buf, n = dove
    righe = list(righe)
    while righe and righe[-1] == RIGA_VUOTA:  # le righe vuote in fondo non contano (il codice salvato ne ha per stare largo)
        righe.pop()
    if len(righe) > n:
        return False
    return proc.scrivi(buf, righe_in_byte(list(righe) + [RIGA_VUOTA] * (n - len(righe))))


def ancora_li(proc, dove, righe_testa):
    """Il codice è ancora in quel punto? (se in Dolphin si cambiano i codici, la memoria si sposta)"""
    testa = righe_in_byte(righe_testa)
    return proc.leggi(dove[0], len(testa)) == testa
