"""Finestrella con slider per regolare la camera di Spider-Man 2 in tempo reale, stato per stato.

Stati (int a [oggetto stato]+0x18C4, oggetto stato = 80AD0140):
  1 = a terra (camminata / corsa: distinte dallo stick, float a +0x18A4 da 0 a 1)
  3 = swing (appeso alla ragnatela)   5 = in aria (salto / caduta)   8 = sul palo
Il gioco usa il profilo TERRA per 1, il profilo ARIA per 3 e 5. Sul palo (8) NON ricopia il profilo:
restano congelati i valori attuali (+0xD2C/+0xD30) di quando l'hai preso → sul palo si scrivono quelli. Ogni frame copia il profilo nei valori attuali,
quindi basta riscrivere il profilo giusto in base allo stato (lo fa questa finestra dal vivo, e il codice AR in gioco).

Parametri camera (oggetto raggiunto dal puntatore fisso [8056D584]):
  +0xD34 altezza | +0xD38/+0xD3C terra min/desiderata | +0xD40/+0xD44 aria min/desiderata
"""
import json
import math
import shutil
import struct
from pathlib import Path
try:  # tkinter serve solo alla finestrella (App): l'app unica importa questo file per il codice AR e l'exe non
    import tkinter as tk  # include tkinter (Tcl/Tk = ~900 file da scompattare a ogni avvio)
    from tkinter import messagebox, simpledialog, ttk
except ImportError:
    tk = messagebox = simpledialog = ttk = None

import dolphin_memory_engine as dme

PUNTATORE = 0x8056D584
STATO = 0x80AD1A04   # int: 1 terra, 3 swing, 5 aria, 8 palo
STICK = 0x80AD19E4   # float 0..1: quanto è spinto lo stick
SOGLIA_CORSA = 0.9   # stick oltre questa soglia = corsa
SPRINT = 0x80AD17FC  # float: 0 in corsa, 1 in sprint (stick + L)
CAM = 0x804BD2E4     # posizione camera VOLUTA (indirizzo fisso)
CAMERA_VERA = 0x81522B90  # posizione camera vera (quella disegnata; insegue la voluta con RITARDO)
SPIDEY = 0x80495F4C  # posizione Spider-Man (indirizzo fisso)
ALTEZZA, TERRA_MIN, TERRA_DES, ARIA_MIN, ARIA_DES = 0xD34, 0xD38, 0xD3C, 0xD40, 0xD44
ATT_MIN, ATT_DES = 0xD2C, 0xD30  # valori attuali: sul palo il gioco NON li ricopia dal profilo (restano congelati)
CAMERA_OBJ = 0x81522958  # oggetto camera (fisso, = [8056D584]); elenco modalità da +0x1F0, precedente +0x228, attuale +0x22C
MODO_M1, MODO_M8 = 0x815235F8, 0x81523B68  # m8 = camera del palo "ferma", m1 = camera normale (quella dello swing)
INI = Path.home() / "Documents" / "Dolphin Emulator" / "GameSettings" / "GK2E52.ini"
BACKUP = Path(__file__).parent / "backup" / "GK2E52.ini.prima_camera"
NOME_CODICE = "$Custom camera, Z + d-pad down to switch custom/original camera"
# nomi di prima del codice camera: salvando, il codice nuovo prende il posto del primo che trova (gli altri spariscono)
VECCHI_CAMERA = ["$Close camera, Z + d-pad down to switch close/original camera", "$Close camera", "$Z + d-pad down to switch close/original camera",
                 "$Z + d-pad up to switch close/original camera"]
VECCHI_FOV = []

# Versioni del gioco. Gli indirizzi qui sopra sono quelli USA; per l'italiana (CON la patch 60Hz, che sposta gli
# oggetti) si traducono con REGOLE_ITA (verificate dal vivo, sessione 6). Quelli non elencati restano uguali
# (stato/stick/sprint di Spidey 80AD...., texture, zona libera 817F....).
GAMESETTINGS = Path.home() / "Documents" / "Dolphin Emulator" / "GameSettings"
# copie extra degli INI (pack di sviluppo, una cartella per versione): percorso in pack_sviluppo.txt (non pubblicato)
_PACK = Path(__file__).with_name("pack_sviluppo.txt")
H = Path(_PACK.read_text(encoding="utf-8").strip()) if _PACK.is_file() else None
H_ITA = H / "ITALIAN" / "GameSettings" if H else None
H_ENG = H / "ENGLISH (USA)" / "GameSettings" if H else None
REGOLE_ITA = [  # (da, fino a, spostamento)
    (0x8046A740, 0x8046A744, 0x80),   # FOV
    (0x804BD2E4, 0x804BD2F0, 0x80),   # posizione camera voluta
    (0x80495F4C, 0x80495F58, 0xA0),   # posizione Spidey
    (0x80554620, 0x80554622, 0x80),   # tasti
    (0x8056D0C0, 0x8056D0C4, 0x80),   # puntatore opzioni (blur)
    (0x8056B9B8, 0x8056B9BC, 0x80),   # gioco in pausa
    (0x804DCE2A, 0x804DCE2B, 0x80),   # modo dell'interfaccia: 1 in partita, 2 menu di pausa
    (0x8056D584, 0x8056D588, 0x80),   # puntatore camera
    (0x81522958, 0x81524000, 0x80),   # oggetto camera e sue modalità (anche come VALORI: fix del palo)
]
VERSIONI = {
    "GK2E52": {"nome": "USA", "titolo": "VERSIONE AMERICANA (USA)", "colore": "#1f3a93",
               "file": [GAMESETTINGS / "GK2E52.ini"] + [H_ENG / f for f in (
                   "GK2E52.ini", r"xbox\GK2E52.ini", r"android\GK2E52.ini", r"android\GK2E52_30fps.ini") if H]},
    "GK2I52": {"nome": "ITA", "titolo": "VERSIONE ITALIANA (PAL, 60Hz)", "colore": "#1e7b3a",
               "file": [GAMESETTINGS / "GK2I52.ini"] + [H_ITA / f for f in (
                   "GK2I52.ini", r"xbox\GK2I52.ini", r"android\GK2I52.ini", r"android\GK2I52_30fps.ini") if H]},
}
MODO_VIDEO_ITA = 0x8056C3B0  # 8 = 60Hz (EuRGB60, patch attiva), 2 = 50Hz: senza patch gli oggetti sono altrove
MODO_VIDEO_PAL = 0x8056C330  # stessa cosa per UK/Germania/Francia (hanno il programma americano: r13 80573260)
# UK (GK2P52), Germania (GK2D52), Francia (GK2F52): stesso main.dol dell'americana (md5 identico) -> tutti gli
# indirizzi fissi uguali; con la patch 60Hz cambia solo l'heap per lingua (verificato dal vivo, sessione 7).
REGOLE_DE = [(0x81522958, 0x81524000, -0x1060)]  # tedesca: solo l'oggetto camera (e modalità) si sposta
for _id, _nome, _titolo, _col, _regole, _cartella in (
        ("GK2P52", "UK", "VERSIONE INGLESE (PAL, 60Hz)", "#8a1c2b", [], "ENGLISH (UK)"),
        ("GK2D52", "DE", "VERSIONE TEDESCA (PAL, 60Hz)", "#5a5a5a", REGOLE_DE, "GERMAN"),
        ("GK2F52", "FR", "VERSIONE FRANCESE (PAL, 60Hz)", "#2b4a9e", [], "FRENCH")):  # [] = come l'americana
    VERSIONI[_id] = {"nome": _nome, "titolo": _titolo, "colore": _col, "regole": _regole,
                     "modo_video": MODO_VIDEO_PAL, "file": [GAMESETTINGS / f"{_id}.ini"] + [
                         H / _cartella / "GameSettings" / f.replace("ID", _id) for f in (
                             "ID.ini", r"xbox\ID.ini", r"android\ID.ini", r"android\ID_30fps.ini") if H]}
VERSIONI["GK2E52"]["regole"] = []
VERSIONI["GK2I52"].update(regole=REGOLE_ITA, modo_video=MODO_VIDEO_ITA)
versione = None  # ID del gioco letto dalla RAM


def sposta(a, regole):
    for da, fino, d in regole or ():
        if da <= a < fino:
            return a + d
    return a


def sposta_ita(a):
    return sposta(a, REGOLE_ITA)


def A(a):
    """Indirizzo USA -> indirizzo della versione aperta."""
    return sposta(a, VERSIONI.get(versione, {}).get("regole"))


def traduci_riga(riga, regole):
    """Riga AR USA -> altra versione (indirizzo, e valore se è un indirizzo dell'oggetto camera, es. fix del palo)."""
    w, v = (int(x, 16) for x in riga.split())
    a = sposta(0x80000000 | (w & 0x01FFFFFF), regole)
    if 0x81522958 <= v < 0x81524000:
        v = sposta(v, regole)
    return f"{(w & 0xFE000000) | (a & 0x01FFFFFF):08X} {v:08X}"


def traduci_riga_ita(riga):
    return traduci_riga(riga, REGOLE_ITA)

FOV = 0x8046A740  # float, radianti: visuale orizzontale (orig 1.57 = 90°). Letto dal gioco a ogni frame.
FOV_ORIG = 90.0   # gradi
RITARDO = 0x815233A8  # float 0.2: "morbidezza" con cui la camera vera insegue quella voluta (oggetto camera +0xA50)
# (più basso = camera più attaccata a Spidey quando va veloce; non usare 0)

# gruppo -> (etichetta, (minima, desiderata, altezza, ritardo) originali del gioco)
GRUPPI = {
    "cammina": ("Fermo / camminata", (4.0, 5.0, 2.0, 0.2)),
    "corsa": ("Corsa", (4.0, 5.0, 2.0, 0.2)),
    "sprint": ("Sprint (L)", (4.0, 5.0, 2.0, 0.2)),
    "salto": ("Salto / caduta", (2.5, 5.5, 2.0, 0.2)),
    "swing": ("Swing", (2.5, 5.5, 2.0, 0.2)),
    "palo": ("Palo", (2.5, 5.5, 2.0, 0.2)),
}
# valori di partenza (minima, desiderata, altezza, ritardo): preset "stile The Amazing Spider-Man"
# (camera vicina all'altezza delle spalle, poco ritardo, swing incollato dietro). Precedenti di John:
# terra 4.0/4.0/1.5, aria 2.9/2.9/1.5, palo 3.9/5.5/2.0, ritardo 0.2 ovunque.
PARTENZA = {"cammina": (3.0, 3.2, 1.4, 0.15), "corsa": (3.0, 3.4, 1.4, 0.12), "sprint": (2.8, 3.2, 1.3, 0.12),
            "salto": (2.8, 3.3, 1.4, 0.12), "swing": (2.6, 3.0, 1.3, 0.12), "palo": (3.9, 5.5, 2.0, 0.15)}
# (swing con ritardo 0.06 = camera scattosa/tremolante: copia ogni oscillazione del pendolo → 0.12)

COLLEGATI = ("sprint", "salto", "swing")  # gruppi con il ritardo collegato (casella nella finestrella)

# Configurazioni pronte (non cancellabili); quelle di John stanno in preset_camera.json
PRESET_FILE = Path(__file__).parent / "preset_camera.json"
PRESET_FISSI = {
    "Stile Amazing Spider-Man": PARTENZA,
    "Vecchio codice": {"cammina": (4.0, 4.0, 1.5, 0.2), "corsa": (4.0, 4.0, 1.5, 0.2),
                              "sprint": (4.0, 4.0, 1.5, 0.2), "salto": (2.9, 2.9, 1.5, 0.2),
                              "swing": (2.9, 2.9, 1.5, 0.2), "palo": (3.9, 5.5, 2.0, 0.2)},
    "Originale del gioco": {g: orig for g, (_, orig) in GRUPPI.items()},
}


INTOCCABILE = "Originale del gioco"  # unica configurazione che non si può sovrascrivere


def leggi_preset_utente():
    try:
        return json.loads(PRESET_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def scrivi_preset_utente(preset):
    PRESET_FILE.write_text(json.dumps(preset, indent=2, ensure_ascii=False), encoding="utf-8")


def gruppo_attivo(stato, stick, sprint=0.0):
    if stato == 8:
        return "palo"
    if stato == 3:
        return "swing"
    if stato == 5:
        return "salto"
    if sprint > 0.5:
        return "sprint"
    return "corsa" if stick > SOGLIA_CORSA else "cammina"


def base_oggetto():
    global versione
    if not dme.is_hooked():
        dme.hook()
        if not dme.is_hooked():
            versione = None
            return None
    try:
        versione = dme.read_bytes(0x80000000, 6).decode("ascii", "replace")
        if versione not in VERSIONI:
            return None
        info = VERSIONI[versione]
        if info.get("regole") is None:
            return None  # versione non ancora verificata: meglio non scrivere niente
        if info.get("modo_video") and dme.read_word(info["modo_video"]) != 8:
            return None  # PAL senza patch 60Hz: gli indirizzi non valgono, meglio non scrivere niente
        p = dme.read_word(A(PUNTATORE))
    except RuntimeError:
        dme.un_hook()
        return None
    return p if 0x80000000 <= p < 0x81800000 else None


def ar(tipo, indirizzo):
    """Prima metà di una riga AR: l'indirizzo ha 25 bit, il bit 24 (indirizzi 81xxxxxx) va nel primo byte."""
    return f"{tipo | ((indirizzo >> 24) & 1):02X}{indirizzo & 0xFFFFFF:06X}"


def righe_float(off, v):
    """Un float scritto tramite puntatore = due scritture a 16 bit: 4256D584 OOOOVVVV (OOOO = offset/2)."""
    hi, lo = struct.unpack(">2H", struct.pack(">f", v))
    p = PUNTATORE & 0xFFFFFF
    return [f"42{p:06X} {off // 2:04X}{hi:04X}", f"42{p:06X} {off // 2 + 1:04X}{lo:04X}"]


PAUSA = 0x804DCE2A  # byte modo dell'interfaccia: 1 = in partita (anche swing, riflessi, dopo il tuffo), 2 = pausa (ITA 804DCEAA). Vedi
# app_core.RIGHE_PARTITA: quello della sessione 9 (8054517F) su USA a volte restava a 0; il vecchio 8056B9B8 valeva 1
# anche durante gli Spider Reflexes (i codici si fermavano col rallenty).


STATO_SPIDEY = 0x80AD1A04  # int: -1 = Spidey non c'è (titolo, menu iniziali, caricamenti); uguale in tutte le versioni
PAUSA_GIOCO = 0x8056B9BB  # byte: 1 = menu di pausa (anche nel rallenty), 0 = si gioca (anche nella mappa) (ITA 8056BA3B)
# byte: 80 = mappa grande del gioco aperta (anche cambiando scheda), 10 = no (ITA 8056B96C). Lo scrive il gioco a
# 0x801FF514 (ITA) solo con questi due valori, da due flag della mappa ([[0x804C28D8]+0x50]+0x4FF8/9); lo usa anche
# l'HUD 16:9. (0x804DCB75/F5 NO: vale 1 anche giocando.)
MAPPA_APERTA = 0x8056B8EC


def riga_pausa():
    """Prime righe dei codici coi comandi (sottotipo 3 = "esegui il resto del codice solo se", due di fila = E):
    Spidey c'è (stato != -1) E il gioco non è in pausa -> nel menu di pausa (dove le frecce servono per muoversi) e al
    titolo il codice non fa niente. Prima: il modo dell'interfaccia (PAUSA) = 1, ma mentre giochi salta a 0 e a 2 per
    qualche fotogramma (girando con la levetta 16 su 100): le pressioni di L3/LB si perdevano e gli interruttori si
    incastravano (John, 2026-10-08). Terza riga (2026-10-18): E la mappa grande è chiusa (nella mappa la croce la muove:
    LB = sinistra+destra accendeva l'HUD, le frecce cambiavano il FOV). Lista di 3 righe."""
    return [f"{ar(0xD4, STATO_SPIDEY)} FFFFFFFF", f"{ar(0xC8, PAUSA_GIOCO)} 00000000", f"{ar(0xD0, MAPPA_APERTA)} 00000050"]


TASTI = 0x80554620  # halfword dei tasti: 0x0001 / 0x0002 = frecce destra/sinistra (vedi righe_fov), giù 0x0004,
#                     su 0x0008, Z/R1 0x0010
NOME_FOV = "$d-pad left to increase FOV, d-pad right to decrease"
FOV_MIN, FOV_MAX = 58, 114  # gradi: tutta la fascia 1.0-2.0 radianti, dove il passo "grezzo" vale sempre 1°


def bit_float(x):
    return struct.unpack(">I", struct.pack(">f", x))[0]


def righe_fov():
    """FOV con le frecce, partendo dal FOV attuale (nessun valore di partenza).
    Trucco: tra 1.0 e 2.0 rad un float ha sempre lo stesso esponente, quindi sommare un intero ai suoi 32 bit
    sposta il valore di una quantità fissa: 1° = 0.0174533 rad = 146410 "passi" (2^23 passi per unità).
    L'AR sa fare somme intere (codice 84 = somma a 32 bit) -> ±1° esatto sul valore che c'è, senza tabelle.
    Tasto 0x0002 = FOV -1° (avvicina), 0x0001 = FOV +1° (allontana); solo SENZA R1 (codice HUD di John).
    Byte liberi: 817F0008/09 = freccia già premuta nel frame prima, 817F000A/0B = premuta adesso."""
    passo = round(math.radians(1) * 2 ** 23)

    def riga(tipo, addr, val):
        return f"{ar(tipo, addr)} {val & 0xFFFFFFFF:08X}"
    r = [NOME_FOV, *riga_pausa()]  # generico: nessun valore di partenza (quello sta nel codice camera)
    for bit, prima, adesso, delta in ((0x0002, 0x817F0008, 0x817F000A, -passo),
                                      (0x0001, 0x817F0009, 0x817F000B, passo)):
        r += [riga(0x00, adesso, 0), riga(0x3A, TASTI, bit), riga(0x00, adesso, 1),   # freccia premuta...
              riga(0x3A, TASTI, 0x0010), riga(0x00, adesso, 0),                       # ...ma non con R1 (HUD)
              riga(0x48, adesso, 1), riga(0x08, prima, 0), riga(0x84, FOV, delta),    # appena premuta: ±1°
              riga(0x08, adesso, 0), riga(0x00, prima, 0), riga(0x08, adesso, 1), riga(0x00, prima, 1)]
    lo, hi = bit_float(math.radians(FOV_MIN)), bit_float(math.radians(FOV_MAX))
    # limiti (float positivi: confronto sui bit = confronto valori), SOLO mentre la freccia è tenuta: sempre attivi
    # riportavano a 114° anche il FOV più largo della prima persona attaccata al muro (124°)
    r += [riga(0x48, 0x817F000A, 1), riga(0x2C, FOV, lo), riga(0x04, FOV, lo),
          riga(0x48, 0x817F000B, 1), riga(0x34, FOV, hi), riga(0x04, FOV, hi)]
    return r


def normalizza(x):
    """(dist, alt) | (min, des, alt) | (min, des, alt, ritardo) -> (min, des, alt, ritardo)"""
    if len(x) == 2:
        return (x[0], x[0], x[1], 0.2)
    if len(x) == 3:
        return (*x, 0.2)
    return tuple(x)


def righe_fov_partenza(gradi):
    """FOV di partenza, scritto UNA volta sola all'avvio (flag 817F000C): poi il codice "FOV con frecce"
    (generico, senza valori) può cambiarlo partendo da qui. Sta nel codice camera, così ogni camera ha il suo FOV."""
    return [f"{ar(0x48, 0x817F000C)} 00000000", f"{ar(0x04, FOV)} {bit_float(math.radians(gradi)):08X}",
            f"{ar(0x00, 0x817F000C)} 00000001"]


def righe_interruttore(fov_gradi=None):
    """Z + freccia giù: camera personalizzata <-> originale. Ritorna (testa, coda) da mettere all'inizio e in fondo
    al codice camera. Byte liberi: C = 817F0010 (contatore pressioni: dispari = originale),
    halfword 817F0012 = [A][P]: P = Z e giù premuti adesso, A = erano premuti (già contati).
    Coda: se C è dispari (condizione AND, sottotipo 3 = "tutto il resto del codice") riscrive gli originali sopra
    quelli personalizzati (il gioco non rimette mai da solo i profili).
    FOV: mentre Z+giù è tenuto ([A][P] = 0101, già contato) rimette il FOV della camera scelta: quello di partenza
    della personalizzata (fov_gradi) o l'originale 1.57 (in coda, solo se C dispari) -> lo switch "resetta" il FOV."""
    c, a, pp = 0x817F0010, 0x817F0012, 0x817F0013

    def riga(tipo, addr, val):
        return f"{ar(tipo, addr)} {val:08X}"
    testa = [riga(0x00, pp, 0), riga(0x7A, TASTI, 0x0010), riga(0x3A, TASTI, 0x0004), riga(0x00, pp, 1),  # P
             riga(0x4A, a, 0x0001), riga(0x80, c, 1), riga(0x00, a, 1),   # A=0 e P=1 (appena premuti): C+1, A=1
             riga(0x08, pp, 0), riga(0x00, a, 0)]                         # lasciati: A=0
    coda = [riga(0xF8, c, 1)]
    if fov_gradi is not None:
        testa += [riga(0x0A, a, 0x0101), riga(0x04, FOV, bit_float(math.radians(fov_gradi)))]
        coda += [riga(0x0A, a, 0x0101), riga(0x04, FOV, bit_float(1.57))]
    coda += [riga(0x04, CAMERA_OBJ + off, bit_float(x)) for off, x in
                                 ((ALTEZZA, 2.0), (TERRA_MIN, 4.0), (TERRA_DES, 5.0), (ARIA_MIN, 2.5), (ARIA_DES, 5.5))]
    return testa, coda + [riga(0x04, RITARDO, bit_float(0.2))]


def codice_ar(v, fov_partenza=None):
    """v[gruppo] = (min, desiderata, altezza, ritardo) (accetta anche le forme corte, vedi normalizza).
    Ordine: valori base (camminata a terra, swing in aria), poi override condizionali.
    Condizionale AR su word: 4C = uguale, 74 = maggiore senza segno ("esegui le 2 righe dopo");
    togliendo i 2 bit alti (0x0C / 0x34) vale solo per la riga dopo (usato per il ritardo, 1 riga)."""
    v = {g: normalizza(x) for g, x in v.items() if g in GRUPPI}
    r = [NOME_CODICE, *riga_pausa()]  # le frecce del FOV sono un codice a parte (righe_fov); qui solo il FOV di partenza
    if fov_partenza is not None:
        r += righe_fov_partenza(fov_partenza)
    testa, coda = righe_interruttore(fov_partenza)
    r += testa

    # Versione compatta: l'oggetto camera è FISSO a 81522958 (verificato su molti avvii), quindi scrivo i float
    # direttamente (1 riga ciascuno) invece che tramite il puntatore 8056D584 (2 righe da 16 bit ciascuno).
    ind = {g: CAMERA_OBJ + o for g, o in (("alt", ALTEZZA), ("tmin", TERRA_MIN), ("tdes", TERRA_DES),
                                           ("amin", ARIA_MIN), ("ades", ARIA_DES), ("pmin", ATT_MIN),
                                           ("pdes", ATT_DES))}
    ind["rit"] = RITARDO

    def scrivi(campo, val):
        return f"{ar(0x04, ind[campo])} {bit_float(val):08X}"

    def blocco(cond_tipo, cond_ind, cond_val, scritture):
        """Condizione "2 righe dopo" (tipo base) per ogni coppia di scritture, "1 riga dopo" per l'ultima dispari."""
        out = []
        for k in range(0, len(scritture), 2):
            coppia = scritture[k:k + 2]
            tipo = cond_tipo if len(coppia) == 2 else cond_tipo & 0x3F
            out += [f"{ar(tipo, cond_ind)} {cond_val:08X}"] + [scrivi(c, x) for c, x in coppia]
        return out

    campi = ("min", "des", "alt", "rit")
    cam, cor, spr = v["cammina"], v["corsa"], v["sprint"]
    r += [scrivi("alt", cam[2]), scrivi("tmin", cam[0]), scrivi("tdes", cam[1]), scrivi("rit", cam[3]),
          scrivi("amin", v["swing"][0]), scrivi("ades", v["swing"][1])]

    def diversi(nuovo, *precedenti, nomi):
        """Solo i campi che cambiano rispetto a TUTTI i valori che potrebbero esserci prima (niente righe inutili)."""
        return [(nomi[i], nuovo[i]) for i in range(4) if any(abs(nuovo[i] - p[i]) > 1e-6 for p in precedenti)]

    terra = ("tmin", "tdes", "alt", "rit")
    soglia = bit_float(SOGLIA_CORSA)
    r += blocco(0x74, STICK, soglia, diversi(cor, cam, nomi=terra))            # corsa (stick > 0.9)
    r += blocco(0x74, SPRINT, bit_float(0.5), diversi(spr, cor, nomi=terra))   # sprint (dopo la corsa)
    # stati in aria / palo: altezza e ritardo potrebbero arrivare da camminata, corsa o sprint
    ground = (cam, cor, spr)
    for stato_n, g, nomi, forza in ((8, "palo", ("pmin", "pdes", "alt", "rit"), True),
                                    (5, "salto", ("amin", "ades", "alt", "rit"), False),
                                    (3, "swing", (None, None, "alt", "rit"), False)):
        x = v[g]
        scr = []
        for i in range(4):
            if nomi[i] is None:
                continue
            if i < 2:  # distanze: palo sempre (valori congelati), salto solo se diverso dallo swing
                if forza or abs(x[i] - v["swing"][i]) > 1e-6:
                    scr.append((nomi[i], x[i]))
            elif any(abs(x[i] - p[i]) > 1e-6 for p in ground):
                scr.append((nomi[i], x[i]))
        r += blocco(0x4C, STATO, stato_n, scr)
    # Palo: il gioco mette la camera in modalità m8 (ferma sulla posizione di entrata finché non muovi gli stick).
    # Quando la modalità attuale è m8 la rimetto a m1 (camera normale): sul palo dà le stesse distanze
    # dell'originale (media 5.2). Oggetto camera 81522958: +0x228 = precedente, +0x22C = attuale.
    attuale, precedente = CAMERA_OBJ + 0x22C, CAMERA_OBJ + 0x228
    r += [f"{ar(0x4C, attuale)} {MODO_M8:08X}", f"{ar(0x04, precedente)} {MODO_M8:08X}",
          f"{ar(0x04, attuale)} {MODO_M1:08X}"]
    return r + coda


def salva_in_ini(righe, nome=None, vecchi=(), ini=None, tipo="ActionReplay", accendi=True):
    """Scrive (o sostituisce) il codice AR `nome` (default NOME_CODICE) nell'INI e lo attiva, lasciando il resto
    del file com'è (righe vuote, CRLF, ordine). Se c'è già il codice o uno dei nomi `vecchi`, il nuovo prende il posto
    del primo che trova (anche nell'elenco dei codici attivi), gli altri vengono tolti; se no va in fondo.
    righe[0] deve essere il nome; righe vuote = cancella il codice.
    tipo = "ActionReplay" (codici AR) oppure "OnFrame" (patch). File o sezioni che mancano vengono creati.
    accendi = None: acceso solo se lo era già (es. FOV con le frecce, spento di base: salvando la camera non va riacceso)."""
    nome = nome or NOME_CODICE
    ini = Path(ini) if ini else INI
    if ini == INI and not BACKUP.exists() and INI.exists():
        BACKUP.parent.mkdir(exist_ok=True)
        shutil.copy2(INI, BACKUP)
    raw = ini.read_bytes() if ini.exists() else b""
    nl = "\n" if raw and b"\r\n" not in raw else "\r\n"
    L = raw.decode("utf-8-sig").split(nl) if raw else []
    nomi = [nome, *vecchi]
    for titolo in (f"[{tipo}]", f"[{tipo}_Enabled]"):
        if titolo not in [x.strip() for x in L]:
            while L and not L[-1].strip():
                L.pop()
            L += ([""] if L else []) + [titolo, ""]
    L = [x.strip() if x.strip().startswith("[") else x for x in L]

    def sezione(titolo):
        i = L.index(titolo) + 1
        j = i
        while j < len(L) and not L[j].startswith("["):
            j += 1
        while j > i and not L[j - 1].strip():  # le righe vuote prima della sezione dopo restano lì
            j -= 1
        return i, j

    i, j = sezione(f"[{tipo}]")
    posto, k = None, i
    while k < j:
        if L[k].strip() in nomi:
            fine = k + 1
            while fine < j and not L[fine].startswith("$"):
                fine += 1
            del L[k:fine]
            j -= fine - k
            posto = k if posto is None else posto
        else:
            k += 1
    if righe:
        L[posto if posto is not None else j:posto if posto is not None else j] = righe
    i, j = sezione(f"[{tipo}_Enabled]")
    attivi = [k for k in range(i, j) if L[k].strip() in nomi]
    posto = attivi[0] if attivi else j
    for k in reversed(attivi):
        del L[k]
    if righe and (accendi or accendi is None and attivi):
        L.insert(posto, nome)
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_bytes(nl.join(L).encode("utf-8"))


class App:
    def __init__(self, root):
        self.root = root
        root.title("Camera Spider-Man 2")
        # insegna con la versione del gioco aperta (bandiera + scritta), aggiornata da tick()
        self.insegna = tk.Frame(root, bg="#777777")
        self.insegna.grid(row=0, column=0, columnspan=5, sticky="we")
        self.bandiera = tk.Canvas(self.insegna, width=54, height=36, highlightthickness=0, bg="#777777")
        self.bandiera.pack(side="left", padx=10, pady=6)
        self.scritta = tk.Label(self.insegna, text="NESSUN GIOCO APERTO", fg="white", bg="#777777",
                                font=("Segoe UI", 16, "bold"))
        self.scritta.pack(side="left", padx=6)
        self._versione_mostrata = "?"
        self.vars = {}
        for col, testo in enumerate(("Minima", "Desiderata", "Altezza", "Ritardo (più basso = più attaccata)"),
                                    start=1):
            tk.Label(root, text=testo, font=("Segoe UI", 9, "bold")).grid(row=1, column=col)
        self.etichette = {}
        self.scale_minima = []
        slider = ((0.5, 8.0, 0.05, 200), (0.5, 8.0, 0.05, 200), (-1.0, 4.0, 0.05, 160), (0.02, 0.6, 0.01, 200))
        for i, (g, (nome, orig)) in enumerate(GRUPPI.items(), start=2):
            lab = tk.Label(root, text=f"{nome}\n(orig. {' / '.join(str(x) for x in orig)})", anchor="w",
                           justify="left", width=22)
            lab.grid(row=i, column=0, sticky="w", padx=8, pady=4)
            self.etichette[g] = lab
            vars_riga = []
            for col, (lo, hi, passo, lung) in enumerate(slider, start=1):
                var = tk.DoubleVar(value=PARTENZA[g][col - 1])
                scala = tk.Scale(root, variable=var, from_=lo, to=hi, resolution=passo, orient="horizontal",
                                 length=lung)
                scala.grid(row=i, column=col, padx=6)
                if col == 1:
                    self.scale_minima.append(scala)
                vars_riga.append(var)
            self.vars[g] = vars_riga
        n = len(GRUPPI) + 2
        self.stato = tk.Label(root, text="...", font=("Consolas", 11), anchor="w")
        self.stato.grid(row=n, column=0, columnspan=5, sticky="w", padx=8, pady=8)
        # ritardo collegato: sprint, salto e swing si alternano di continuo (corsa sui muri) -> stesso valore
        self.collega = tk.BooleanVar(value=True)
        opz = tk.Frame(root)
        opz.grid(row=n + 3, column=0, columnspan=5, pady=(0, 8))
        tk.Checkbutton(opz, text="Ritardo uguale per sprint, salto e swing", variable=self.collega).pack(
            side="left", padx=10)
        # Minima = Desiderata: usa la desiderata anche come minima, senza toccare gli slider della minima
        self.min_uguale = tk.BooleanVar(value=False)
        tk.Checkbutton(opz, text="Minima = Desiderata", variable=self.min_uguale,
                       command=self.aggiorna_minima).pack(side="left", padx=10)
        # FOV unico per tutti gli stati (cambiarlo per stato darebbe scatti di zoom)
        self.fov = tk.DoubleVar(value=FOV_ORIG)
        tk.Label(opz, text=f"FOV di partenza (orig. {FOV_ORIG:.0f}):").pack(side="left", padx=(20, 4))
        tk.Scale(opz, variable=self.fov, from_=FOV_MIN, to=FOV_MAX, resolution=1, orient="horizontal",
                 length=220).pack(side="left")
        self._sincro = False
        for g in COLLEGATI:
            self.vars[g][3].trace_add("write", lambda *_, sorgente=g: self.sincronizza(sorgente))
        pres = tk.Frame(root)
        pres.grid(row=n + 1, column=0, columnspan=5, pady=4)
        tk.Label(pres, text="Configurazione:").pack(side="left", padx=4)
        self.scelta = tk.StringVar(value="Stile Amazing Spider-Man")
        self.menu = ttk.Combobox(pres, textvariable=self.scelta, state="readonly", width=32)
        self.menu.pack(side="left", padx=4)
        tk.Button(pres, text="Carica", command=self.carica_preset).pack(side="left", padx=4)
        tk.Button(pres, text="Salva", command=self.sovrascrivi_preset).pack(side="left", padx=4)
        tk.Button(pres, text="Salva come...", command=self.salva_preset).pack(side="left", padx=4)
        tk.Button(pres, text="Elimina", command=self.elimina_preset).pack(side="left", padx=4)
        self.aggiorna_menu()
        self.imposta(self.tutti_i_preset()["Stile Amazing Spider-Man"])  # parte dalla versione di John, se salvata
        bott = tk.Frame(root)
        bott.grid(row=n + 2, column=0, columnspan=5, pady=8)
        tk.Button(bott, text="Salva codice AR nel gioco", command=self.salva).pack(side="left", padx=6)
        self.tick()

    def mostra_versione(self):
        if versione == self._versione_mostrata:
            return
        self._versione_mostrata = versione
        c = self.bandiera
        c.delete("all")
        info = VERSIONI.get(versione)
        colore = info["colore"] if info else "#777777"
        if versione == "GK2I52":  # tricolore
            for k, col in enumerate(("#009246", "#ffffff", "#ce2b37")):
                c.create_rectangle(k * 18, 0, k * 18 + 18, 36, fill=col, outline="")
        elif versione == "GK2E52":  # strisce + riquadro blu con le stelline
            for k in range(7):
                c.create_rectangle(0, k * 36 / 7, 54, (k + 1) * 36 / 7, fill="#b22234" if k % 2 == 0 else "#ffffff",
                                   outline="")
            c.create_rectangle(0, 0, 24, 36 * 4 / 7, fill="#3c3b6e", outline="")
            for x in range(3):
                for y in range(3):
                    c.create_oval(4 + x * 7, 3 + y * 6.5, 6 + x * 7, 5 + y * 6.5, fill="white", outline="")
        else:
            c.create_text(27, 18, text="?", fill="white", font=("Segoe UI", 18, "bold"))
        testo = f"{info['titolo']}  ({versione})" if info else "NESSUN GIOCO APERTO"
        for w in (self.insegna, c, self.scritta):
            w.config(bg=colore)
        self.scritta.config(text=testo)
        self.root.title(f"Camera Spider-Man 2 - {info['nome']}" if info else "Camera Spider-Man 2")

    def effettivi(self):
        """Valori usati davvero (gioco e codice AR): con "Minima = Desiderata" la minima diventa la desiderata.
        Gli slider della minima non vengono toccati, così togliendo la spunta tornano i valori di prima."""
        v = self.valori()
        if self.min_uguale.get():
            v = {g: (x[1], x[1], x[2], x[3]) for g, x in v.items()}
        return v

    def aggiorna_minima(self):
        stato = "disabled" if self.min_uguale.get() else "normal"
        for scala in self.scale_minima:
            scala.config(state=stato, fg="gray" if stato == "disabled" else "black")

    def sincronizza(self, sorgente):
        if self._sincro or not self.collega.get():
            return
        self._sincro = True
        try:
            valore = self.vars[sorgente][3].get()
            for g in COLLEGATI:
                if g != sorgente:
                    self.vars[g][3].set(valore)
        finally:
            self._sincro = False

    def tutti_i_preset(self):
        return {**PRESET_FISSI, **leggi_preset_utente()}

    def aggiorna_menu(self):
        self.menu["values"] = list(self.tutti_i_preset())

    def imposta(self, valori):
        for g, vs in self.vars.items():
            for var, val in zip(vs, normalizza(valori[g])):
                var.set(val)
        self.fov.set(valori.get("fov", FOV_ORIG))  # preset vecchi senza FOV -> originale

    def carica_preset(self):
        preset = self.tutti_i_preset().get(self.scelta.get())
        if preset:
            self.imposta(preset)

    def _salva_con_nome(self, nome):
        if nome == INTOCCABILE:
            messagebox.showerror("Non si può", f"\"{INTOCCABILE}\" resta sempre com'è: salvala con un altro nome.")
            return
        preset = leggi_preset_utente()
        preset[nome] = {**self.valori(), "fov": self.fov.get()}
        scrivi_preset_utente(preset)
        self.aggiorna_menu()
        self.scelta.set(nome)

    def sovrascrivi_preset(self):
        nome = self.scelta.get()
        if nome and messagebox.askyesno("Salva", f"Sovrascrivere \"{nome}\" con i valori attuali?"):
            self._salva_con_nome(nome)

    def salva_preset(self):
        nome = simpledialog.askstring("Salva configurazione", "Nome della configurazione:", parent=self.root)
        if nome:
            self._salva_con_nome(nome)

    def elimina_preset(self):
        nome = self.scelta.get()
        preset = leggi_preset_utente()
        if nome not in preset:
            messagebox.showinfo("Non si può", "Le configurazioni pronte (non modificate) non si possono eliminare.")
            return
        domanda = (f"Annullare le tue modifiche a \"{nome}\" e tornare alla versione originale?" if nome in PRESET_FISSI
                   else f"Eliminare la configurazione \"{nome}\"?")
        if messagebox.askyesno("Elimina", domanda):
            del preset[nome]
            scrivi_preset_utente(preset)
            self.aggiorna_menu()
            if nome not in PRESET_FISSI:
                self.scelta.set("Stile Amazing Spider-Man")

    def valori(self):
        """g -> (minima, desiderata, altezza, ritardo)"""
        return {g: tuple(round(x.get(), 2) for x in vs) for g, vs in self.vars.items()}

    def tick(self):
        base = base_oggetto()
        self.mostra_versione()
        if base is None:
            if versione == "GK2I52" and dme.is_hooked():
                testo = "Versione italiana SENZA patch 60Hz: attiva \"60Hz (PAL60) patch\" e riavvia il gioco"
            elif versione and versione not in VERSIONI:
                testo = f"Gioco aperto: {versione} (non è Spider-Man 2 USA/ITA)"
            else:
                testo = "Gioco non agganciato / in caricamento..."
            self.stato.config(text=testo, fg="red")
        else:
            try:
                v = self.effettivi()
                stato, stick, sprint = dme.read_word(A(STATO)), dme.read_float(A(STICK)), dme.read_float(A(SPRINT))
                g = gruppo_attivo(stato, stick, sprint)
                # stessa logica del codice AR: base + override dello stato attuale
                terra = v[g] if g in ("palo", "corsa", "sprint") else v["cammina"]
                aria = v["salto"] if g == "salto" else v["palo"] if g == "palo" else v["swing"]
                for off, val in ((TERRA_MIN, terra[0]), (TERRA_DES, terra[1]), (ARIA_MIN, aria[0]),
                                 (ARIA_DES, aria[1]), (ALTEZZA, v[g][2])):
                    dme.write_float(base + off, val)
                dme.write_float(A(RITARDO), v[g][3])
                dme.write_float(A(FOV), math.radians(self.fov.get()))
                if g == "palo":
                    dme.write_float(base + ATT_MIN, v["palo"][0])
                    dme.write_float(base + ATT_DES, v["palo"][1])
                if dme.read_word(A(CAMERA_OBJ + 0x22C)) == A(MODO_M8):  # come il codice AR: niente camera "ferma"
                    dme.write_word(A(CAMERA_OBJ + 0x228), A(MODO_M8))                  # sul palo
                    dme.write_word(A(CAMERA_OBJ + 0x22C), A(MODO_M1))
                c = struct.unpack(">3f", dme.read_bytes(A(CAM), 12))
                s = struct.unpack(">3f", dme.read_bytes(A(SPIDEY), 12))
                for gg, lab in self.etichette.items():
                    lab.config(bg="#ffe680" if gg == g else root_bg)
                self.stato.config(
                    fg="black",
                    text=f"Adesso: {GRUPPI[g][0]:17s} (stato {stato}, stick {stick:.2f}, sprint {sprint:.0f})  "
                         f"dist. voluta={math.hypot(c[0] - s[0], c[2] - s[2]):5.2f}  "
                         f"dist. vera={math.dist(struct.unpack('>3f', dme.read_bytes(A(CAMERA_VERA), 12)), s):5.2f}")
            except RuntimeError:
                dme.un_hook()
        self.root.after(30, self.tick)

    def salva(self):
        if versione not in VERSIONI:
            messagebox.showerror("Quale versione?", "Apri il gioco (USA o italiano) in Dolphin: il codice viene "
                                                     "salvato per la versione che stai giocando.")
            return
        info = VERSIONI[versione]
        righe = codice_ar(self.effettivi(), self.fov.get())  # camera + FOV di partenza (una volta sola)
        fov = righe_fov()  # frecce del FOV: codice generico, parte da quello che c'è
        regole = info.get("regole") or []
        righe = righe[:1] + [traduci_riga(x, regole) for x in righe[1:]]
        fov = fov[:1] + [traduci_riga(x, regole) for x in fov[1:]]
        salvati, errori = [], []
        for f in info["file"]:
            try:
                salva_in_ini(righe, vecchi=VECCHI_CAMERA, ini=f)
                salva_in_ini(fov, NOME_FOV, vecchi=VECCHI_FOV, ini=f)
                salvati.append(str(f))
            except (OSError, ValueError) as e:
                errori.append(f"{f}: {e}")
        testo = "\n".join(righe)
        self.root.clipboard_clear()
        self.root.clipboard_append(testo)
        (Path(__file__).parent / f"codice_camera_AR_{info['nome']}.txt").write_text(testo + "\n", encoding="utf-8")
        msg = (f"{info['titolo']}\nCodice AR ({len(righe) - 1} righe) salvato in:\n" + "\n".join(salvati) +
               "\n\nCopiato anche negli appunti.")
        if errori:
            messagebox.showwarning("Salvato in parte", msg + "\n\nNON salvato in:\n" + "\n".join(errori))
        else:
            messagebox.showinfo("Salvato", msg)


if __name__ == "__main__":
    root = tk.Tk()
    root_bg = root.cget("bg")
    App(root)
    root.mainloop()
