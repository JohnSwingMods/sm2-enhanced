"""Spider-Cam dentro l'app unica: collegamento dal vivo con Dolphin (thread ogni 30 ms) e salvataggio del codice.
Stessa logica di spider_cam.py (che resta l'exe separato): codice AR e traduzioni vengono da camera_slider.py."""
import json
import math
import os
import struct
import threading
import time
import traceback
from pathlib import Path

import dolphin_memory_engine as dme

import app_core as core
import camera_slider as cs

cs.INI = None  # i backup li fa l'app
PATCH_ITA = ["$60Hz (PAL60) patch", "0x802ED89C:dword:0x4182005C", "0x803863B0:dword:0x40800034"]
PATCH_PAL = ["$60Hz (PAL60) patch", "0x802ED82C:dword:0x4182005C", "0x80386340:dword:0x40800034"]
GRUPPI = list(cs.GRUPPI)  # cammina, corsa, sprint, salto, swing, palo


def _p(cam, cor, spr, sal, swi, pal):
    return {"cammina": cam, "corsa": cor, "sprint": spr, "salto": sal, "swing": swi, "palo": pal}


PRESET_FISSI = {  # id -> (nome it, nome en, valori, fov)
    "migliorata": ("Camera migliorata (consigliata)", "Improved camera (recommended)",  # la camera di John (prima "Web-Slinger", "Stile ASM")
            _p((3.0, 3.2, 1.2, 0.10), (3.0, 3.4, 1.2, 0.10), (2.8, 3.2, 1.1, 0.13), (2.8, 3.3, 0.55, 0.13),
               (2.6, 3.0, 0.0, 0.13), (3.9, 5.5, 2.0, 0.15)), 95),  # in aria 0.13 (John: con 0.12 un minimo di tremolio in swing)
    "originale": ("Originale del gioco", "Original game camera", {g: orig for g, (_, orig) in cs.GRUPPI.items()}, 90),
}

NOMI_ALTRE_LINGUE = {"migliorata": {"de": "Verbesserte Kamera (empfohlen)", "fr": "Caméra améliorée (recommandée)", "es": "Cámara mejorada (recomendada)"},
                     "originale": {"de": "Originalkamera des Spiels", "fr": "Caméra d'origine du jeu", "es": "Cámara original del juego"}}


def patch_60hz(ver):
    return None if ver == "GK2E52" else PATCH_ITA if ver == "GK2I52" else PATCH_PAL


def trucchi_attivi(dolphin):
    f = Path(dolphin) / "Config" / "Dolphin.ini"
    try:
        righe = f.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    sez = None
    for r in righe:
        s = r.strip()
        if s.startswith("["):
            sez = s
        elif sez == "[Core]" and s.split("=")[0].strip() == "EnableCheats":
            return s.split("=", 1)[1].strip().lower() == "true"
    return False


def attiva_trucchi_ini(dolphin):
    f = Path(dolphin) / "Config" / "Dolphin.ini"
    raw = f.read_bytes() if f.exists() else b""
    nl = "\n" if raw and b"\r\n" not in raw else "\r\n"
    L = raw.decode("utf-8-sig", errors="ignore").split(nl) if raw else []
    if "[Core]" not in [x.strip() for x in L]:
        L = ["[Core]", "EnableCheats = True"] + L
    else:
        i = [x.strip() for x in L].index("[Core]")
        j = i + 1
        while j < len(L) and not L[j].strip().startswith("["):
            if L[j].split("=")[0].strip() == "EnableCheats":
                L[j] = "EnableCheats = True"
                break
            j += 1
        else:
            L.insert(i + 1, "EnableCheats = True")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(nl.join(L).encode("utf-8"))


def preset_spidercam():
    """Configurazioni e ultimi valori della vecchia Spider-Cam (%APPDATA%\\Spider-Cam), per non perderli."""
    f = Path(os.environ.get("APPDATA", Path.home())) / "Spider-Cam" / "config.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, None
    return d.get("preset", {}), d.get("ultimi")


class Camera:
    """Thread che, quando è acceso (pagina Spider-Cam aperta), si aggancia al gioco e scrive i valori dal vivo."""

    def __init__(self):
        self.attiva = False
        self.valori = {g: tuple(PRESET_FISSI["migliorata"][2][g]) for g in GRUPPI}
        self.fov = 95.0
        self._fov_da_scrivere = True
        self.stato = {"conn": "off", "id": None, "gruppo": None, "dati": None, "conflitto": False}
        self._scritti, self._diversi = None, 0
        self._ultimo_aggancio = 0.0
        self._lock = threading.Lock()
        threading.Thread(target=self._giro, daemon=True).start()

    def imposta(self, valori, fov):
        with self._lock:
            self.valori = {g: tuple(float(x) for x in valori[g]) for g in GRUPPI}
            if abs(float(fov) - self.fov) > 1e-6:
                self.fov = float(fov)
                self._fov_da_scrivere = True

    def accendi(self, si):
        self.attiva = bool(si)
        if si:
            self._fov_da_scrivere = True
            self._scritti, self._diversi = None, 0

    def _giro(self):
        while True:
            if self.attiva:
                try:
                    self._aggiorna()
                except RuntimeError:
                    self._sgancia()
                except Exception:  # noqa: BLE001 - il ciclo non deve mai fermarsi
                    core.log_errore(traceback.format_exc())
                    self._sgancia()
            time.sleep(0.03 if self.attiva else 0.25)

    def _sgancia(self):
        try:
            dme.un_hook()
        except Exception:  # noqa: BLE001
            pass

    def _aggiorna(self):
        now = time.monotonic()
        if not dme.is_hooked() and now - self._ultimo_aggancio < 0.7:
            return
        if not dme.is_hooked():
            self._ultimo_aggancio = now
        base = cs.base_oggetto()  # aggancia Dolphin e legge l'ID (cs.versione)
        st = {"conn": "off", "id": None, "gruppo": None, "dati": None, "conflitto": False}
        if not dme.is_hooked():
            st["conn"] = "dolphin" if core.exe_dolphin_aperti() else "off"
        else:
            id_ = cs.versione or ""
            st["id"] = id_ if id_.isalnum() and len(id_) == 6 else None
            if st["id"] is None:
                st["conn"] = "dolphin"
            elif st["id"] not in cs.VERSIONI:
                st["conn"] = "altro"
            elif cs.VERSIONI[st["id"]].get("modo_video") and dme.read_word(cs.VERSIONI[st["id"]]["modo_video"]) not in (0, 8):
                st["conn"] = "pal50"
            else:
                st["conn"] = "live" if base else "carica"
        if st["conn"] == "live":
            self._scrivi(base, st)
        else:
            self._fov_da_scrivere, self._scritti, self._diversi = True, None, 0
        self.stato = st

    def _scrivi(self, base, st):
        A = cs.A
        with self._lock:
            v = dict(self.valori)
            fov = self.fov
            scrivi_fov, self._fov_da_scrivere = self._fov_da_scrivere, False
        stato, stick = dme.read_word(A(cs.STATO)), dme.read_float(A(cs.STICK))
        g = cs.gruppo_attivo(stato, stick, dme.read_float(A(cs.SPRINT)))
        terra = v[g] if g in ("palo", "corsa", "sprint") else v["cammina"]
        aria = v["salto"] if g == "salto" else v["palo"] if g == "palo" else v["swing"]
        scritture = ((cs.TERRA_MIN, terra[0]), (cs.TERRA_DES, terra[1]), (cs.ARIA_MIN, aria[0]),
                     (cs.ARIA_DES, aria[1]), (cs.ALTEZZA, v[g][2]))
        letti = struct.unpack(">5f", dme.read_bytes(base + cs.TERRA_MIN - 4, 20))
        letti = dict(zip((cs.ALTEZZA, cs.TERRA_MIN, cs.TERRA_DES, cs.ARIA_MIN, cs.ARIA_DES), letti))
        cambiato = self._scritti is not None and any(abs(letti[o] - x) > 1e-3 for o, x in self._scritti)
        self._diversi = self._diversi + 1 if cambiato else 0
        # il codice AR acceso riscrive i valori: lo vedo dal flag che scrive appena parte (FOV di partenza, 817F000C)
        # anche se i suoi valori sono uguali a quelli degli slider; oppure dai valori riscritti (codici vecchi senza flag)
        st["codice"] = dme.read_byte(A(0x817F000C)) == 1
        st["conflitto"] = st["codice"] or self._diversi > 15
        for off, val in scritture:
            dme.write_float(base + off, val)
        self._scritti = scritture
        dme.write_float(A(cs.RITARDO), v[g][3])
        if scrivi_fov:
            dme.write_float(A(cs.FOV), math.radians(fov))
        if g == "palo":
            dme.write_float(base + cs.ATT_MIN, v["palo"][0])
            dme.write_float(base + cs.ATT_DES, v["palo"][1])
        if dme.read_word(A(cs.CAMERA_OBJ + 0x22C)) == A(cs.MODO_M8):
            dme.write_word(A(cs.CAMERA_OBJ + 0x228), A(cs.MODO_M8))
            dme.write_word(A(cs.CAMERA_OBJ + 0x22C), A(cs.MODO_M1))
        c = struct.unpack(">3f", dme.read_bytes(A(cs.CAM), 12))
        s = struct.unpack(">3f", dme.read_bytes(A(cs.SPIDEY), 12))
        vera = struct.unpack(">3f", dme.read_bytes(A(cs.CAMERA_VERA), 12))
        st["gruppo"] = g
        voluta = (math.hypot(c[0] - s[0], c[2] - s[2]), c[1] - s[1])
        if voluta[0] <= 30:  # a volte per un attimo lì c'è un'altra camera
            st["dati"] = {"voluta": voluta, "vera": (math.hypot(vera[0] - s[0], vera[2] - s[2]), vera[1] - s[1]),
                          "min": v[g][0], "des": v[g][1], "fov": math.degrees(dme.read_float(A(cs.FOV)))}


RIGHE_CAMERA = 64  # il codice camera si salva sempre di 64 righe (il più lungo possibile ne ha 60): così il menu in gioco
# lo può cambiare dal vivo dentro Dolphin con qualsiasi valore (ar_vivo: il codice nuovo non può essere più lungo)


def testa_vivo(gid):
    """Le prime righe del codice camera (non dipendono dai valori) con cui ar_vivo lo ritrova nella memoria di Dolphin.
    Le prime 2 sono le righe "solo in partita", uguali in TUTTI i codici coi comandi (HUD, FOV, costume): serve anche la
    3a (497F000C, FOV di partenza scritto una volta), che c'è solo nella camera. Con 2 righe ar_vivo trovava anche HUD e
    costume e li sovrascriveva con la camera (controllo testa_ar_vivo_unica)."""
    return codici(PRESET_FISSI["migliorata"][2], 95, gid)[0][1:2 + len(cs.riga_pausa())]


def codici(valori, fov, ver):
    import ar_vivo
    camera = cs.codice_ar({g: tuple(valori[g]) for g in GRUPPI}, round(fov))
    righe_fov = cs.righe_fov()
    regole = cs.VERSIONI[ver].get("regole") or []
    camera = camera[:1] + [cs.traduci_riga(x, regole) for x in camera[1:]]
    camera += [ar_vivo.RIGA_VUOTA] * max(0, RIGHE_CAMERA - (len(camera) - 1))
    righe_fov = righe_fov[:1] + [cs.traduci_riga(x, regole) for x in righe_fov[1:]]
    return camera, righe_fov


def salva(dolphin, valori, fov, ver):
    """Scrive Custom camera + FOV (+ patch 60Hz per le PAL) in GameSettings/<ver>.ini. (Le "copie extra" della vecchia
    Spider-Cam, le cartelle extra del pack, non le scrive più: l'app non aveva modo di sceglierle.)"""
    unici = [Path(dolphin) / "GameSettings" / f"{ver}.ini"]
    camera, righe_fov = codici(valori, fov, ver)
    salvati, errori = [], []
    for f in unici:
        try:
            core.backup_file(f, "GameSettings")
            cs.salva_in_ini(camera, vecchi=cs.VECCHI_CAMERA, ini=f)
            cs.salva_in_ini(righe_fov, cs.NOME_FOV, vecchi=cs.VECCHI_FOV, ini=f, accendi=None)  # il FOV con le frecce resta com'era
            if patch_60hz(ver):
                cs.salva_in_ini(patch_60hz(ver), patch_60hz(ver)[0], ini=f, tipo="OnFrame")
            salvati.append(str(f))
        except (OSError, ValueError) as e:
            errori.append(f"{f}: {e}")
    return {"salvati": salvati, "errori": errori, "righe": len(camera) - 1}


def installa_patch(dolphin, ver):
    f = Path(dolphin) / "GameSettings" / f"{ver}.ini"
    p = patch_60hz(ver) or PATCH_ITA
    core.backup_file(f, "GameSettings")
    cs.salva_in_ini(p, p[0], ini=f, tipo="OnFrame")
