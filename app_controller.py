"""Controller: il profilo dei tasti che Dolphin usa per Spider-Man 2 (Config/Profiles/GCPad/spiderman 2.ini, che gli INI del
gioco caricano con PadProfile1).

Ogni tasto del GameCube ha una "espressione" con i tasti del pad del PC, es. `D-Pad/Down = `Pad S` | `Thumb L``.
Qui la divido in: tasto BASE (il primo) + tasti EXTRA della mod, che premono più tasti del GameCube insieme:
  costume = freccia giù                  (oggi: tuffo in picchiata del programma camera; nome storico)
  camera  = Z + freccia giù              (codice camera: camera della mod / originale)
  mappa   = Z + Start                    (nel gioco GameCube la mappa si apre così)
  hud     = freccia sinistra + destra    (interruttore del codice HUD: insieme sul d-pad non si possono premere)
Predefiniti: costume L3, camera R3, mappa Select (Back/View), HUD LB. Il tasto extra "costume" (L3 = freccia giù) dal
2026-10-09 fa il TUFFO IN PICCHIATA (programma camera, come L3 su Spider-Man PS4); il costume si cambia con un colpetto
di RB (= Z, codice "$RB (Z) tap to switch skin"). La chiave resta "costume" per non toccare i profili già fatti.

Nomi dei tasti (presi dal codice di Dolphin): XInput "Button A..Y", "Shoulder L/R", "Trigger L/R", "Back", "Start",
"Thumb L/R", "Pad N/S/W/E"; SDL (pad PlayStation/Nintendo) uguali ma "Button S/E/W/N" (per posizione) al posto di A/B/X/Y.
Gli assi hanno gli stessi nomi in XInput e SDL ("Left Y+" = su)."""
import re
from pathlib import Path

import app_core as core

NOME_PROFILO = "spiderman 2"
TASTI_GC = ["Buttons/A", "Buttons/B", "Buttons/X", "Buttons/Y", "Buttons/Z", "Buttons/Start", "Triggers/L", "Triggers/R",
            "D-Pad/Up", "D-Pad/Down", "D-Pad/Left", "D-Pad/Right"]
# extra della mod -> tasti del GameCube che preme insieme
EXTRA = {"costume": ["D-Pad/Down"], "camera": ["Buttons/Z", "D-Pad/Down"], "mappa": ["Buttons/Z", "Buttons/Start"],
         "hud": ["D-Pad/Left", "D-Pad/Right"]}  # sinistra + destra insieme = interruttore dell'HUD (codice HUD nuovo)
EXTRA_DEFAULT = {"costume": "Thumb L", "camera": "Thumb R", "mappa": "Back", "hud": "Shoulder L"}
# predefiniti delle versioni precedenti dell'app (per aggiornare chi non li ha mai cambiati)
EXTRA_VECCHI = [{"costume": "Back", "camera": None, "mappa": None, "hud": None},
                {"costume": "Thumb L", "camera": "Thumb R", "mappa": "Back", "hud": None}]
# indice del tasto nella "standard gamepad" del browser (Gamepad API) -> nome in Dolphin
STANDARD_XINPUT = ["Button A", "Button B", "Button X", "Button Y", "Shoulder L", "Shoulder R", "Trigger L", "Trigger R",
                   "Back", "Start", "Thumb L", "Thumb R", "Pad N", "Pad S", "Pad W", "Pad E"]
STANDARD_SDL = ["Button S", "Button E", "Button W", "Button N"] + STANDARD_XINPUT[4:]
# nome del pad come lo chiama SDL dentro Dolphin (SDL_GetGamepadName): da verificare con un pad vero
# Tasto della tastiera che una versione dell'app aggiungeva a Start (F13) per mettere in pausa il gioco col menu in gioco.
# Non si usa più (Start con RB tenuto = Z + Start apriva la mappa): assicura() lo toglie dai profili dove c'è.
TASTO_PAUSA = "DInput/0/Keyboard Mouse:F13"
# Tasto della tastiera che l'app aggiunge a X (nascosto nella pagina Controller): dopo un viaggio del menu in gioco l'app
# lo preme per chiudere la mappa grande del gioco ("X RIPRENDI"; il menu della mappa legge il controller vero, i tasti
# finti in memoria non bastano). Messo da assicura() prima di ogni partita dal launcher.
TASTO_MAPPA = "DInput/0/Keyboard Mouse:F14"
# F15 su Z e su Start insieme = apre la mappa grande del gioco (come Select): l'app lo preme per il giro fotografico della
# mappa di tutta la città (mappa_citta.py, menu in gioco > Viaggio).
TASTO_APRI_MAPPA = "DInput/0/Keyboard Mouse:F15"
NASCOSTI = {"Buttons/Start": (TASTO_PAUSA, TASTO_APRI_MAPPA), "Buttons/X": (TASTO_MAPPA,), "Buttons/Z": (TASTO_APRI_MAPPA,)}
DELL_APP = {"Buttons/X": (TASTO_MAPPA,), "Buttons/Z": (TASTO_APRI_MAPPA,), "Buttons/Start": (TASTO_APRI_MAPPA,)}  # quelli che mette


def _senza(v, tasti):
    tasti = (tasti,) if isinstance(tasti, str) else tasti
    return " | ".join(x.strip() for x in v.split("|") if x.strip() and x.strip().strip("`").strip() not in tasti)
NOMI_SDL = {"ps5": "DualSense Wireless Controller", "ps4": "PS4 Controller", "switch": "Nintendo Switch Pro Controller"}
# Nomi VERI dei pad in Dolphin 2609 (SDL 3), letti dal suo registro con i pad collegati (2026-10-03): (vendor, product) -> nome.
# Per gli altri pad l'app chiede a Dolphin (dispositivi_dolphin in spidey_app) e si ricorda la risposta (config pad_sdl).
NOMI_NOTI = {(0x054C, 0x0CE6): "DualSense Wireless Controller", (0x054C, 0x0DF2): "DualSense Wireless Controller",
             (0x054C, 0x09CC): "PS4 Controller", (0x054C, 0x05C4): "PS4 Controller"}
PAROLE = {0x054C: ("dualsense", "ps5", "ps4", "playstation", "wireless controller"), 0x057E: ("nintendo", "pro controller", "switch"),
          0x18D1: ("stadia",)}  # per riconoscere il pad giusto tra i dispositivi SDL di Dolphin


def chiave_pad(pad):
    return f"{pad.get('vid', '')}:{pad.get('pid', '')}".lower()


def nome_atteso(pad, cache=None):
    """Nome SDL che Dolphin dà a questo pad, se lo sappiamo (elenco verificato o risposta di Dolphin ricordata)."""
    if not pad or pad.get("tipo") == "xbox":
        return None
    try:
        k = (int(pad.get("vid") or "0", 16), int(pad.get("pid") or "0", 16))
    except ValueError:
        k = (0, 0)
    return (cache or {}).get(chiave_pad(pad)) or NOMI_NOTI.get(k)


def scegli_sdl(dispositivi, pad):
    """Tra i dispositivi di Dolphin ("SDL/0/PS4 Controller", "DInput/0/Wireless Controller"...) quello SDL del pad."""
    sdl = [d.split("/", 2)[2] for d in dispositivi if d.startswith("SDL/") and d.count("/") >= 2]
    sdl = [n for n in sdl if not any(x in n.lower() for x in ("xbox", "xinput"))]
    try:
        vid = int((pad or {}).get("vid") or "0", 16)
    except ValueError:
        vid = 0
    for n in sdl:
        if any(x in n.lower() for x in PAROLE.get(vid, ())):
            return n
    return sdl[0] if sdl else None


def file_profilo(dolphin):
    return Path(dolphin) / "Config" / "Profiles" / "GCPad" / f"{NOME_PROFILO}.ini"


def predefinito():
    return core.contenuti() / "Profiles" / "pc" / f"{NOME_PROFILO}.ini"


def leggi(f):
    """[(chiave, valore)] nell'ordine del file (sezione [Profile])."""
    righe = []
    for r in Path(f).read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in r and not r.lstrip().startswith(("[", ";", "#")):
            k, v = r.split("=", 1)
            righe.append((k.strip(), v.strip()))
    return righe


def _termini(espr):
    return [x.strip().strip("`").strip() for x in espr.split("|") if x.strip()]


def _q(nome):
    return f"`{nome}`" if " " in nome else nome


def analizza(righe):
    """{device, backend, base {tasto GC: nome}, extra {costume/camera/mappa: nome o None}, avanzato}."""
    d = dict(righe)
    for k, tasto in NASCOSTI.items():  # i tasti della tastiera dell'app non sono una scelta di chi gioca: via prima di guardare
        if k in d:
            d[k] = _senza(d[k], tasto)
    dev = d.get("Device", "")
    avanzato = any(re.search(r"[&!()@^:]", d.get(k, "")) for k in TASTI_GC)  # espressioni fatte a mano in Dolphin
    base, resto = {}, {}
    for k in TASTI_GC:
        t = _termini(d.get(k, ""))
        base[k] = t[0] if t else None
        resto[k] = set(t[1:])
    z, giu, start = resto["Buttons/Z"], resto["D-Pad/Down"], resto["Buttons/Start"]
    camera = sorted(z & giu)
    mappa = sorted((z & start) - set(camera))
    costume = sorted(giu - set(camera))
    hud = sorted(resto["D-Pad/Left"] & resto["D-Pad/Right"])
    extra = {"costume": costume[0] if costume else None, "camera": camera[0] if camera else None,
             "mappa": mappa[0] if mappa else None, "hud": hud[0] if hud else None}
    backend = "xinput" if dev.startswith("XInput/") else "sdl" if dev.startswith("SDL/") else "altro"
    return {"device": dev, "backend": backend, "base": base, "extra": extra, "avanzato": bool(avanzato)}


def componi(righe, device, base, extra):
    """Riscrive le righe dei tasti GC (le altre - stick, calibrazione - restano com'erano)."""
    termini = {k: ([base[k]] if base.get(k) else []) for k in TASTI_GC}
    for cosa, gc in EXTRA.items():
        nome = extra.get(cosa)
        if nome:
            for k in gc:
                if nome not in termini[k]:
                    termini[k].append(nome)
    nuovo = {k: " | ".join(_q(x) for x in v) for k, v in termini.items()}
    for k, tasti in DELL_APP.items():  # tasti della tastiera dell'app (TASTO_MAPPA, TASTO_APRI_MAPPA)
        nuovo[k] = " | ".join(x for x in (nuovo[k], *(_q(t) for t in tasti)) if x)
    if base.get("Triggers/L", "").startswith("Trigger"):
        nuovo["Triggers/L-Analog"] = _q(base["Triggers/L"])
    if base.get("Triggers/R", "").startswith("Trigger"):
        nuovo["Triggers/R-Analog"] = _q(base["Triggers/R"])
    out, fatti = [], set()
    for k, v in righe:
        if k == "Device":
            out.append((k, device))
        elif k in nuovo:
            if nuovo[k]:
                out.append((k, nuovo[k]))
            fatti.add(k)
        else:
            out.append((k, v))
    out += [(k, v) for k, v in nuovo.items() if k not in fatti and v]
    return out


def scrivi(f, righe):
    f = Path(f)
    f.parent.mkdir(parents=True, exist_ok=True)
    core.backup_file(f, "Config")
    testo = "[Profile]\n" + "".join(f"{k} = {v}\n" for k, v in righe)
    if f.exists():
        f.unlink()  # potrebbe essere un collegamento: mai scrivere dentro
    f.write_text(testo, encoding="utf-8")


def _segno(espr):
    """'+' o '-' dell'asse in un'espressione del profilo (`Right Y+`, `Axis 1-`), None se non è un asse semplice."""
    m = re.fullmatch(r"`?[^`|&!()]*?([+-])`?", (espr or "").strip())
    return m.group(1) if m else None


INVERTI = {"y": ("C-Stick/Up", "C-Stick/Down", "Main Stick/Up"), "x": ("C-Stick/Left", "C-Stick/Right", "Main Stick/Left")}


def inversione(righe):
    """Camera (levetta destra = C-Stick) invertita? {"y": bool, "x": bool}: invertita = il segno della levetta destra è
    opposto a quello della sinistra nella stessa direzione (vale per XInput `Y+`, SDL e Android `Axis 1-`). None = non si
    capisce (espressioni fatte a mano)."""
    d = dict(righe)
    out = {}
    for asse, (a, _b, rif) in INVERTI.items():
        c, s = _segno(d.get(a)), _segno(d.get(rif))
        out[asse] = None if not c or not s else c != s
    return out


def inverti(righe, scelta):
    """Righe del profilo con la camera invertita come in scelta {"y": bool, "x": bool} (scambia su/giù o sinistra/destra
    della levetta destra solo se serve). Vale per tutte le camere, anche quella del gioco: il gioco legge la levetta così."""
    d, ora, scambi = dict(righe), inversione(righe), {}
    for asse, (a, b, _rif) in INVERTI.items():
        if asse in (scelta or {}) and ora.get(asse) is not None and bool(scelta[asse]) != ora[asse] and a in d and b in d:
            scambi[a], scambi[b] = d[b], d[a]
    return [(k, scambi.get(k, v)) for k, v in righe], bool(scambi)


def applica_inversione(dolphin, scelta):
    """Mette nel profilo di Dolphin l'inversione della camera scelta nell'app (dopo Ripristina, profilo automatico, avvio)."""
    if not dolphin or not scelta:
        return False
    f = file_profilo(dolphin)
    if not f.is_file():
        return False
    righe, cambiato = inverti(leggi(f), scelta)
    if cambiato:
        scrivi(f, righe)
    return cambiato


def converti_backend(info, verso):
    """Da XInput a SDL o viceversa: stessi tasti per posizione (A<->S, B<->E, X<->W, Y<->N)."""
    da, a = (STANDARD_XINPUT, STANDARD_SDL) if verso == "sdl" else (STANDARD_SDL, STANDARD_XINPUT)
    m = dict(zip(da[:4], a[:4]))
    base = {k: m.get(v, v) if v else v for k, v in info["base"].items()}
    extra = {k: m.get(v, v) if v else v for k, v in info["extra"].items()}
    return base, extra


VERSIONE_PROFILO = 2  # 1 = L3/R3/Select, 2 = + LB per l'HUD


def aggiorna_vecchio(dolphin, conf=None):
    """Il profilo che l'app metteva prima diventa quello nuovo (L3 costume, R3 camera, Select mappa, LB HUD).
    Solo se è proprio un vecchio predefinito (un profilo cambiato a mano resta) e una volta sola (conf
    "profilo_v": se poi togli un tasto extra non te lo rimetto)."""
    if conf is not None and conf.get("profilo_v", 0) >= VERSIONE_PROFILO:
        return False
    fatto = _aggiorna_vecchio(dolphin)
    if conf is not None:
        conf["profilo_v"] = VERSIONE_PROFILO
        core.scrivi_config(conf)
    return fatto


def _aggiorna_vecchio(dolphin):
    f = file_profilo(dolphin)
    if not f.is_file():
        return False
    righe = leggi(f)
    info = analizza(righe)
    if info["avanzato"] or info["extra"] not in EXTRA_VECCHI:
        return False
    vecchio = {"Buttons/A": "Button A", "Buttons/B": "Button X", "Buttons/X": "Button B", "Buttons/Y": "Button Y",
               "Buttons/Z": "Shoulder R", "Buttons/Start": "Start", "D-Pad/Down": "Pad S"}
    if any(info["base"].get(k) != v for k, v in vecchio.items()) or info["device"] != "XInput/0/Gamepad":
        return False
    scrivi(f, componi(righe, info["device"], info["base"], dict(EXTRA_DEFAULT)))
    return True


def stato(dolphin, versioni_ini):
    """Profilo attuale + controlli: esiste? gli INI del gioco lo usano? porta 1 = controller standard?"""
    f = file_profilo(dolphin) if dolphin else None
    out = {"profilo": None, "esiste": bool(f and f.is_file()), "ini_senza": [], "porta_ok": True}
    if not dolphin:
        return out
    if out["esiste"]:
        out["profilo"] = analizza(leggi(f))
    for gid, ini in versioni_ini.items():
        if not ini.is_file():
            continue
        testo = ini.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"(?im)^\s*PadProfile1\s*=\s*" + re.escape(NOME_PROFILO) + r"\s*$", testo):
            out["ini_senza"].append(gid)
    dini = Path(dolphin) / "Config" / "Dolphin.ini"
    if dini.is_file():
        m = re.search(r"(?im)^\s*SIDevice0\s*=\s*(\d+)", dini.read_text(encoding="utf-8", errors="replace"))
        out["porta_ok"] = not m or m.group(1) in ("6", "12")  # 6 = controller standard, 12 = adattatore WiiU
    return out


def metti_nei_giochi(ini):
    """Aggiunge [Controls] PadType0 = 6 / PadProfile1 = spiderman 2 all'INI di una versione."""
    core.backup_file(ini, "GameSettings")
    core.scrivi_ini_valori(ini, {("Controls", "PadType0"): "6", ("Controls", "PadProfile1"): NOME_PROFILO})


def pad_collegati():
    """Controller collegati, senza dover premere niente (il browser li mostra solo dopo il primo tasto):
    XInput (pad Xbox e compatibili) con XInputGetState, gli altri (PlayStation, Nintendo...) con il joystick di Windows
    (winmm), che dà anche produttore/prodotto: 045E Microsoft, 054C Sony, 057E Nintendo."""
    import ctypes
    from ctypes import wintypes
    out = []
    try:
        xi = ctypes.windll.xinput1_4
    except OSError:
        try:
            xi = ctypes.windll.xinput9_1_0
        except OSError:
            xi = None
    if xi:
        buf = ctypes.create_string_buffer(16)
        for i in range(4):
            if xi.XInputGetState(i, buf) == 0:
                out.append({"tipo": "xbox", "nome": "Pad Xbox" if i == 0 else f"Pad Xbox {i + 1}", "xinput": True})

    class JOYCAPSW(ctypes.Structure):
        _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("szPname", wintypes.WCHAR * 32), ("wXmin", wintypes.UINT),
                    ("wXmax", wintypes.UINT), ("wYmin", wintypes.UINT), ("wYmax", wintypes.UINT), ("wZmin", wintypes.UINT),
                    ("wZmax", wintypes.UINT), ("wNumButtons", wintypes.UINT), ("wPeriodMin", wintypes.UINT),
                    ("wPeriodMax", wintypes.UINT), ("wRmin", wintypes.UINT), ("wRmax", wintypes.UINT), ("wUmin", wintypes.UINT),
                    ("wUmax", wintypes.UINT), ("wVmin", wintypes.UINT), ("wVmax", wintypes.UINT), ("wCaps", wintypes.UINT),
                    ("wMaxAxes", wintypes.UINT), ("wNumAxes", wintypes.UINT), ("wMaxButtons", wintypes.UINT),
                    ("szRegKey", wintypes.WCHAR * 32), ("szOEMVxD", wintypes.WCHAR * 260)]

    class JOYINFOEX(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD)] + [(n, wintypes.DWORD) for n in
                    ("x", "y", "z", "r", "u", "v", "b", "nb", "pov", "r1", "r2")]
    try:
        wm = ctypes.windll.winmm
        for i in range(min(wm.joyGetNumDevs(), 16)):
            info = JOYINFOEX(dwSize=ctypes.sizeof(JOYINFOEX), dwFlags=0xFF)
            if wm.joyGetPosEx(i, ctypes.byref(info)) != 0:
                continue
            caps = JOYCAPSW()
            if wm.joyGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) != 0:
                continue
            vid = caps.wMid
            if vid == 0x045E:
                continue  # Xbox: già contato con XInput
            tipo = "ps" if vid == 0x054C else "switch" if vid == 0x057E else "altro"
            sdl = "ps5" if vid == 0x054C and caps.wPid in (0x0CE6, 0x0DF2) else "ps4" if vid == 0x054C else "switch" if tipo == "switch" else None
            out.append({"tipo": tipo, "nome": caps.szPname or "Controller", "xinput": False, "vid": f"{vid:04x}",
                        "pid": f"{caps.wPid:04x}", "sdl": sdl})
    except Exception:  # noqa: BLE001 - è solo un controllo
        pass
    try:  # pad che il joystick di Windows non vede (es. Stadia): li cerco come dispositivi HID
        visti = {(x.get("vid"), x.get("pid")) for x in out}
        for h in pad_hid():
            v, p = f"{h['vid']:04x}", f"{h['pid']:04x}"
            if (v, p) in visti:  # già visto dal joystick di Windows, che però lo chiama "Driver joystick Microsoft PC"
                for x in out:
                    if (x.get("vid"), x.get("pid")) == (v, p) and x["nome"].lower().startswith("driver"):
                        x["nome"] = h["nome"]
                continue
            tipo = "ps" if h["vid"] == 0x054C else "switch" if h["vid"] == 0x057E else "altro"
            out.append({"tipo": tipo, "nome": h["nome"], "xinput": False, "vid": v, "pid": p,
                        "sdl": "ps5" if tipo == "ps" and h["pid"] in (0x0CE6, 0x0DF2) else "ps4" if tipo == "ps" else "switch" if tipo == "switch" else None})
            visti.add((v, p))
    except Exception:  # noqa: BLE001
        pass
    return out


def verdetto(profilo, pad, cache=None):
    """Il profilo dei tasti va bene per i controller collegati? -> (esito, pad usato):
    "ok", "nessuno" (nessun controller), "sdl" (pad PlayStation/Nintendo ma profilo per Xbox), "xinput" (pad Xbox ma
    profilo SDL), "altro" (controller sconosciuto), "manca" (nessun profilo)."""
    if not profilo:
        return "manca", None
    if not pad:
        return "nessuno", None
    xbox = next((p for p in pad if p["tipo"] == "xbox"), None)
    altro = next((p for p in pad if p["tipo"] != "xbox"), None)
    if profilo["backend"] == "xinput":
        if xbox:
            return "ok", xbox
        return "sdl", altro  # qualsiasi pad non Xbox: con SDL Dolphin lo legge (PlayStation, Nintendo, Stadia, generici)
    if profilo["backend"] == "sdl":
        if altro:  # pad non Xbox col profilo SDL: va bene solo se il nome del dispositivo è quello giusto
            atteso = nome_atteso(altro, cache)
            if atteso and (profilo.get("device") or "").split("/", 2)[-1] != atteso:
                return "nome", altro
            return ("ok", altro) if atteso or altro["tipo"] in ("ps", "switch") else ("altro", altro)
        return ("xinput", xbox) if xbox else ("altro", altro)
    return "altro", pad[0]


def assicura(dolphin, gid):
    """Prima di giocare: il profilo dei tasti c'è e l'INI della versione lo usa (anche giocando senza mod/codici)."""
    f = file_profilo(dolphin)
    if not f.is_file():
        f.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copyfile(predefinito(), f)
    togli_tasto_pausa(f)
    metti_tasto_mappa(f)
    if not gid:
        return
    ini = Path(dolphin) / "GameSettings" / f"{gid}.ini"
    testo = ini.read_text(encoding="utf-8", errors="replace") if ini.is_file() else ""
    if not re.search(r"(?im)^\s*PadProfile1\s*=\s*" + re.escape(NOME_PROFILO) + r"\s*$", testo):
        ini.parent.mkdir(parents=True, exist_ok=True)
        metti_nei_giochi(ini)


def togli_tasto_pausa(f):
    """Toglie F13 da Start (vedi TASTO_PAUSA), senza toccare il resto. True = c'era."""
    righe = leggi(f)
    if not any(k == "Buttons/Start" and TASTO_PAUSA in v for k, v in righe):
        return False
    pulito = lambda v: " | ".join(x.strip() for x in v.split("|") if x.strip() and x.strip().strip("`").strip() != TASTO_PAUSA)
    scrivi(f, [(k, pulito(v)) if k == "Buttons/Start" else (k, v) for k, v in righe])
    return True


def metti_tasto_mappa(f):
    """Aggiunge i tasti della tastiera dell'app (F14 su X, F15 su Z e Start: vedi DELL_APP), senza toccare il resto.
    True = aggiunto qualcosa adesso."""
    righe = leggi(f)
    cambiato = False
    for chiave, tasti in DELL_APP.items():
        for t in tasti:
            if any(k == chiave and t in v for k, v in righe):
                continue
            q = _q(t)
            if any(k == chiave for k, v in righe):
                righe = [(k, " | ".join(x for x in (v.strip(), q) if x)) if k == chiave else (k, v) for k, v in righe]
            else:
                righe = righe + [(chiave, q)]
            cambiato = True
    if cambiato:
        scrivi(f, righe)
    return cambiato


class PadWinmm:
    """Pad che non sono XInput (PlayStation, Switch Pro, Stadia, generici) letti col joystick di Windows (winmm), per il
    menu in gioco: i tasti diventano quelli di un pad Xbox (stessi bit di XInput), così LB + RB = L1 + R1 e il resto
    funziona uguale. Ordine dei tasti per pad (indice da 0, dal database dei controller di SDL, "bN"); la croce è il
    POV, lo stick sinistro gli assi X/Y. Con un pad Xbox collegato si leggono solo i pad di marche note (gli altri
    potrebbero essere lo stesso pad Xbox visto due volte, con un ordine dei tasti diverso)."""
    BIT = {"a": 0x1000, "b": 0x2000, "x": 0x4000, "y": 0x8000, "lb": 0x0100, "rb": 0x0200, "lt": 0x10000, "rt": 0x20000,
           "back": 0x0020, "start": 0x0010, "ls": 0x0040, "rs": 0x0080}
    MAPPE = {0x054C: {"x": 0, "a": 1, "b": 2, "y": 3, "lb": 4, "rb": 5, "lt": 6, "rt": 7, "back": 8, "start": 9, "ls": 10, "rs": 11},  # PS4 / PS5
             0x057E: {"a": 0, "b": 1, "x": 2, "y": 3, "lb": 4, "rb": 5, "lt": 6, "rt": 7, "back": 8, "start": 9, "ls": 10, "rs": 11},  # Switch Pro (per posizione)
             0x18D1: {"a": 0, "b": 1, "x": 2, "y": 3, "lb": 4, "rb": 5, "ls": 6, "rs": 7, "back": 8, "start": 9, "rt": 11, "lt": 12}}  # Stadia (DirectInput; via HID vedi HID_MAPPE)
    GENERICA = {"a": 0, "b": 1, "x": 2, "y": 3, "lb": 4, "rb": 5, "lt": 6, "rt": 7, "back": 8, "start": 9, "ls": 10, "rs": 11}

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class JOYINFOEX(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD)] + [(n, wintypes.DWORD) for n in
                        ("x", "y", "z", "r", "u", "v", "b", "nb", "pov", "r1", "r2")]

        class JOYCAPSW(ctypes.Structure):
            _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("szPname", wintypes.WCHAR * 32)] +                        [(n, wintypes.UINT) for n in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax", "nb", "pmin", "pmax",
                                                     "rmin", "rmax", "umin", "umax", "vmin", "vmax", "caps", "maxax", "nax", "maxb")] +                        [("szRegKey", wintypes.WCHAR * 32), ("szOEMVxD", wintypes.WCHAR * 260)]
        self._ct, self._JI, self._JC = ctypes, JOYINFOEX, JOYCAPSW
        try:
            self._wm = ctypes.windll.winmm
        except OSError:
            self._wm = None
        self._pad, self._quando = [], 0.0
        self.destro = (0.0, 0.0)  # stick destro (-1..1), letto insieme ai tasti: per girare/zoomare lo Spidey del menu
        self.sinistro = (0.0, 0.0)  # stick sinistro (-1..1, su = negativo): la mappa della città si muove fluida
        self.dispositivi = []  # un pad per voce, tasti SENZA lo stick (pagina Controller dell'app: vedi LettorePad)

    def _cerca(self, con_xbox):
        """Quali joystick leggere (ogni 2 s: si possono collegare mentre giochi). Microsoft = già XInput."""
        out = []
        for i in range(min(self._wm.joyGetNumDevs(), 16)):
            caps = self._JC()
            if self._wm.joyGetDevCapsW(i, self._ct.byref(caps), self._ct.sizeof(caps)) != 0 or caps.wMid == 0x045E:
                continue
            if con_xbox and caps.wMid not in self.MAPPE:
                continue
            info = self._JI(dwSize=self._ct.sizeof(self._JI), dwFlags=0xFF)
            if self._wm.joyGetPosEx(i, self._ct.byref(info)) == 0:
                out.append((i, self.MAPPE.get(caps.wMid, self.GENERICA), caps.wMid, caps.wPid, caps.szPname))
        self._pad = out

    def bottoni(self, con_xbox=False):
        import time
        if not self._wm:
            return 0
        if time.time() - self._quando > 2:
            self._quando = time.time()
            self._cerca(con_xbox)
        b, destro, sinistro, disp = 0, (0.0, 0.0), (0.0, 0.0), []
        for i, mappa, vid, pid, nome in self._pad:
            info = self._JI(dwSize=self._ct.sizeof(self._JI), dwFlags=0xFF)
            if self._wm.joyGetPosEx(i, self._ct.byref(info)) != 0:
                continue
            b_prima = b
            dx, dy = info.z / 32767.5 - 1, info.r / 32767.5 - 1  # stick destro: Z / Rz (PlayStation e quasi tutti)
            if (info.z or info.r) and abs(dx) + abs(dy) > abs(destro[0]) + abs(destro[1]):  # 0 e 0 = pad senza quegli assi
                destro = (dx, dy)
            assi = bool(info.x or info.y)  # 0 e 0 = pad senza assi X/Y (se no su+sinistra sempre premuti: il menu scorreva da solo)
            sx, sy = info.x / 32767.5 - 1, info.y / 32767.5 - 1
            if assi and abs(sx) + abs(sy) > abs(sinistro[0]) + abs(sinistro[1]):
                sinistro = (sx, sy)
            for nome, n in mappa.items():
                if info.b & (1 << n):
                    b |= self.BIT[nome]
            pov = info.pov
            if pov != 0xFFFF and pov <= 36000:  # croce: centesimi di grado, 0 = su
                b |= (0x0001 if pov >= 31500 or pov <= 4500 else 0) | (0x0008 if 4500 <= pov <= 13500 else 0) |                      (0x0002 if 13500 <= pov <= 22500 else 0) | (0x0004 if 22500 <= pov <= 31500 else 0)
            tasti = 0  # questo pad da solo, senza lo stick (per la prova dei tasti)
            for nome_t, n in mappa.items():
                if info.b & (1 << n):
                    tasti |= self.BIT[nome_t]
            tasti |= (b & ~b_prima) & 0x000F
            if assi:
                b |= (0x0001 if info.y < 12000 else 0) | (0x0002 if info.y > 53500 else 0) |                  (0x0004 if info.x < 12000 else 0) | (0x0008 if info.x > 53500 else 0)  # stick sinistro (0-65535)
            disp.append({"id": f"w{i}", "vid": vid, "pid": pid, "nome": nome, "b": tasti,
                         "sx": (info.x / 32767.5 - 1) if assi else 0.0, "sy": (info.y / 32767.5 - 1) if assi else 0.0,
                         "dx": (info.z / 32767.5 - 1) if info.z or info.r else 0.0, "dy": (info.r / 32767.5 - 1) if info.z or info.r else 0.0})
        self.destro, self.sinistro, self.dispositivi = destro, sinistro, disp
        return b


# ---------------------------------------------------------------- pad letti come dispositivi HID (Stadia, generici...)
_HID = []


def _hid_api():
    """Funzioni di Windows per i dispositivi HID (hid.dll, setupapi.dll, kernel32) con i tipi giusti a 64 bit.
    Preparate UNA volta: ridefinirle cambierebbe i tipi sotto i piedi ai fili che stanno già leggendo."""
    if not _HID:
        _HID.append(_hid_api_crea())
    return _HID[0]


def _hid_api_crea():
    import ctypes
    from ctypes import wintypes
    hid, sa, k32 = ctypes.windll.hid, ctypes.windll.setupapi, ctypes.windll.kernel32

    class GUID(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    class SPDID(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("guid", GUID), ("flags", wintypes.DWORD), ("res", ctypes.c_void_p)]

    class ATTR(ctypes.Structure):
        _fields_ = [("Size", wintypes.ULONG), ("VendorID", wintypes.USHORT), ("ProductID", wintypes.USHORT), ("Version", wintypes.USHORT)]

    class CAPS(ctypes.Structure):
        _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT), ("InLen", wintypes.USHORT), ("OutLen", wintypes.USHORT),
                    ("FeatLen", wintypes.USHORT), ("Reserved", wintypes.USHORT * 17)] + [(n, wintypes.USHORT) for n in (
                    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j")]

    class VALCAPS(ctypes.Structure):  # HIDP_VALUE_CAPS
        _fields_ = [("UsagePage", wintypes.USHORT), ("ReportID", ctypes.c_ubyte), ("IsAlias", ctypes.c_ubyte), ("BitField", wintypes.USHORT),
                    ("LinkCollection", wintypes.USHORT), ("LinkUsage", wintypes.USHORT), ("LinkUsagePage", wintypes.USHORT),
                    ("IsRange", ctypes.c_ubyte), ("IsStringRange", ctypes.c_ubyte), ("IsDesignatorRange", ctypes.c_ubyte), ("IsAbsolute", ctypes.c_ubyte),
                    ("HasNull", ctypes.c_ubyte), ("Reserved", ctypes.c_ubyte), ("BitSize", wintypes.USHORT), ("ReportCount", wintypes.USHORT),
                    ("Reserved2", wintypes.USHORT * 5), ("UnitsExp", wintypes.ULONG), ("Units", wintypes.ULONG),
                    ("LogicalMin", ctypes.c_long), ("LogicalMax", ctypes.c_long), ("PhysicalMin", ctypes.c_long), ("PhysicalMax", ctypes.c_long),
                    ("UsageMin", wintypes.USHORT), ("UsageMax", wintypes.USHORT), ("StrMin", wintypes.USHORT), ("StrMax", wintypes.USHORT),
                    ("DesMin", wintypes.USHORT), ("DesMax", wintypes.USHORT), ("DataMin", wintypes.USHORT), ("DataMax", wintypes.USHORT)]
    sa.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    sa.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), ctypes.c_wchar_p, ctypes.c_void_p, wintypes.DWORD]
    sa.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD, ctypes.POINTER(SPDID)]
    sa.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(SPDID), ctypes.c_void_p, wintypes.DWORD,
                                                   ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    sa.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    k32.CreateFileW.restype = ctypes.c_void_p
    k32.CreateFileW.argtypes = [ctypes.c_wchar_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    k32.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
    hid.HidD_GetAttributes.argtypes = [ctypes.c_void_p, ctypes.POINTER(ATTR)]
    hid.HidD_GetProductString.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.ULONG]
    hid.HidD_GetPreparsedData.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(CAPS)]
    hid.HidP_GetValueCaps.argtypes = [ctypes.c_int, ctypes.POINTER(VALCAPS), ctypes.POINTER(wintypes.USHORT), ctypes.c_void_p]
    hid.HidP_GetUsages.argtypes = [ctypes.c_int, wintypes.USHORT, wintypes.USHORT, ctypes.POINTER(wintypes.USHORT),
                                   ctypes.POINTER(wintypes.ULONG), ctypes.c_void_p, ctypes.c_void_p, wintypes.ULONG]
    hid.HidP_GetUsages.restype = ctypes.c_long
    hid.HidP_GetUsageValue.argtypes = [ctypes.c_int, wintypes.USHORT, wintypes.USHORT, wintypes.USHORT, ctypes.POINTER(wintypes.ULONG),
                                       ctypes.c_void_p, ctypes.c_void_p, wintypes.ULONG]
    hid.HidP_GetUsageValue.restype = ctypes.c_long
    g = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(g))
    return ctypes, wintypes, hid, sa, k32, g, SPDID, ATTR, CAPS, VALCAPS


HIDP_OK = 0x00110000  # HIDP_STATUS_SUCCESS


def pad_hid():
    """Gamepad/joystick HID collegati (non Microsoft: quelli sono XInput): [{path, vid, pid, nome}]."""
    out = []
    try:
        ctypes, wintypes, hid, sa, k32, g, SPDID, ATTR, CAPS, _ = _hid_api()
    except Exception:  # noqa: BLE001
        return out
    h = sa.SetupDiGetClassDevsW(ctypes.byref(g), None, None, 0x12)  # DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    if not h or h == ctypes.c_void_p(-1).value:
        return out
    try:
        i = 0
        while True:
            d = SPDID(cbSize=ctypes.sizeof(SPDID))
            if not sa.SetupDiEnumDeviceInterfaces(h, None, ctypes.byref(g), i, ctypes.byref(d)):
                break
            i += 1
            n = wintypes.DWORD()
            sa.SetupDiGetDeviceInterfaceDetailW(h, ctypes.byref(d), None, 0, ctypes.byref(n), None)
            buf = ctypes.create_string_buffer(n.value)
            ctypes.c_uint32.from_buffer(buf).value = 8  # cbSize di SP_DEVICE_INTERFACE_DETAIL_DATA_W a 64 bit
            if not sa.SetupDiGetDeviceInterfaceDetailW(h, ctypes.byref(d), buf, n, None, None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            f = k32.CreateFileW(path, 0, 3, None, 3, 0, None)  # solo attributi: niente accesso, condiviso
            if not f or f == ctypes.c_void_p(-1).value:
                continue
            try:
                a = ATTR(Size=ctypes.sizeof(ATTR))
                pp = ctypes.c_void_p()
                if not hid.HidD_GetAttributes(f, ctypes.byref(a)) or a.VendorID == 0x045E or not hid.HidD_GetPreparsedData(f, ctypes.byref(pp)):
                    continue
                c = CAPS()
                hid.HidP_GetCaps(pp, ctypes.byref(c))
                hid.HidD_FreePreparsedData(pp)
                if c.UsagePage != 1 or c.Usage not in (4, 5):  # Generic Desktop: Joystick / Gamepad
                    continue
                nb = ctypes.create_unicode_buffer(128)
                hid.HidD_GetProductString(f, nb, ctypes.sizeof(nb))
                out.append({"path": path, "vid": a.VendorID, "pid": a.ProductID, "nome": nb.value.strip() or "Controller"})
            finally:
                k32.CloseHandle(f)
    finally:
        sa.SetupDiDestroyDeviceInfoList(h)
    return out


# Pad letti come HID: i numeri dei tasti sono le "usage" HID (meno 1), che NON sempre coincidono con l'ordine DirectInput
# del database di SDL. Stadia: ordine "standard Android" (A=1, B=2, X=4, Y=5, LB=7, RB=8, LT=9, RT=10, Select=11,
# Start=12, L3=14, R3=15), verificato con le pressioni di John (LB=7, RB=8, A=1, Start=12).
HID_MAPPE = {0x18D1: {"a": 0, "b": 1, "x": 3, "y": 4, "lb": 6, "rb": 7, "lt": 8, "rt": 9, "back": 10, "start": 11, "ls": 13, "rs": 14}}


class PadHid:
    """Legge i gamepad HID (Stadia, generici...) con un filo per pad: i report vengono tradotti nei bit di un pad Xbox
    (mappe di PadWinmm: tasto HID n = "b(n-1)" del database di SDL)."""

    def __init__(self):
        import threading
        self._stato, self._fili, self._quando, self._lock = {}, {}, 0.0, threading.Lock()
        self._destro = {}  # stick destro per pad (-1..1)
        self._sinistro = {}  # stick sinistro per pad (-1..1)
        self._tasti, self._info = {}, {}  # per pad: tasti senza lo stick e {vid, pid, nome} (pagina Controller)

    def _leggi(self, info, mappa):
        """Filo di un pad: legge i report finché il pad c'è (ReadFile bloccante, condiviso con Dolphin e Windows)."""
        f = pp = None
        try:
            ctypes, wintypes, hid, sa, k32, g, SPDID, ATTR, CAPS, VALCAPS = _hid_api()
            f = k32.CreateFileW(info["path"], 0xC0000000, 3, None, 3, 0, None)  # lettura+scrittura, condiviso
            if not f or f == ctypes.c_void_p(-1).value:
                f = k32.CreateFileW(info["path"], 0x80000000, 3, None, 3, 0, None)
            if not f or f == ctypes.c_void_p(-1).value:
                return
            pp = ctypes.c_void_p()
            hid.HidD_GetPreparsedData(f, ctypes.byref(pp))
            c = CAPS()
            hid.HidP_GetCaps(pp, ctypes.byref(c))
            n = wintypes.USHORT(64)
            vc = (VALCAPS * 64)()
            hid.HidP_GetValueCaps(0, vc, ctypes.byref(n), pp)
            lim, grilletti = {}, []
            for v in vc[:n.value]:
                if v.UsagePage == 1:
                    for u in (range(v.UsageMin, v.UsageMax + 1) if v.IsRange else (v.UsageMin,)):
                        lim[u] = (v.LogicalMin, v.LogicalMax if v.LogicalMax > v.LogicalMin else (1 << v.BitSize) - 1)
                elif v.UsagePage == 2 and v.UsageMin in (0xC4, 0xC5):  # grilletti analogici come pedali (Stadia):
                    hi = v.LogicalMax if v.LogicalMax > v.LogicalMin else (1 << v.BitSize) - 1  # freno = LT, acceleratore = RT
                    grilletti.append((v.UsageMin, v.LogicalMin, hi, PadWinmm.BIT["lt" if v.UsageMin == 0xC5 else "rt"]))
            buf = ctypes.create_string_buffer(c.InLen)
            letti = wintypes.DWORD()
            usages = (wintypes.USHORT * 64)()
            val = wintypes.ULONG()
            while info["path"] in self._fili:
                if not k32.ReadFile(f, buf, c.InLen, ctypes.byref(letti), None):
                    break
                b = 0
                cnt = wintypes.ULONG(64)
                if hid.HidP_GetUsages(0, 9, 0, usages, ctypes.byref(cnt), pp, buf, letti.value) == HIDP_OK:
                    premuti = {usages[i] - 1 for i in range(cnt.value)}
                    for nome, k in mappa.items():
                        if k in premuti:
                            b |= PadWinmm.BIT[nome]
                if 0x39 in lim and hid.HidP_GetUsageValue(0, 1, 0, 0x39, ctypes.byref(val), pp, buf, letti.value) == HIDP_OK:
                    d = val.value - lim[0x39][0]  # croce: 0 = su, poi in senso orario; fuori = niente
                    if 0 <= d <= 7:
                        b |= (0x0001 if d in (7, 0, 1) else 0) | (0x0008 if d in (1, 2, 3) else 0) | \
                             (0x0002 if d in (3, 4, 5) else 0) | (0x0004 if d in (5, 6, 7) else 0)
                sin, bs = [0.0, 0.0], 0
                for k, (u, (meno, piu)) in enumerate(((0x30, (0x0004, 0x0008)), (0x31, (0x0001, 0x0002)))):  # stick sinistro X / Y
                    if u in lim and hid.HidP_GetUsageValue(0, 1, 0, u, ctypes.byref(val), pp, buf, letti.value) == HIDP_OK:
                        lo, hi = lim[u]
                        x = (val.value - lo) / max(1, hi - lo)
                        sin[k] = 2 * x - 1
                        bs |= meno if x < 0.2 else piu if x > 0.8 else 0
                self._sinistro[info["path"]] = tuple(sin)
                if 0x32 in lim and 0x35 in lim:  # stick destro (Z / Rz): per girare/zoomare lo Spidey del menu
                    xy = []
                    for u in (0x32, 0x35):
                        lo, hi = lim[u]
                        xy.append(2 * (val.value - lo) / max(1, hi - lo) - 1
                                  if hid.HidP_GetUsageValue(0, 1, 0, u, ctypes.byref(val), pp, buf, letti.value) == HIDP_OK else 0.0)
                    self._destro[info["path"]] = tuple(xy)
                for u, lo, hi, bit in grilletti:  # premuto oltre il 55% (come i grilletti XInput nel menu)
                    if hid.HidP_GetUsageValue(0, 2, 0, u, ctypes.byref(val), pp, buf, letti.value) == HIDP_OK and \
                            (val.value - lo) / max(1, hi - lo) > 0.55:
                        b |= bit
                with self._lock:
                    self._stato[info["path"]] = b | bs
                    self._tasti[info["path"]] = b
        except Exception:  # noqa: BLE001 - un pad che sparisce non deve fermare niente
            pass
        finally:
            try:  # anche dopo un errore (prima restavano aperti)
                if pp:
                    hid.HidD_FreePreparsedData(pp)
                if f and f != ctypes.c_void_p(-1).value:
                    k32.CloseHandle(f)
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                self._stato.pop(info["path"], None)
                self._destro.pop(info["path"], None)
                self._sinistro.pop(info["path"], None)
                self._tasti.pop(info["path"], None)
                self._info.pop(info["path"], None)
            self._fili.pop(info["path"], None)

    def bottoni(self, con_xbox=False, salta=(0x054C, 0x057E)):
        """salta = marche lette già col joystick di Windows (PadWinmm), per non leggerle due volte."""
        import threading
        import time
        if time.time() - self._quando > 3:
            self._quando = time.time()
            for p in pad_hid():
                if p["vid"] in salta or (con_xbox and p["vid"] not in PadWinmm.MAPPE) or p["path"] in self._fili:
                    continue
                self._fili[p["path"]] = True
                with self._lock:
                    self._info[p["path"]] = {"vid": p["vid"], "pid": p["pid"], "nome": p["nome"]}
                mappa = HID_MAPPE.get(p["vid"]) or PadWinmm.MAPPE.get(p["vid"], PadWinmm.GENERICA)
                threading.Thread(target=self._leggi, args=(p, mappa), daemon=True).start()
        with self._lock:
            b = 0
            for v in self._stato.values():
                b |= v
            return b

    @property
    def dispositivi(self):
        """Un pad per voce come PadWinmm.dispositivi (solo quelli che hanno già mandato un report)."""
        with self._lock:
            out = []
            for k, b in self._tasti.items():
                i, sx, dx = self._info.get(k, {}), self._sinistro.get(k, (0.0, 0.0)), self._destro.get(k, (0.0, 0.0))
                out.append({"id": "h" + k[-12:], "vid": i.get("vid"), "pid": i.get("pid"), "nome": i.get("nome") or "Controller",
                            "b": b, "sx": sx[0], "sy": sx[1], "dx": dx[0], "dy": dx[1]})
            return out

    @property
    def destro(self):
        with self._lock:
            return max(self._destro.values(), key=lambda v: abs(v[0]) + abs(v[1]), default=(0.0, 0.0))

    @property
    def sinistro(self):
        with self._lock:
            return max(self._sinistro.values(), key=lambda v: abs(v[0]) + abs(v[1]), default=(0.0, 0.0))


# ---------------------------------------------------------------- tutti i pad per l'app (pagina Controller, navigazione)
# Nomi dei pad Xbox dal prodotto (XInputGetCapabilitiesEx): il browser dell'app chiama "Xbox 360 Controller" qualsiasi pad
# XInput (anche un Series X) e a volte "Unknown Gamepad" con i tasti in un altro ordine.
NOMI_XBOX = {0x028E: "Xbox 360", 0x028F: "Xbox 360", 0x0291: "Xbox 360", 0x0719: "Xbox 360",
             0x02D1: "Xbox One", 0x02DD: "Xbox One", 0x02EA: "Xbox One", 0x02E0: "Xbox One", 0x02FD: "Xbox One", 0x0B20: "Xbox One",
             0x02E3: "Xbox Elite", 0x0B00: "Xbox Elite 2", 0x0B05: "Xbox Elite 2", 0x0B22: "Xbox Elite 2",
             0x0B12: "Xbox Series X|S", 0x0B13: "Xbox Series X|S", 0x0B0A: "Xbox Adaptive"}


def tipo_da_vid(vid):
    return "xbox" if vid == 0x045E else "ps" if vid == 0x054C else "switch" if vid == 0x057E else "altro"


class LettorePad:
    """Tutti i pad collegati come li legge il menu in gioco (XInput + PadWinmm + PadHid: tasti già nell'ordine di un pad
    Xbox, per marca), uno per voce, e quale è stato toccato per ultimo (con due pad l'app segue quello che usi)."""

    def __init__(self):
        import ctypes
        self._ct = ctypes
        try:
            self._xi = ctypes.windll.xinput1_4
        except OSError:
            self._xi = None
        self._ex = None
        try:
            self._ex = self._xi[108] if self._xi else None  # XInputGetCapabilitiesEx (senza nome: solo per numero)
        except (AttributeError, OSError):
            self._ex = None
        self.ps, self.hid = PadWinmm(), PadHid()
        self._nomi, self._prima, self.attivo = {}, {}, None

    def _nome_xinput(self, i):
        if i in self._nomi:
            return self._nomi[i]
        nome, vid, pid = "Xbox", 0x045E, None
        if self._ex:
            buf = self._ct.create_string_buffer(64)
            try:
                if self._ex(1, i, 0, buf) == 0:
                    vid, pid = int.from_bytes(buf.raw[20:22], "little"), int.from_bytes(buf.raw[22:24], "little")
                    nome = NOMI_XBOX.get(pid, "Xbox") if vid == 0x045E else "XInput"
            except (OSError, ValueError):
                pass
        self._nomi[i] = (nome, vid, pid)
        return self._nomi[i]

    def leggi(self):
        """-> {"pad": [{id, tipo, nome, b, sx, sy, dx, dy}], "attivo": id}. b = bit XInput (A 0x1000, B 0x2000, X 0x4000,
        Y 0x8000, LB 0x100, RB 0x200, LT 0x10000, RT 0x20000, View 0x20, Menu 0x10, L3 0x40, R3 0x80, croce 1/2/4/8)
        SENZA lo stick; levette -1..1 (su = negativo)."""
        ct, out = self._ct, []

        class ST(ct.Structure):
            _fields_ = [("pkt", ct.c_uint32), ("b", ct.c_uint16), ("lt", ct.c_ubyte), ("rt", ct.c_ubyte),
                        ("lx", ct.c_short), ("ly", ct.c_short), ("rx", ct.c_short), ("ry", ct.c_short)]
        for i in range(4) if self._xi else ():
            st = ST()
            if self._xi.XInputGetState(i, ct.byref(st)) != 0:
                self._nomi.pop(i, None)  # scollegato: al prossimo collegamento rileggo il nome (può essere un altro pad)
                continue
            nome, vid, pid = self._nome_xinput(i)
            b = st.b | (0x10000 if st.lt > 140 else 0) | (0x20000 if st.rt > 140 else 0)
            out.append({"id": f"x{i}", "tipo": "xbox", "nome": nome, "b": b, "sx": st.lx / 32768, "sy": -st.ly / 32768,
                        "dx": st.rx / 32768, "dy": -st.ry / 32768})
        con_xbox = bool(out)
        try:
            self.ps.bottoni(con_xbox=con_xbox)
            self.hid.bottoni(con_xbox=con_xbox)
            for d in self.ps.dispositivi + self.hid.dispositivi:
                d = dict(d, tipo=tipo_da_vid(d.get("vid")))
                if d["tipo"] == "xbox":
                    continue  # già letto con XInput
                if d["tipo"] == "ps":
                    d["nome"] = "DualSense" if d.get("pid") in (0x0CE6, 0x0DF2) else "DualShock 4" if d.get("pid") in (0x09CC, 0x05C4) else d["nome"]
                out.append(d)
        except Exception:  # noqa: BLE001 - un pad strano non deve fermare gli altri
            pass
        for d in out:  # toccato adesso = tasto cambiato o levetta oltre metà corsa
            mosso = max(abs(d["sx"]), abs(d["sy"]), abs(d["dx"]), abs(d["dy"])) > 0.5
            if (d["b"] != self._prima.get(d["id"], (0, False))[0] and d["b"]) or (mosso and not self._prima.get(d["id"], (0, False))[1]):
                self.attivo = d["id"]
            self._prima[d["id"]] = (d["b"], mosso)
        if out and self.attivo not in {d["id"] for d in out}:
            self.attivo = out[0]["id"]
        return {"pad": out, "attivo": self.attivo if out else None}
