"""Motore dell'app unica "SM2 Enhanced" (fino al 2026-10-16 "Spider-Man 2 Definitive Edition"): trova Dolphin e il pack, legge il catalogo di skin e
ragnatele, installa i file delle texture (con backup). Niente grafica qui: la usa spidey_app.py."""
import base64
import math
import ctypes
import hashlib
import io
import json
import threading
import os
import re
import shutil
import sys
import winreg
from datetime import datetime
from pathlib import Path

import psutil
from PIL import Image

VERSIONE_APP = "1.2"
# PROVA DA ZERO (--da-zero): l'app vive in una cartella tutta sua e non vede il Dolphin, la libreria, gli zip e le
# impostazioni veri, come su un PC dove non c'è niente. Serve a provare l'esperienza di chi parte da zero.
DA_ZERO = "--da-zero" in sys.argv
# SPIDEY_BASE_PROVA = cartella diversa per le prove automatiche (così non tocco la prova da zero che John sta usando)
BASE_PROVA = Path(os.environ.get("SPIDEY_BASE_PROVA") or Path.home() / "SM2 Enhanced - prova da zero")
# NOME (2026-10-16, Patreon): "SM2 Enhanced" e non più "Spider-Man 2 DE" / "Definitive Edition" (sembrava un prodotto
# ufficiale). Cartelle e file con il nome vecchio vengono rinominati da soli al primo avvio (_migra_nome).
NOME_APP = "SM2 Enhanced"
# TUTTO GRATIS (2026-10-27): una sola edizione con tutte le funzioni (la "Plus" per Patreon è stata tolta). Patreon resta
# solo come sostegno volontario: niente funzioni bloccate.
PATREON_URL = "https://www.patreon.com/JohnSwing"  # pagina Patreon di John Swing (pulsante "Sostienimi")
NOME_VECCHIO = "Spider-Man 2 DE"


def _migra_nome(radice):
    """radice/"Spider-Man 2 DE" -> radice/"SM2 Enhanced" se c'è solo la vecchia. Se non si può (file in uso: un'app vecchia
    o il Dolphin installato dall'app sono aperti) per questa volta resta la vecchia. Ritorna la cartella da usare e se l'ha
    appena spostata."""
    nuova, vecchia = radice / NOME_APP, radice / NOME_VECCHIO
    if nuova.exists() or not vecchia.exists():
        return nuova, False
    try:
        os.rename(vecchia, nuova)
        return nuova, True
    except OSError:
        return vecchia, False


if DA_ZERO:
    CONF_DIR = BASE_PROVA / "AppData"
else:
    CONF_DIR, _CONF_SPOSTATA = _migra_nome(Path(os.environ.get("APPDATA", Path.home())))
CONF = CONF_DIR / "config.json"
CACHE = CONF_DIR / "cache"
BACKUP_DIR = CONF_DIR / "backup"
LOG = CONF_DIR / "errori.log"
# pack di sviluppo (solo da Python, facoltativo): percorso in pack_sviluppo.txt accanto agli script (non pubblicato)
PACK_SVILUPPO = Path((Path(__file__).with_name("pack_sviluppo.txt").read_text(encoding="utf-8").strip()
                      if Path(__file__).with_name("pack_sviluppo.txt").is_file() else "") or Path(__file__).parent)

ID_GIOCO = ["GK2E52", "GK2P52", "GK2I52", "GK2D52", "GK2F52"]

# texture di Spidey (nomi dei file nel pack); "quarta" = usata solo dalle skin recenti
CORPO = "tex1_512x256_f1fab63166fd99c4_851435972ec1a204_8.png"
SKIN_FILE = {
    "corpo": CORPO,
    "parte": "tex1_512x128_f92a5e6f22979e17_1fa692102c5edd5b_8.png",
    "dettaglio": "tex1_32x32_4f1344ca5c70e651_14.png",
    "quarta": "tex1_512x256_230cce7eb485c073_14.png",
}
# costume alternativo (freccia giù): stessi file con l'impronta cambiata dal codice AR (vedi costume.py)
ALT_FILE = {
    "corpo": "tex1_512x256_14332605d4fa1ec7_851435972ec1a204_8.png",
    "parte": "tex1_512x128_a47aee78084b112f_1fa692102c5edd5b_8.png",
    "dettaglio": "tex1_32x32_4cffd40c5dce418c_14.png",
}
RAGNATELE_FILE = [
    "tex1_128x128_fad47984a88db67d_e88245a96aeb8621_8.png", "tex1_64x64_19465401f45c150e_4bf7d3f3620d3b20_8.png",
    "tex1_64x64_d5053742d3f8d542_df4467aa65ecbf2a_8.png", "tex1_64x64_m_be41a500126e082c_80bf80302fb5ae0d_9.png",
    "tex1_32x32_165bff62af94a520_2.png", "tex1_32x32_2fa57170451bdc32_6.png", "tex1_32x32_8f12b3865198cb9e_2.png",
    "tex1_32x32_af480f9bef757fdd_2.png", "tex1_32x32_d861eb4f8b0326e0_2.png", "tex1_64x64_20220603ef1e10dd_2.png",
    "tex1_64x64_791d5dc49bcaf82a_2.png",
]
MODDB = "https://www.moddb.com/mods/spider-man-2-re-alpha"


def lungo(p):
    """Percorso "lungo" di Windows (prefisso \\?\): funziona anche oltre i 260 caratteri senza l'impostazione di sistema
    "percorsi lunghi" (che sul PC di sviluppo è accesa, su tanti altri no: le varianti di Fresh Start arrivano a ~270)."""
    if p is None:
        return None
    s = str(p)
    if os.name != "nt" or s.startswith("\\\\?\\"):
        return Path(s)
    s = os.path.abspath(s)
    return Path("\\\\?\\UNC\\" + s[2:]) if s.startswith("\\\\") else Path("\\\\?\\" + s)


def corto(p):
    """Lo stesso percorso senza il prefisso \\?\ (da mostrare, da confrontare, da passare ad altri programmi)."""
    if p is None:
        return None
    s = str(p)
    if s.startswith("\\\\?\\UNC\\"):
        return "\\\\" + s[8:]
    return s[4:] if s.startswith("\\\\?\\") else s


def tex(cartella, nome):
    """File vero di una texture: nome.png oppure nome.dds (stesso nome, compressa). None se non c'è."""
    if not cartella:
        return None
    p = Path(cartella) / nome
    if p.is_file():
        return p
    d = p.with_suffix(".dds")
    return d if d.is_file() else None


def logico(nome):
    """Nome con cui l'app conosce una texture (sempre .png, anche se il file è .dds)."""
    return nome[:-4] + ".png" if nome.lower().endswith(".dds") else nome
CREDITI = {  # gruppo -> (autore / fonte, pagina ModDB). Autori verificati sulle pagine ModDB (campo Uploader).
    "Collezione": ("RE Mods (special thanks: KomandoUgur)", MODDB),
    "LifeGeeksYT": ("LifeGeeksYT (JayeSGee)", MODDB + "/addons/lifegeeksyts-spider-mods-spider-man-2-re3"),
    "Fresh Start Suit": ("JayeSGee", MODDB + "/addons/fresh-start-suit"),
    "Fantastic Spider-Man Suit": ("JayeSGee", MODDB + "/addons/fantastic-spider-man-suit"),
    "Zombie Hunter Suit": ("JayeSGee", MODDB + "/addons/zombie-hunter-suit"),
    "Spider-Armor MK I": ("JayeSGee · Web of Spider-Man #100 (Kavanagh, Saviuk)", MODDB + "/addons/spider-armor-mk-i"),
    "Vanilla Suit Colors HD": ("ThunderTurtle", MODDB + "/addons/tex1-512x256-f1fab63166fd99c4-851435972ec1a204-8"),
    "Unofficial Update Pack V2.3": ("ThunderTurtle", MODDB + "/addons/unofficial-update-pack-v2"),
    "Movie Accuracy Suit": ("ThunderTurtle", MODDB + "/addons/unofficial-update-pack-v2"),
    "Philly Suit": ("JayeSGee · design @philadelphia_spiderman",
                    MODDB + "/addons/philly-suit-design-by-philadelphia-spiderman-on-tiktok-and-instagram"),
}
CREDITI["Aggiunte"] = ("—", MODDB)
CREDITI_SKIN = {  # singole skin della collezione con un autore diverso
    "2003_BETA_SUIT": ("KomandoUgur", MODDB + "/addons/2003-beta-suit-mod"),
}
CARTELLE_IGNORATE = {"2nd Skin"}  # uscita del vecchio costume.py, non è una skin


# ---------------------------------------------------------------- sistema
def log_errore(testo):
    try:
        CONF_DIR.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S} (v{VERSIONE_APP})\n{testo}\n")
    except OSError:
        pass


def _migra_da_python_store():
    """Prima volta come .exe: la versione di sviluppo (Python del Microsoft Store) teneva la configurazione in una
    AppData "virtuale" (%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.*\LocalCache\Roaming). La copio nella
    AppData vera (tranne la cache del browser interno), così libreria, preferenze, codici e foto degli stati restano."""
    if DA_ZERO or CONF.exists() or not getattr(sys, "frozen", False):
        return
    pacchetti = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages"
    trovate = [v for n in (NOME_APP, NOME_VECCHIO) for v in pacchetti.glob(f"PythonSoftwareFoundation.Python.*/LocalCache/Roaming/{n}")]
    for vecchia in sorted(trovate, reverse=True):
        if (vecchia / "config.json").is_file():
            shutil.copytree(vecchia, CONF_DIR, dirs_exist_ok=True, ignore=shutil.ignore_patterns("webview", "md5"))  # md5 = 48 mila file, si rifà
            return


def carica_config():
    _migra_da_python_store()
    try:
        return json.loads(CONF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_CONF_LOCK = threading.Lock()


def scrivi_config(conf):
    """Scrive config.json tutto in una volta (file temporaneo + os.replace): la scrivono più fili insieme e l'app si
    chiude con os._exit, un file scritto a metà farebbe perdere tutte le impostazioni (carica_config darebbe {})."""
    with _CONF_LOCK:
        CONF_DIR.mkdir(parents=True, exist_ok=True)
        for prova in range(5):  # un altro filo può cambiare un dizionario dentro mentre lo trasformo in testo
            try:
                dati = json.dumps(dict(conf), indent=2, ensure_ascii=False)
                break
            except RuntimeError:
                if prova == 4:
                    raise
        scrivi_sicuro(CONF, dati)


_SCRIVI_LOCK = threading.Lock()


def scrivi_sicuro(p, testo):
    """Scrive un file di testo tutto in una volta (temporaneo accanto + os.replace): chi lo legge trova il file di prima o
    quello nuovo, mai uno a metà (l'app si chiude con os._exit; manifesto DDS e libreria.json rovinati = l'app non
    riconosceva più i suoi DDS o i pacchetti installati)."""
    p = Path(p)
    with _SCRIVI_LOCK:
        tmp = p.with_name(p.name + f".tmp{threading.get_ident()}")
        tmp.write_text(testo, encoding="utf-8")
        os.replace(tmp, p)


def lingua_sistema():
    try:
        return {0x10: "it", 0x07: "de", 0x0C: "fr", 0x0A: "es"}.get(ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF, "en")
    except (AttributeError, OSError):
        return "en"


def cartella_app():
    """Documenti/SM2 Enhanced (libreria, Dolphin installato dall'app). Al primo avvio col nome nuovo sposta la cartella
    vecchia e aggiorna i percorsi salvati (config e file .json in AppData)."""
    doc = cartella_documenti()
    if DA_ZERO:
        return doc / NOME_APP
    cartella, _spostata = _migra_nome(doc)
    # percorsi salvati aggiornati UNA volta (segno in AppData), anche se la cartella l'aveva già spostata un altro avvio
    # (es. la versione di sviluppo, che ha un'AppData sua): se no la libreria resterebbe "persa"
    segno = CONF_DIR / "nome_aggiornato.txt"
    if cartella.name == NOME_APP and not segno.is_file() and CONF_DIR.is_dir():
        _aggiorna_percorsi(str(doc / NOME_VECCHIO), str(cartella))
        try:
            segno.write_text(NOME_APP, encoding="utf-8")
        except OSError:
            pass
    return cartella


def _aggiorna_percorsi(vecchio, nuovo):
    """Nei .json di AppData (config, libreria, compressione, cache...) i percorsi che iniziano col vecchio nome della
    cartella in Documenti passano al nuovo."""
    def cambia(x):
        if isinstance(x, str):
            return nuovo + x[len(vecchio):] if x.lower().startswith(vecchio.lower()) else x
        if isinstance(x, list):
            return [cambia(v) for v in x]
        if isinstance(x, dict):
            return {cambia(k): cambia(v) for k, v in x.items()}
        return x
    for f in CONF_DIR.rglob("*.json"):
        try:
            if f.stat().st_size > 50_000_000 or "webview" in f.parts:
                continue
            testo = f.read_text(encoding="utf-8")
            if NOME_VECCHIO not in testo:
                continue
            scrivi_sicuro(f, json.dumps(cambia(json.loads(testo)), indent=2 if f.name == "config.json" else None, ensure_ascii=False))
        except (OSError, ValueError):
            pass


def cartella_documenti():
    if DA_ZERO:
        return BASE_PROVA / "Documenti"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
        if buf.value:
            return Path(buf.value)
    except (AttributeError, OSError):
        pass
    return Path.home() / "Documents"


_APERTI = {"quando": 0.0, "lista": []}
_APERTI_LOCK = threading.Lock()


def exe_dolphin_aperti(fresco=False):
    """Percorsi degli exe di Dolphin aperti. Elencare i processi con l'exe costa ~35 ms e lo chiedono più fili ogni
    mezzo secondo mentre giochi (CPU rubata a Dolphin, che è il collo di bottiglia): risultato tenuto 1 s."""
    import time
    with _APERTI_LOCK:
        if not fresco and time.monotonic() - _APERTI["quando"] < 1.0:
            return list(_APERTI["lista"])
        out = _exe_dolphin_aperti()
        _APERTI["quando"], _APERTI["lista"] = time.monotonic(), out
        return list(out)


def e_dolphin(nome):
    """Il nome di processo è Dolphin (non DolphinMemoryEngine.exe né DolphinTool.exe, che hanno lo stesso inizio)."""
    nome = (nome or "").lower()
    return nome.startswith("dolphin") and nome.endswith(".exe") and "memory" not in nome and "tool" not in nome


def ambiente_figli():
    """Ambiente per i programmi che l'app avvia (Dolphin, PowerShell della musica, texconv, estrattori): con l'exe di
    PyInstaller via la sua cartella _MEI dal PATH e le variabili del bootloader (_PYI_*: un altro exe di PyInstaller
    avviato da qui si crederebbe un nostro sottoprocesso e userebbe la NOSTRA cartella _MEI). None = come il nostro."""
    if not getattr(sys, "frozen", False):
        return None
    mei = os.path.normcase(sys._MEIPASS)
    env = {k: v for k, v in os.environ.items() if k.upper() != "PATH" and not k.upper().startswith(("_PYI_", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env["PATH"] = os.pathsep.join(x for x in os.environ.get("PATH", "").split(os.pathsep) if not os.path.normcase(x).startswith(mei))
    return env


def _exe_dolphin_aperti():
    out = []
    for p in psutil.process_iter(["name", "exe"]):
        if e_dolphin(p.info.get("name")):
            e = p.info.get("exe")
            if DA_ZERO and (not e or BASE_PROVA not in Path(e).parents):
                continue  # prova da zero: il Dolphin vero non esiste
            out.append(e)
    return out


_AGGANCIO = {"pid": None, "quando": 0.0}
# La memoria di Dolphin (dolphin_memory_engine) si legge da un filo alla volta: letture insieme da più fili davano
# risultati sbagliati (sessione 18). Rientrante: chi lo tiene può chiamare funzioni che lo riprendono.
DME_LOCK = threading.RLock()
# Gli INI del gioco li scrivono più fili insieme (ogni chiamata dalla pagina gira in un filo suo: es. ←/→ veloci sulla
# vista della prima persona nel menu in gioco = più cam_opzione insieme): uno poteva leggere un INI mentre un altro lo
# riscriveva e salvarlo a metà. Le funzioni che riscrivono gli INI passano tutte da qui (RLock: si chiamano tra loro).
INI_LOCK = threading.RLock()


def _sotto_lock_ini(f):
    import functools

    @functools.wraps(f)
    def dentro(*a, **k):
        with INI_LOCK:
            return f(*a, **k)
    return dentro


_GIA_FATTO = {}  # (funzione, INI, argomenti, database) -> (data, peso) dell'INI subito dopo


def _salta_se_uguale(vuoto):
    """Per i controlli che si rifanno a ogni apertura di Codici, Spider-Cam, launcher (aggiorna_codici_vecchi,
    allinea_camera: 5 versioni = ~2 s): se l'INI non è cambiato da quando l'ho già sistemato con gli stessi argomenti e lo
    stesso database dei codici, non serve rifarlo (ritorna `vuoto`)."""
    def deco(f):
        import functools

        @functools.wraps(f)
        def dentro(ini, *a, **k):
            try:
                db = os.stat(Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "codici_db.json").st_mtime_ns
                chiave = (f.__name__, os.path.normcase(str(ini)), repr(a), repr(sorted(k.items())), db)
                st = os.stat(ini)
                if _GIA_FATTO.get(chiave) == (st.st_mtime_ns, st.st_size):
                    return vuoto
            except OSError:
                return f(ini, *a, **k)
            ris = f(ini, *a, **k)
            try:
                st = os.stat(ini)
                _GIA_FATTO[chiave] = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
            return ris
        return dentro
    return deco


def aggancia_dme():
    """Vedi _aggancia_dme (sotto DME_LOCK: sganciare mentre un altro filo legge faceva fallire le sue letture)."""
    with DME_LOCK:
        return _aggancia_dme()


def _aggancia_dme():
    """dolphin_memory_engine agganciato al Dolphin di ADESSO. Dopo che Dolphin si chiude e si riapre il vecchio aggancio
    risulta ancora "agganciato" ma legge la memoria di un processo morto (le letture falliscono per sempre): se il
    processo cambia lo sgancio e riaggancio. Il processo si controlla al massimo ogni 1,5 s.
    Ritorna il modulo dme agganciato, o None (Dolphin chiuso / non agganciabile)."""
    import time
    import dolphin_memory_engine as dme
    ora = time.monotonic()
    if ora - _AGGANCIO["quando"] > 1.5:
        _AGGANCIO["quando"] = ora
        pid = None
        for pr in psutil.process_iter(["name"]):
            nome = (pr.info.get("name") or "").lower()
            if nome.startswith("dolphin") and nome.endswith(".exe") and "memory" not in nome and "tool" not in nome:
                pid = pr.pid
                break
        if pid != _AGGANCIO["pid"]:
            try:
                dme.un_hook()
            except Exception:  # noqa: BLE001
                pass
            _AGGANCIO["pid"] = pid
    if not _AGGANCIO["pid"]:
        return None
    try:
        if not dme.is_hooked():
            dme.hook()
        if not dme.is_hooked():
            return None
        try:  # agganciato ma la memoria non si legge (John, mappa 3D 2026-10-19: "Could not read memory at 0x80000000" a
            dme.read_byte(0x80000000)  # metà vista e poi per sempre: la mappa restava bloccata) -> sgancio e riaggancio
        except Exception:  # noqa: BLE001
            dme.un_hook()
            dme.hook()
            if not dme.is_hooked():
                return None
            dme.read_byte(0x80000000)
        return dme
    except Exception:  # noqa: BLE001
        return None


def trova_dolphin(conf=None):
    """Cartella utente di Dolphin: scelta a mano, portable, registro, Documenti, AppData."""
    candidati = []
    if conf and conf.get("dolphin"):
        scelta = Path(conf["dolphin"])
        if (scelta / "Config").is_dir() or (scelta / "GameSettings").is_dir():
            return scelta  # scelta a mano e valida: niente ricerca tra i processi
        candidati.append(scelta)
    aperti = [Path(e).parent for e in exe_dolphin_aperti() if e]
    candidati += [d / "User" for d in aperti if (d / "portable.txt").exists()]
    try:
        if DA_ZERO:
            raise OSError  # prova da zero: niente registro né cartelle vere di Dolphin
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Dolphin Emulator") as k:
            for nome in ("UserConfigPath", "LocalUserConfig"):
                try:
                    v, _ = winreg.QueryValueEx(k, nome)
                except OSError:
                    continue
                if nome == "UserConfigPath" and v:
                    candidati.append(Path(v))
                elif nome == "LocalUserConfig" and str(v) == "1":
                    candidati += [d / "User" for d in aperti]
    except OSError:
        pass
    candidati += [cartella_documenti() / "Dolphin Emulator"] + ([] if DA_ZERO else [Path(os.environ.get("APPDATA", "")) / "Dolphin Emulator"])
    for c in candidati:
        if (c / "Config").is_dir() or (c / "GameSettings").is_dir():
            return c
    return None


def trova_pack(conf=None):
    """Cartella del pack: quella scelta, quella dell'exe (l'app sta nella radice del pack), quella di sviluppo."""
    cand = []
    if conf and conf.get("pack"):
        cand.append(Path(conf["pack"]))
    if getattr(sys, "frozen", False):
        cand.append(Path(sys.executable).parent)
    cand += [] if getattr(sys, "frozen", False) or DA_ZERO else [Path(__file__).parent, PACK_SVILUPPO]  # il pack di sviluppo solo da Python
    for c in cand:
        if (c / "Skins" / "Suit Mods").is_dir():
            return lungo(c)  # dentro la libreria ci sono percorsi oltre i 260 caratteri
    return None


def cartelle_texture(dolphin):
    """Le cartelle Load/Textures/<ID> del gioco che esistono (almeno quella USA, creata se manca)."""
    base = Path(dolphin) / "Load" / "Textures"
    out = [base / i for i in ID_GIOCO if (base / i).is_dir()]
    if not out:
        out = [base / "GK2E52"]
    return out


def versioni_texture(dolphin):
    """Versioni del gioco che hanno le texture: cartelle Load/Textures/<ID> e file <ID>.txt dentro (collegamenti)."""
    base = Path(dolphin) / "Load" / "Textures"
    out = []
    for cart in cartelle_texture(dolphin):
        if not cart.is_dir():
            continue
        for g in [cart.name] + [p.stem for p in cart.glob("*.txt")]:
            if g in ID_GIOCO and g not in out:
                out.append(g)
    return sorted(out, key=ID_GIOCO.index)


# ---------------------------------------------------------------- catalogo
def pulisci(t):
    t = re.sub(r"_v\d+(\.\d+)*$", "", t).replace("_", " ")
    return re.sub(r"\s*\(Design by [^)]*\)", "", t).strip()


def _nodo(cartella, nome):
    """Albero delle varianti: ogni cartella con il file del corpo è una skin installabile."""
    figli = []
    for d in sorted(p for p in cartella.iterdir() if p.is_dir()):
        n = _nodo(d, d.name)
        if n:
            figli.append(n)
    ha_file = tex(cartella, CORPO) is not None
    if not ha_file and not figli:
        return None
    if not ha_file and len(figli) == 1 and cartella.name in ("Suit Styles",):
        return figli[0]
    return {"nome": pulisci(nome).replace("Suit Style", "Stile").replace(" (Default)", ""),
            "default": "(Default)" in nome, "path": str(cartella) if ha_file else None, "figli": figli}


def foglia_default(nodo):
    """Percorso della variante predefinita dall'autore: i file del nodo, se ci sono, altrimenti il figlio (Default)."""
    if nodo["path"] and not any(f["default"] for f in nodo["figli"]):
        return nodo["path"]
    figli = nodo["figli"]
    scelto = next((f for f in figli if f["default"]), figli[0] if figli else None)
    return foglia_default(scelto) if scelto else nodo["path"]


def conta_foglie(nodo):
    return (1 if nodo["path"] else 0) + sum(conta_foglie(f) for f in nodo["figli"])


def catalogo_skin(pack):
    base = Path(pack) / "Skins" / "Suit Mods"
    voci = []

    def aggiungi(cartella, gruppo, nome, cred=None):
        cred = cred or CREDITI_SKIN.get(cartella.name) or CREDITI.get(gruppo, ("ModDB", MODDB))
        n = _nodo(cartella, cartella.name)
        if not n:
            return
        n["nome"] = nome
        voci.append({"id": f"{gruppo}/{cartella.name}", "gruppo": gruppo, "nome": nome, "albero": n,
                     "default": foglia_default(n), "varianti": conta_foglie(n),
                     "crediti": cred[0], "link": cred[1]})

    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        if d.name in CARTELLE_IGNORATE:
            continue
        if d.name == "1-LifeGeeksYT's Skins":
            for s in sorted(p for p in d.iterdir() if p.is_dir()):
                aggiungi(s, "LifeGeeksYT", pulisci(s.name))
        elif d.name == "1-Aggiunte":  # aggiunte dall'utente col pulsante "Aggiungi"
            for s in sorted(p for p in d.iterdir() if p.is_dir()):
                aggiungi(s, "Aggiunte", pulisci(s.name), CREDITI["Aggiunte"])
        elif d.name == "1-Others":  # mod di JayeSGee (verificato su ModDB): un gruppo solo, crediti per mod
            for s in sorted(p for p in d.iterdir() if p.is_dir()):
                nome = pulisci(s.name)
                cred = CREDITI.get(nome, ("ModDB", MODDB))
                aggiungi(s, cred[0].split(" ·")[0] if cred[0] != "ModDB" else nome, nome, cred)  # gruppo = autore
        else:
            aggiungi(d, "Collezione", pulisci(d.name))
    voci.sort(key=lambda v: (v["gruppo"] != "Collezione", v["gruppo"] != "LifeGeeksYT", v["gruppo"], v["nome"].lower()))
    return voci


def catalogo_ragnatele(pack):
    base = Path(pack) / "Skins" / "Webs"
    out = [{"id": "vanilla", "nome": "Originali del gioco", "path": None, "file": 0}]
    if base.is_dir():
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            fs = [f for f in RAGNATELE_FILE if tex(d, f)]
            if fs:
                out.append({"id": d.name, "nome": d.name.replace(" Webbing", ""), "path": str(d), "file": len(fs)})
    return out


# ---------------------------------------------------------------- immagini (con cache su disco)
def _chiave(p):
    st = Path(p).stat()
    return hashlib.md5(f"{corto(p)}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()  # la cache non cambia col prefisso


def immagine64(percorso, larg=1024, alt=512, fondo=None):
    """PNG del pack -> JPEG base64 ridimensionato (cache in APPDATA). fondo = colore per le trasparenze."""
    k = _chiave(percorso) + f"_{larg}x{alt}_{fondo or ''}"
    f = CACHE / "img" / f"{k}.jpg"
    if not f.exists():
        im = Image.open(percorso).convert("RGBA")
        if fondo:
            sotto = Image.new("RGBA", im.size, fondo)
            im = Image.alpha_composite(sotto, im)
        im = im.convert("RGB").resize((larg, alt), Image.LANCZOS)
        f.parent.mkdir(parents=True, exist_ok=True)
        im.save(f, "JPEG", quality=86)
    return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()


# ---------------------------------------------------------------- costume originale (preso dal gioco dell'utente)
# L'app NON contiene la texture del costume originale del gioco: la ricava dal disco di chi gioca (o dalla memoria del
# gioco mentre gira) e la tiene in APPDATA. È la texture del corpo 512x256 C4 (16 colori RGB565 subito dopo i dati),
# salvata così com'è nell'archivio packs/amalga_gc.pak, nello stesso punto in tutte e 5 le versioni (verificato).
SKIN_ORIGINALE = CONF_DIR / "skin_originale.png"
SKIN_PAK = ("packs", "amalga_gc.pak", 129829472)  # cartella e file nel disco, posizione dei dati
SKIN_RAM = 0x8090A720  # in memoria col gioco aperto (USA/UK/DE/FR/ITA), stessa disposizione
SKIN_MD5 = "6b06a1d56f59247d471d2bea84db1ba0"  # dati + colori (0x10020 byte): solo per riconoscerli
SKIN_LUNGO = 0x10020


def skin_originale_da_dati(dati):
    """Dati grezzi del gioco -> skin_originale.png. True = erano davvero quelli del costume originale."""
    if len(dati) != SKIN_LUNGO or hashlib.md5(dati).hexdigest() != SKIN_MD5:
        return False
    w, h = 512, 256
    colori = []
    for i in range(16):
        v = dati[0x10000 + 2 * i] << 8 | dati[0x10001 + 2 * i]
        r, g, b = v >> 11 & 31, v >> 5 & 63, v & 31
        colori.append((r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2))
    px = bytearray(w * h * 3)
    k = 0
    for ty in range(0, h, 8):  # blocchi 8x8, 4 bit per pixel (prima il nibble alto)
        for tx in range(0, w, 8):
            for y in range(ty, ty + 8):
                for x in range(tx, tx + 8, 2):
                    c = dati[k]
                    k += 1
                    o = (y * w + x) * 3
                    px[o:o + 3] = bytes(colori[c >> 4])
                    px[o + 3:o + 6] = bytes(colori[c & 15])
    SKIN_ORIGINALE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SKIN_ORIGINALE.with_suffix(".tmp")
    Image.frombytes("RGB", (w, h), bytes(px)).save(tmp, "PNG")
    os.replace(tmp, SKIN_ORIGINALE)
    return True


def skin_originale_dal_pak(pak):
    """Dall'archivio del gioco già estratto dal disco."""
    with open(pak, "rb") as f:
        f.seek(SKIN_PAK[2])
        return skin_originale_da_dati(f.read(SKIN_LUNGO))


# ---------------------------------------------------------------- modello 3D di Spidey (preso dal gioco dell'utente)
# Come il costume: l'app NON contiene il modello del gioco. Lo ricostruisce dal disco (modello_disco.py: vertici, pesi,
# triangoli e uv da amalga_gc.pak, skinning emulato come fa il gioco) con le pose dell'anteprima (contenuti/modello_pose.json,
# l'unica cosa dentro l'app) e lo tiene in APPDATA/modello. Il timbro = md5 delle pose: cambiandole si rifà.
MODELLO_DIR = CONF_DIR / "modello"


def _timbro_pose(pose):
    return hashlib.md5(Path(pose).read_bytes()).hexdigest() if Path(pose).is_file() else ""


def modello_pronto(pose):
    t = MODELLO_DIR / "timbro.txt"
    return (MODELLO_DIR / "spidey_modello.json").is_file() and (MODELLO_DIR / "spidey_modello_idle.json").is_file()         and t.is_file() and t.read_text(encoding="utf-8").strip() == _timbro_pose(pose)


def modello_dal_pak(pak, pose):
    """Dall'archivio del gioco già estratto dal disco. True = fatto."""
    import modello_disco
    if not modello_disco.crea(pak, MODELLO_DIR, pose):
        return False
    (MODELLO_DIR / "timbro.txt").write_text(_timbro_pose(pose), encoding="utf-8")
    return True


def modello_json():
    """{"gioco": ..., "idle": ...} o None se non c'è ancora."""
    try:
        return {"gioco": json.loads((MODELLO_DIR / "spidey_modello.json").read_text(encoding="utf-8")),
                "idle": json.loads((MODELLO_DIR / "spidey_modello_idle.json").read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return None


def skin_originale_dalla_ram(dme):
    """Dalla memoria del gioco aperto (riserva se il disco non si può leggere). False anche se in quel momento in memoria
    c'è il costume alternativo (il codice cambia un byte)."""
    try:
        return skin_originale_da_dati(bytes(dme.read_bytes(SKIN_RAM, SKIN_LUNGO)))
    except Exception:  # noqa: BLE001
        return False


def _incolla_contenuto(tela, im, x, y, w, h):
    """Incolla `im` dentro il riquadro w x h senza deformarlo (centrata)."""
    im = im.convert("RGBA")
    im.thumbnail((w, h), Image.LANCZOS) if im.width > w or im.height > h else None
    r = min(w / im.width, h / im.height)
    if r > 1:  # le texture piccole si ingrandiscono un po' per vederle
        im = im.resize((max(1, round(im.width * r)), max(1, round(im.height * r))), Image.LANCZOS)
    tela.alpha_composite(im, (x + (w - im.width) // 2, y + (h - im.height) // 2))


def anteprima_ragnatele(cartella):
    """Mosaico delle texture della ragnatela su fondo scuro (per la scheda), proporzioni rispettate."""
    if not cartella:
        return None
    k = hashlib.md5(("v3|" + "|".join(f"{f}:{tex(cartella, f).stat().st_mtime_ns}" for f in RAGNATELE_FILE
                                      if tex(cartella, f))).encode()).hexdigest()
    f = CACHE / "img" / f"rag_{k}.png"
    if not f.exists():
        tela = Image.new("RGBA", (512, 256), (40, 45, 60, 255))  # grigio-blu: si vedono sia le ragnatele chiare che quelle nere
        grande = tex(cartella, RAGNATELE_FILE[0])
        piccole = [Image.open(tex(cartella, n)) for n in RAGNATELE_FILE[1:] if tex(cartella, n)]
        g = Image.open(grande) if grande else None
        if g is not None and g.height >= 2 * g.width:  # filo lungo e stretto: lo metto in orizzontale in alto
            _incolla_contenuto(tela, g.convert("RGBA").rotate(90, expand=True), 8, 8, 496, 100)
            for i, im in enumerate(piccole[:16]):
                _incolla_contenuto(tela, im, (i % 8) * 64 + 4, 120 + (i // 8) * 64 + 4, 56, 56)
        else:
            x = 0
            if g is not None:
                _incolla_contenuto(tela, g, 8, 8, 240, 240)
                x = 256
            for i, im in enumerate(piccole[:8]):
                _incolla_contenuto(tela, im, x + (i % 4) * 64 + 4, (i // 4) * 64 + 68, 56, 56)
        f.parent.mkdir(parents=True, exist_ok=True)
        tela.save(f)
    return "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()


def filo_ragnatela(cartella):
    """Il filo della ragnatela (prima texture) in PNG con trasparenza, lati potenza di 2 (WebGL), per l'anteprima 3D."""
    f = tex(cartella, RAGNATELE_FILE[0]) if cartella else None
    if not f:
        return None
    k = CACHE / "img" / f"filo_{_chiave(f)}.png"
    if not k.exists():
        im = Image.open(f).convert("RGBA")
        p2 = lambda x, m: min(m, 1 << max(2, round(math.log2(max(1, x)))))
        im = im.resize((p2(im.width, 256), p2(im.height, 1024)), Image.LANCZOS)
        k.parent.mkdir(parents=True, exist_ok=True)
        im.save(k)
    return "data:image/png;base64," + base64.b64encode(k.read_bytes()).decode()


def md5_file(p):
    k = CACHE / "md5" / (_chiave(p) + ".txt")
    if k.exists():
        h = k.read_text().strip()
        if len(h) == 32:  # un file di cache vuoto o a metà (app chiusa mentre scriveva) = rifaccio il conto
            return h
    h = hashlib.md5(Path(p).read_bytes()).hexdigest()
    k.parent.mkdir(parents=True, exist_ok=True)
    k.write_text(h)
    return h


# ---------------------------------------------------------------- stato installato
def foglie(nodo):
    if nodo["path"]:
        yield nodo["path"]
    for f in nodo["figli"]:
        yield from foglie(f)


def installate(dolphin, voci, ragnatele):
    """Riconosce cosa è installato adesso confrontando i file (md5) con quelli del catalogo (png o dds)."""
    cart = cartelle_texture(dolphin)[0]
    ris = {"primaria": None, "alternativa": None, "ragnatele": None}
    for slot, nomi in (("primaria", SKIN_FILE), ("alternativa", ALT_FILE)):
        f = tex(cart, nomi["corpo"])
        if not f:
            continue
        h = md5_file(f)
        for v in voci:
            for p in foglie(v["albero"]):
                q = tex(p, CORPO)
                if q and md5_file(q) == h:
                    ris[slot] = {"id": v["id"], "path": p}
                    break
            if ris[slot]:
                break
        if not ris[slot]:
            ris[slot] = {"id": "?", "path": None}
    presenti = [n for n in RAGNATELE_FILE if tex(cart, n)]
    if not presenti:
        ris["ragnatele"] = "vanilla"
    else:
        for r in ragnatele[1:]:
            if all(bool(tex(r["path"], n)) == bool(tex(cart, n)) and
                   (not tex(cart, n) or md5_file(tex(cart, n)) == md5_file(tex(r["path"], n)))
                   for n in RAGNATELE_FILE):
                ris["ragnatele"] = r["id"]
                break
        else:
            ris["ragnatele"] = "?"
    return ris


# ---------------------------------------------------------------- installazione
def _metti(src, dest, fresco=False):
    """Mette il file in Dolphin: se la libreria è sullo stesso disco è un hard link (nessuno spazio in più),
    altrimenti una copia. Il file vecchio va tolto prima: se era collegato alla libreria, scriverci dentro
    cambierebbe anche la libreria. fresco = copia con la data di adesso (skin, ragnatele, HUD, tasti): Dolphin, col
    gioco aperto, ricarica una texture solo se il file ha una data nuova; un hard link ha la data vecchia della
    libreria e il cambio non si vedeva finché non si riavviava il gioco (provato dal vivo, anche col precaricamento)."""
    dest = Path(dest)
    if fresco and dest.is_file() and os.stat(dest).st_nlink == 1:
        _riscrivi(src, dest)  # col gioco aperto: si riscrive DENTRO il file (vedi _riscrivi)
        return
    if dest.exists():
        dest.unlink()
    if fresco:
        shutil.copyfile(src, dest)
        return
    try:
        if os.path.splitdrive(corto(os.path.abspath(src)))[0].lower() == os.path.splitdrive(corto(os.path.abspath(dest)))[0].lower():
            os.link(src, dest)
            return
    except OSError:
        pass
    shutil.copyfile(src, dest)


def _riscrivi(src, dest):
    """Mette il contenuto di src DENTRO dest (che esiste e non è collegato alla libreria), con la data di adesso.
    Provato dal vivo: Dolphin a gioco aperto ricarica la texture ogni volta; se invece il file si cancella e si ricrea,
    a volte Dolphin lo perde (tiene la texture vecchia, poi mostra quella originale del gioco fino al riavvio)."""
    dati = Path(src).read_bytes()
    with open(dest, "r+b") as f:
        f.write(dati)
        f.truncate()


# ---------------------------------------------------------------- ragnatele del costume alternativo
# Il codice "cambio costume" cambia 1 byte della texture del corpo in memoria: 0x55 = costume principale, 0x00 =
# alternativo. Le ragnatele invece non stanno ferme in memoria (caricate al volo): le cambia l'app, riscrivendo i file
# delle ragnatele in Dolphin quando il costume cambia (Dolphin le ricarica subito). Serve l'app aperta.
COSTUME_BYTE = 0x8090A720  # stesso indirizzo in tutte e 5 le versioni
COSTUME_FIRMA = (0x8091A720, bytes.fromhex("102030a210a440c3"))  # primi colori della tavolozza del corpo: texture caricata


def costume_alternativo(dme):
    """True = in gioco c'è il costume alternativo, False = il principale, None = non si sa (texture non ancora in memoria)."""
    try:
        if bytes(dme.read_bytes(COSTUME_FIRMA[0], 8)) != COSTUME_FIRMA[1]:
            return None
        b = bytes(dme.read_bytes(COSTUME_BYTE, 16))
    except Exception:  # noqa: BLE001
        return None
    if b[1:] != b"\x55" * 15 or b[0] not in (0x55, 0x00):
        return None
    return b[0] == 0x00


def scambia_ragnatele(dolphin, cartella, riserva=None):
    """Mette in Dolphin le ragnatele di `cartella` riscrivendo i file che ci sono già (si vede subito anche a gioco
    aperto). I file che `cartella` non ha si prendono da `riserva` (le ragnatele principali): così non si cancella mai
    niente col gioco aperto. Ritorna quanti file ha riscritto."""
    n = 0
    for cart in cartelle_texture(dolphin):
        for nome in RAGNATELE_FILE:
            src = tex(cartella, nome) or tex(riserva, nome)
            if not src:
                continue
            dest = cart / (nome[:-4] + src.suffix)
            altro = cart / (nome[:-4] + (".png" if src.suffix.lower() == ".dds" else ".dds"))
            if altro.is_file():  # formato diverso (raro): va tolto
                altro.unlink()
            if dest.is_file() and _uguali(dest, src):
                continue
            _metti(src, dest, fresco=True)
            n += 1
    return n


def _backup(file, cartella, nome=None, copia=False):
    """Copia di sicurezza di un file prima di toglierlo da Dolphin. Sullo stesso disco è un hard link (istantaneo e
    senza spazio in più): è sicuro perché chi cambia un file in Dolphin lo toglie prima (_metti), mai ci scrive dentro.
    copia = True per i file che _metti riscrive DENTRO (skin, ragnatele, HUD, tasti: vedi _riscrivi): con un link il
    file avrebbe 2 collegamenti, _metti non lo riscriverebbe dentro e Dolphin a volte perde la texture."""
    cartella.mkdir(parents=True, exist_ok=True)
    dest = cartella / (nome or file.name)
    if dest.exists():
        return
    if not copia:
        try:
            os.link(file, dest)
            return
        except OSError:
            pass
    shutil.copy2(file, dest)


def _uguali(a, b):
    """Stesso contenuto? Se è lo stesso file (hard link dalla libreria) non serve calcolare l'MD5."""
    try:
        if os.path.samefile(a, b):
            return True
        return a.stat().st_size == b.stat().st_size and md5_file(a) == md5_file(b)
    except OSError:
        return False


class Installazione:
    """Raccoglie le operazioni (copia / cancella) e le esegue con backup dei file toccati."""

    def __init__(self, dolphin):
        self.cartelle = cartelle_texture(dolphin)
        self.ops = []  # (sorgente o None, nome destinazione)
        self.fresco = set()  # nomi da copiare con la data di adesso (si vedono subito anche a gioco aperto)
        self.fatti = self.totale = 0  # avanzamento (la pagina lo legge mentre lavora)

    def skin(self, cartella, alternativa=False, base=None):
        """base = cartella con la tuta di Spider-Man 2: RE: le texture che la skin non ha si prendono da lì
        (es. Vanilla Suit Colors HD cambia solo il corpo), invece di toglierle."""
        nomi = ALT_FILE if alternativa else SKIN_FILE
        for chiave, dest in nomi.items():
            src = tex(cartella, SKIN_FILE[chiave]) or tex(base, SKIN_FILE[chiave])
            self.ops.append((src, dest))
            self.fresco.add(dest)

    def ragnatele(self, cartella):
        for n in RAGNATELE_FILE:
            self.ops.append((tex(cartella, n), n))
            self.fresco.add(n)

    def esegui(self):
        quando = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        copiati = cancellati = 0
        self.nuovi = set()  # PNG copiati (da comprimere se la compressione è accesa)
        man = manifesto()
        self.totale, self.fatti = len(self.cartelle) * len(self.ops), 0
        for cart in self.cartelle:
            cart.mkdir(parents=True, exist_ok=True)
            comp = compressi(cart)
            for src, nome in self.ops:
                self.fatti += 1
                dds = cart / (nome[:-4] + ".dds")
                if src and src.suffix.lower() == ".dds":  # sorgente già compressa: in Dolphin va il .dds
                    dest, altro = dds, cart / nome
                    if altro.is_file():  # c'era il PNG: via (con backup)
                        _backup(altro, BACKUP_DIR / quando / cart.name, altro.name)
                        altro.unlink()
                    man.get(str(cart), {}).pop(nome, None)
                    if dest.is_file():
                        if _uguali(dest, src):
                            continue
                        _backup(dest, BACKUP_DIR / quando / cart.name, dest.name, copia=nome in self.fresco)
                    _metti(src, dest, nome in self.fresco)
                    copiati += 1
                    continue
                dest = cart / nome
                if nome in comp and not dest.is_file():  # c'è la versione DDS fatta dall'app
                    if src and comp[nome] == md5_file(src):
                        continue
                    _backup(dds, BACKUP_DIR / quando / cart.name, dds.name)
                    dds.unlink()
                    man.get(str(cart), {}).pop(nome, None)
                    if not src:
                        cancellati += 1
                        continue
                elif dds.is_file() and not dest.is_file():  # un .dds non fatto dall'app (es. libreria in DDS)
                    _backup(dds, BACKUP_DIR / quando / cart.name, dds.name)
                    dds.unlink()
                    if not src:
                        cancellati += 1
                        continue
                if dest.is_file():
                    if src and _uguali(dest, src):
                        continue
                    _backup(dest, BACKUP_DIR / quando / cart.name, nome, copia=nome in self.fresco)
                if src:
                    _metti(src, dest, nome in self.fresco)
                    self.nuovi.add(nome)
                    copiati += 1
                elif dest.is_file():
                    dest.unlink()
                    cancellati += 1
        if man:
            salva_manifesto()
        vecchi = sorted(p for p in BACKUP_DIR.iterdir() if p.is_dir() and p.name != "ini") if BACKUP_DIR.is_dir() else []
        for p in vecchi[:-15]:
            shutil.rmtree(p, ignore_errors=True)
        return {"copiati": copiati, "cancellati": cancellati, "cartelle": [c.name for c in self.cartelle]}


# ---------------------------------------------------------------- codici AR (GameSettings/<ID>.ini)
NOMI_VERSIONE = {"GK2E52": "USA", "GK2P52": "UK", "GK2I52": "ITA", "GK2D52": "DE", "GK2F52": "FR"}
PAL = {"GK2P52", "GK2I52", "GK2D52", "GK2F52"}


def carica_codici_db():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return json.loads((base / "codici_db.json").read_text(encoding="utf-8"))["codici"]


def _righe_ini(ini):
    raw = Path(ini).read_bytes() if Path(ini).exists() else b""
    nl = "\n" if raw and b"\r\n" not in raw else "\r\n"
    return (raw.decode("utf-8-sig").split(nl) if raw else []), nl


def _sezione(L, titolo):
    """(inizio, fine) del contenuto della sezione; fine esclude le righe vuote prima della sezione dopo."""
    i = next(k for k, x in enumerate(L) if x.strip() == titolo) + 1  # anche con spazi attorno al titolo
    j = i
    while j < len(L) and not L[j].strip().startswith("["):
        j += 1
    while j > i and not L[j - 1].strip():
        j -= 1
    return i, j


_LETTI_INI = {}  # INI -> ((data, peso), risultato): leggi_codici_ini è chiamata decine di volte per pagina


def leggi_codici_ini(ini):
    """Codici presenti, accesi e patch accese dell'INI. Rilegge il file solo se è cambiato (data o peso); ritorna sempre
    insiemi nuovi (chi li riceve può modificarli)."""
    try:
        st = os.stat(ini)
        firma = (st.st_mtime_ns, st.st_size)
    except OSError:
        firma = None
    k = os.path.normcase(str(ini))
    if firma and k in _LETTI_INI and _LETTI_INI[k][0] == firma:
        return {x: set(v) for x, v in _LETTI_INI[k][1].items()}
    ris = _leggi_codici_ini(ini)
    if firma:
        _LETTI_INI[k] = (firma, ris)
    return {x: set(v) for x, v in ris.items()}


def _leggi_codici_ini(ini):
    L, _ = _righe_ini(ini)
    pres, att, sez, patch = set(), set(), None, set()
    for r in L:
        s = r.strip()
        if s.startswith("["):
            sez = s
        elif s.startswith("$"):
            if sez in ("[ActionReplay]", "[Gecko]"):
                pres.add(s)
            elif sez in ("[ActionReplay_Enabled]", "[Gecko_Enabled]"):
                att.add(s)
            elif sez == "[OnFrame_Enabled]":
                patch.add(s)
    return {"presenti": pres, "attivi": att, "patch_attive": patch}


def nomi_gecko():
    """Nomi dei nostri codici Gecko (tipo "gecko" nel database), anche quelli di prima ("vecchi"): stanno in [Gecko] /
    [Gecko_Enabled], non negli AR. (Senza i vecchi, il vecchio Gecko della camera restava in [Gecko] accanto al nuovo e
    insieme sforavano lo spazio Gecko: Dolphin non ne caricava nessuno.)"""
    return {n for c in carica_codici_db() if c.get("tipo") == "gecko" for n in [c["nome_ini"], *c.get("vecchi", [])]}


@_sotto_lock_ini
def scrivi_codici_ini(ini, accendi, spegni):
    """accendi = [(nome, righe)]: il codice viene aggiunto se manca (se c'è già resta com'è: es. i valori della camera)
    e attivato. spegni = [(nome, togli_blocco)]: tolto dai codici attivi e, se togli_blocco, anche dall'elenco.
    Il resto del file resta com'è (CRLF, righe vuote, ordine). I codici Gecko vanno nelle loro sezioni."""
    ini = Path(ini)
    L, nl = _righe_ini(ini)
    gk = nomi_gecko()
    for sez, en, acc, spe in (("[ActionReplay]", "[ActionReplay_Enabled]", [x for x in accendi if x[0] not in gk],
                               [x for x in spegni if x[0] not in gk]),
                              ("[Gecko]", "[Gecko_Enabled]", [x for x in accendi if x[0] in gk], [x for x in spegni if x[0] in gk])):
        if sez == "[Gecko]" and not acc and sez not in [x.strip() for x in L]:
            continue  # niente da fare coi Gecko: non creo sezioni vuote
        _scrivi_sezioni(L, sez, en, acc, spe)
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_bytes(nl.join(L).encode("utf-8"))


def _scrivi_sezioni(L, sez, en, accendi, spegni):
    for titolo in (sez, en):
        if titolo not in [x.strip() for x in L]:
            while L and not L[-1].strip():
                L.pop()
            L += ([""] if L else []) + [titolo, ""]
    pulisci_nome = {n for n, togli in spegni if togli}
    i, j = _sezione(L, sez)
    k = i
    while k < j:  # toglie i blocchi da eliminare
        if L[k].strip() in pulisci_nome:
            fine = k + 1
            while fine < j and not L[fine].strip().startswith("$"):
                fine += 1
            while fine > k + 1 and not L[fine - 1].strip():
                fine -= 1
            del L[k:fine]
            j -= fine - k
        else:
            k += 1
    presenti = {L[x].strip() for x in range(i, j)}
    nuovi = [r for n, righe in accendi if n not in presenti for r in [n, *righe]]
    L[j:j] = nuovi
    i, j = _sezione(L, en)
    via = {n for n, _ in spegni}
    tieni = [L[x] for x in range(i, j) if L[x].strip() not in via]
    gia = {x.strip() for x in tieni}
    tieni += [n for n, _ in accendi if n not in gia]
    L[i:j] = tieni


def blocco_codice(ini, nome):
    """Righe di un codice AR dell'INI (None se non c'è)."""
    if not Path(ini).is_file():
        return None
    L, _ = _righe_ini(ini)
    for sez in ("[ActionReplay]", "[Gecko]"):
        if sez not in [x.strip() for x in L]:
            continue
        i, j = _sezione(L, sez)
        for k in range(i, j):
            if L[k].strip() == nome:
                fine = k + 1
                while fine < j and not L[fine].strip().startswith("$"):
                    fine += 1
                return [x.strip() for x in L[k + 1:fine] if x.strip()]
    return None


@_sotto_lock_ini
def sostituisci_codice(ini, vecchio, nuovo, righe):
    """Un codice cambiato di nome e di righe (es. l'HUD con l'interruttore): lo rimetto AL SUO POSTO, acceso se era
    acceso. Il resto del file resta com'è."""
    L, nl = _righe_ini(ini)
    sez = "[Gecko]" if nuovo in nomi_gecko() else "[ActionReplay]"
    if sez not in [x.strip() for x in L]:
        return False
    i, j = _sezione(L, sez)
    for k in range(i, j):
        if L[k].strip() == vecchio:
            fine = k + 1  # fino al prossimo codice, come blocco_codice (prima: fino alla prima riga vuota -> con una riga
            while fine < j and not L[fine].strip().startswith("$"):  # vuota dentro un codice restavano righe orfane)
                fine += 1
            while fine > k + 1 and not L[fine - 1].strip():  # le righe vuote prima del codice dopo restano dell'utente
                fine -= 1
            L[k:fine] = [nuovo, *righe]
            break
    else:
        return False
    if vecchio != nuovo and sez[:-1] + "_Enabled]" in [x.strip() for x in L]:  # stesso nome = solo righe nuove
        i, j = _sezione(L, sez[:-1] + "_Enabled]")
        nomi = [L[x].strip() for x in range(i, j)]
        for x in range(i, j):
            if L[x].strip() == vecchio:
                if nuovo in nomi:
                    del L[x]
                else:
                    L[x] = nuovo
                break
    Path(ini).write_bytes(nl.join(L).encode("utf-8"))
    return True


# CAMERA = codice AR "Custom camera" (la classica, valori di Spider-Cam) + codice Gecko (cam_ps4: camera moderna e
# R3 tra camera principale e alternativa). Nell'app sono UNA voce: accesi e spenti insieme. Le due camere scelte
# stanno in una riga del Gecko (817F0084: byte principale, byte alternativa).
CAM_MODI = {"moderna": 0, "classica": 1, "originale": 2, "prima": 3, "cinematica": 4, "amazing": 5}  # classica = "Migliorata" nell'app
CAM_MODI_BASE = ["moderna", "amazing"]  # le consigliate (John 2026-10-10; prima moderna + originale)
CAM_RIGA = "057F0084"
CAM_RIGA_OPZ = "057F0088"  # opzioni: byte 817F0088 = prima persona, la vista segue le acrobazie in aria (1 = sì)


def cam_opzioni_valore(opz):
    """Riga 057F0088: movimento della testa in prima persona (vedi cam_ps4.VISTE) e tuffo (byte
    817F0089: tuffo con L3 / camera della picchiata, vedi cam_ps4.valore_tuffo)."""
    import cam_ps4
    return cam_ps4.valore_vista(opz) << 24 | cam_ps4.valore_tuffo(opz) << 16


def cam_modi_valore(modi):
    m = [x if x in CAM_MODI else CAM_MODI_BASE[i] for i, x in enumerate((list(modi or []) + [None, None])[:2])]
    return m, CAM_MODI[m[0]] << 24 | CAM_MODI[m[1]] << 16 | 0x100  # 817F0086 = 1: camere già scritte


@_sotto_lock_ini
@_salta_se_uguale(False)
def allinea_camera(ini, gid, modi=None, opzioni=None):
    """Camera classica (AR) accesa -> accesi anche i suoi pezzi (Gecko con le camere scelte + programma AR), con le righe
    del database (se nell'INI sono vecchie le rimetto); spenta -> spenti anche loro."""
    if not Path(ini).is_file():
        return False
    aggiorna_codici_vecchi(ini, gid)  # es. il Gecko "$Modern camera..." di prima: via, se no sfora lo spazio Gecko
    db = {c["id"]: c for c in carica_codici_db()}
    ar = db.get("camera")
    pezzi = [c for c in db.values() if c.get("parte_di") == "camera" and gid in c["versioni"]]
    if not ar or not pezzi:
        return False
    on = ar["nome_ini"] in leggi_codici_ini(ini)["attivi"]
    _, val = cam_modi_valore(modi)
    v_opz = cam_opzioni_valore(opzioni)
    proprie = (CAM_RIGA + " ", CAM_RIGA_OPZ + " ")
    cambiato = False
    for c in pezzi:
        att = leggi_codici_ini(ini)["attivi"]
        c_on = c["nome_ini"] in att
        righe = [f"{CAM_RIGA} {val:08X}" if r.startswith(CAM_RIGA + " ") else f"{CAM_RIGA_OPZ} {v_opz:08X}"
                 if r.startswith(CAM_RIGA_OPZ + " ") else r for r in c["versioni"][gid]]
        if not on:
            if c_on:
                backup_file(ini, "GameSettings")
                scrivi_codici_ini(ini, [], [(c["nome_ini"], False)])
                cambiato = True
            continue
        blocco = blocco_codice(ini, c["nome_ini"])
        if blocco is not None:  # righe vecchie (codice rifatto nell'app, a parte le camere scelte): lo rimetto, anche se
            # era spento (se no accendendolo partirebbero le righe vecchie)
            vecchio = [x.upper() for x in blocco if not x.upper().startswith(proprie)]
            if vecchio != [x.upper() for x in righe if not x.startswith(proprie)]:
                backup_file(ini, "GameSettings")
                scrivi_codici_ini(ini, [], [(c["nome_ini"], True)])
                c_on = False
        if not c_on:
            backup_file(ini, "GameSettings")
            scrivi_codici_ini(ini, [(c["nome_ini"], righe)], [])
            cambiato = True
        if c.get("tipo") == "gecko":
            cambiato |= metti_modi_camera(ini, c["nome_ini"], {CAM_RIGA: val, CAM_RIGA_OPZ: v_opz})
    return cambiato


@_sotto_lock_ini
def metti_modi_camera(ini, nome, valori):
    """Riscrive solo le righe delle camere scelte e delle opzioni nel blocco Gecko `nome` (il resto del file com'è).
    valori = {inizio riga: valore}."""
    L, nl = _righe_ini(ini)
    if "[Gecko]" not in [x.strip() for x in L]:
        return False
    i, j = _sezione(L, "[Gecko]")
    dentro, cambiato = False, False
    for k in range(i, j):
        x = L[k].strip()
        if x.startswith("$"):
            dentro = x == nome
            continue
        for inizio, val in valori.items():
            if dentro and x.upper().startswith(inizio + " ") and x.upper() != f"{inizio} {val:08X}":
                L[k] = f"{inizio} {val:08X}"
                cambiato = True
    if cambiato:
        backup_file(ini, "GameSettings")
        Path(ini).write_bytes(nl.join(L).encode("utf-8"))
    return cambiato


# Prima riga dei codici coi comandi = "esegui solo in partita" (byte 1 in partita e nel rallenty, 0 nei menu). Il byte
# della sessione 9 (USA 0x8054517F) su USA/UK/DE/FR a volte resta a 0 anche in partita (foto della RAM orbA/brk1 e prova
# del 2026-10-06: i codici non partivano). Poi 0x8057DFDB (ITA 0x8057E05B): vale 0 per 1-2 s a ogni inizio di swing (i
# codici si fermavano e l'HUD 16:9 tornava stirato). Ora 0x80546963 (ITA 0x805469E3): 1 in partita (camminata, swing, salti,
# muri), 0 solo nel menu di pausa, su USA e ITA (foto della RAM e 1,5 milioni di letture in 40 s di gioco, 2026-10-06).
# MA dopo un tuffo in acqua (caricamento e rinascita sulla riva) resta a 0 per sempre (i codici coi comandi non
# giravano più: HUD che non si nascondeva) e nei riflessi va a 0 un quarto del tempo. Ora il MODO DELL'INTERFACCIA
# 0x804DCE2A (ITA 0x804DCEAA): 1 in partita (anche riflessi e dopo la rinascita), 2 menu di pausa, 0 titolo/caricamenti
# (verificato dal vivo 2026-10-07; sopra l'acqua salta a 0/2 per frazioni di secondo: i codici si fermano un attimo).
# riga "solo in partita" di prima -> le due righe di adesso (Spidey c'è E niente pausa; vedi camera_slider.riga_pausa):
# il modo dell'interfaccia (C84DCE2A / C84DCEAA) mentre giochi salta a 0 e a 2 per qualche fotogramma
RIGHE_PARTITA = {f"{v} 00000001": n for n, vv in
                 (("D4AD1A04 FFFFFFFF|C856B9BB 00000000", ("C854517F", "C857DFDB", "C8546963", "C84DCE2A")),
                  ("D4AD1A04 FFFFFFFF|C856BA3B 00000000", ("C85451FF", "C857E05B", "C85469E3", "C84DCEAA")))
                 for v in vv}


@_sotto_lock_ini
def aggiorna_riga_partita(f):
    """Sostituisce la vecchia riga "solo in partita" con quella giusta (vedi RIGHE_PARTITA). True = cambiato."""
    f = Path(f)
    if not f.is_file():
        return False
    s = f.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in s else "\n"
    n = s
    for vecchia, nuova in RIGHE_PARTITA.items():
        nuova = nuova.replace("|", nl)
        n = n.replace(vecchia, nuova).replace(vecchia.lower(), nuova)
    # terza riga "solo con la mappa chiusa" (2026-10-18) dopo le due di prima; non nel codice dell'ora (0D7FF100: deve
    # tenere fermo il cielo anche con la mappa aperta) e non se c'è già. La prima versione guardava 0x804DCB75/F5, che
    # vale 1 anche giocando (codici fermi): diventa il byte giusto (camera_slider.MAPPA_APERTA)
    import re
    for vecchia, giusta in (("C84DCB75 00000000", "D056B8EC 00000050"), ("C84DCBF5 00000000", "D056B96C 00000050")):
        n = re.sub(rf"(?im)^{giusta}(\r?\n){vecchia}(?=\r?$)", giusta, n)  # tutte e due (prima versione di questa funzione)
        n = re.sub(rf"(?im)^{vecchia}(?=\r?$)", giusta, n)
    for coppia, mappa in (("D4AD1A04 FFFFFFFF|C856B9BB 00000000", "D056B8EC 00000050"),
                          ("D4AD1A04 FFFFFFFF|C856BA3B 00000000", "D056B96C 00000050")):
        a, b = coppia.split("|")
        n = re.sub(rf"(?im)^{a}\r?\n{b}(?!\r?\n(?:0D7FF100|D056B8EC|D056B96C))", f"{a}{nl}{b}{nl}{mappa}", n)
    if n == s:
        return False
    backup_file(f, "GameSettings")
    f.write_bytes(n.encode("utf-8"))
    return True


@_sotto_lock_ini
@_salta_se_uguale([])
def aggiorna_codici_vecchi(ini, gid):
    """I nostri codici rifatti (nel database hanno "vecchi" = i nomi di prima): nell'INI dell'utente il vecchio
    diventa il nuovo, stesso posto e stesso acceso/spento. Senza, l'installer aggiungerebbe il nuovo accanto al vecchio.
    Sistema anche la riga "solo in partita" (aggiorna_riga_partita)."""
    if not Path(ini).is_file():
        return []
    fatti = ["riga_partita"] if aggiorna_riga_partita(ini) else []
    letti = leggi_codici_ini(ini)
    pres, att = letti["presenti"], letti["attivi"]
    for c in carica_codici_db():
        nuove = c["versioni"].get(gid)
        for v in c.get("vecchi", []):
            if v in pres and nuove:
                if c["nome_ini"] in pres:  # c'è già anche il nuovo: tolgo il vecchio (se era acceso, accendo il nuovo)
                    backup_file(ini, "GameSettings")
                    scrivi_codici_ini(ini, [(c["nome_ini"], nuove)] if v in att else [], [(v, True)])
                else:
                    backup_file(ini, "GameSettings")
                    sostituisci_codice(ini, v, c["nome_ini"], nuove)
                fatti.append(c["id"])
        # codice nuovo che prima stava dentro un altro (tuffo con L3 dentro la camera): se l'INI ha l'altro e non questo,
        # lo aggiungo acceso/spento come l'altro (se l'utente lo toglie dopo, il blocco resta e non lo rimetto)
        con = c.get("nuovo_con")
        if con and nuove and c["nome_ini"] not in pres:
            p = next((x for x in carica_codici_db() if x["id"] == con), None)
            if p and p["nome_ini"] in pres:
                backup_file(ini, "GameSettings")
                acceso = p["nome_ini"] in leggi_codici_ini(ini)["attivi"]
                scrivi_codici_ini(ini, [(c["nome_ini"], nuove)], [])
                if not acceso:
                    scrivi_codici_ini(ini, [], [(c["nome_ini"], False)])
                fatti.append(c["id"])
                pres = leggi_codici_ini(ini)["presenti"]
        # pezzi di un altro codice (es. HUD 16:9 dentro "Schermo 16:9"; la camera ha allinea_camera): stessi acceso/spento
        padre = c.get("parte_di")
        p = next((x for x in carica_codici_db() if x["id"] == padre), None) if padre and padre != "camera" else None
        if p and nuove:  # (padre che non è un codice, es. "formato" del 4:3 o "ora": li gestisce Grafica, non si toccano;
            # prima il "4:3" scelto in Grafica veniva spento qui perché il "padre" non c'era)
            att = leggi_codici_ini(ini)["attivi"]
            on, c_on = bool(p and p["nome_ini"] in att), c["nome_ini"] in att
            if on != c_on:
                backup_file(ini, "GameSettings")
                scrivi_codici_ini(ini, [(c["nome_ini"], nuove)] if on else [], [] if on else [(c["nome_ini"], False)])
                fatti.append(c["id"])
                pres = leggi_codici_ini(ini)["presenti"]
        # nostri codici con righe fisse ("aggiorna", es. HUD 16:9): se l'app li ha rifatti, righe nuove al loro posto
        if c.get("aggiorna") and nuove and c["nome_ini"] in pres:
            vecchie = blocco_codice(ini, c["nome_ini"])
            if vecchie is not None and [x.upper() for x in vecchie] != [x.upper() for x in nuove]:
                backup_file(ini, "GameSettings")
                sostituisci_codice(ini, c["nome_ini"], c["nome_ini"], nuove)
                fatti.append(c["id"])
    return fatti


def posizioni_attivi(ini, nomi):
    """{nome: posizione} dei codici accesi (per rimetterli poi esattamente dov'erano, vedi riaccendi_codici)."""
    L, _ = _righe_ini(ini)
    if "[ActionReplay_Enabled]" not in [x.strip() for x in L]:
        return {}
    i, j = _sezione(L, "[ActionReplay_Enabled]")
    return {L[k].strip(): k - i for k in range(i, j) if L[k].strip() in nomi}


def riaccendi_codici(ini, posizioni):
    """Rimette accesi dei codici (già presenti nel file) al loro posto nell'elenco: il file torna com'era."""
    L, nl = _righe_ini(ini)
    if "[ActionReplay_Enabled]" not in [x.strip() for x in L]:
        return
    pres = leggi_codici_ini(ini)["presenti"]
    i, j = _sezione(L, "[ActionReplay_Enabled]")
    elenco = L[i:j]
    gia = {x.strip() for x in elenco}
    for nome, pos in sorted(posizioni.items(), key=lambda x: x[1]):
        if nome in pres and nome not in gia:
            elenco.insert(min(pos, len(elenco)), nome)
    L[i:j] = elenco
    Path(ini).write_bytes(nl.join(L).encode("utf-8"))


def codici_di_serie(exe, gid):
    """Codici che Dolphin porta di serie per Spider-Man 2 (Sys/GameSettings/GK2.ini e <ID>.ini nella cartella del
    programma: es. "$16:9 Widescreen [Vague Rant]" che tocca il FOV, "$60 FPS", "$Freeze Timers"). Sono spenti di base."""
    if not exe:
        return set()
    cart = Path(exe).parent / "Sys" / "GameSettings"
    nomi = set()
    for f in (cart / f"{gid[:3]}.ini", cart / f"{gid}.ini"):
        if f.is_file():
            nomi |= leggi_codici_ini(f)["presenti"]
    return nomi


@_sotto_lock_ini
def spegni_di_serie(dolphin, exe, gid):
    """Se qualcuno ha acceso in Dolphin i codici di serie, li spengo: fanno le stesse cose dei nostri (60 fps, widescreen
    col FOV) e si pestano i piedi. Non li cancello: stanno nei file di Dolphin e tornerebbero a ogni aggiornamento."""
    ini = Path(dolphin) / "GameSettings" / f"{gid}.ini"
    if not ini.is_file():
        return []
    nostri = {c["nome_ini"] for c in carica_codici_db()}
    accesi = leggi_codici_ini(ini)["attivi"] & (codici_di_serie(exe, gid) - nostri)
    if accesi:
        scrivi_codici_ini(ini, [], [(n, False) for n in accesi])
    return sorted(accesi)


_BACKUP_FONTI = {}  # copia di sicurezza -> file da cui viene (backup_file)


def backup_file(f, sotto):
    """Copia di sicurezza di un file di impostazioni (INI, config di Dolphin) in backup/ini/<data e ora>/<sotto>.
    Se nello stesso secondo c'è già una copia di quel file non la sovrascrive: la prima è quella di "prima" (es.
    codici_applica e poi allinea_camera sullo stesso INI). Tiene le ultime 60 cartelle."""
    f = Path(f)
    if not f.exists():
        return
    radice = BACKUP_DIR / "ini"
    d = radice / datetime.now().strftime("%Y-%m-%d_%H-%M-%S") / sotto
    d.mkdir(parents=True, exist_ok=True)
    # stesso nome ma file diverso nello stesso secondo (es. GK2I52.ini dell'installer e quello di Dolphin): "GK2I52 (2).ini"
    fonte, dest, n = str(f.resolve()).lower(), d / f.name, 1
    while dest.exists() and _BACKUP_FONTI.get(str(dest)) != fonte:
        n += 1
        dest = d / f"{f.stem} ({n}){f.suffix}"
    if not dest.exists():
        shutil.copy2(f, dest)
        _BACKUP_FONTI[str(dest)] = fonte
    for vecchia in sorted(p for p in radice.iterdir() if p.is_dir())[:-60]:
        shutil.rmtree(vecchia, ignore_errors=True)


# ---------------------------------------------------------------- HUD e tasti
HUD_FILE = ["tex1_128x256_f1d8cb04d3438079_5a55c588858c7462_9.png",   # anello della vita + icone (file principale)
            "tex1_256x128_8dd88f8cb357c0f1_3ad4489c72e64c7b_9.png",
            "tex1_256x256_29ea9ebc9df81335_3412d67830d81839_9.png"]
HUD_BASE = "HD Vanilla HUD"   # pezzi che una HUD non ha: si prendono da qui (HUD originale in HD)
HUD_EXTRA = ("HD HUD", "Improvments")  # icone migliorate: sempre installate
TASTI_FILE = ["tex1_256x64_fe6c415418c727a5_f16d1da6b65f8214_9.png",   # striscia dei pulsanti
              "tex1_256x256_da303ca840336f30_14.png"]                    # disegno del controller (menu comandi)
TASTI_XBOX = "XBOX 360 Buttons 1"  # unico set col disegno del controller: lo usano tutti i layout Xbox


def _albero(cartella, chiave, nome=None):
    """Come _nodo ma per qualsiasi file chiave (HUD, tasti)."""
    figli = [n for d in sorted(p for p in cartella.iterdir() if p.is_dir())
             if (n := _albero(d, chiave))]
    ha = tex(cartella, chiave) is not None
    if not ha and not figli:
        return None
    return {"nome": pulisci(nome or cartella.name).replace(" (Default)", ""), "default": "(Default)" in cartella.name,
            "path": str(cartella) if ha else None, "figli": figli}


def catalogo_hud(pack):
    base = Path(pack) / "Skins" / "HUDs"
    out = []
    if not base.is_dir():
        return out
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        dentro = sorted(p for p in d.iterdir() if p.is_dir()) if d.name.startswith("1-") else [d]
        gruppo = pulisci(d.name[2:]) if d.name.startswith("1-") else "Collezione"
        for s in dentro:
            n = _albero(s, HUD_FILE[0])
            if n:
                out.append({"id": f"{gruppo}/{s.name}", "gruppo": gruppo, "nome": pulisci(s.name), "albero": n,
                            "default": foglia_default(n), "varianti": conta_foglie(n),
                            "pezzi": sum(tex(s, f) is not None for f in HUD_FILE)})
    out.sort(key=lambda v: (v["gruppo"] != "Collezione", v["gruppo"], v["nome"].lower()))
    return out


def catalogo_tasti(pack):
    base = Path(pack) / "Layout Controller"
    out = []
    if base.is_dir():
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            n = _albero(d, TASTI_FILE[0])
            if n:
                out.append({"id": d.name, "gruppo": "Layout", "nome": d.name, "albero": n, "default": foglia_default(n),
                            "varianti": conta_foglie(n), "xbox": "XBOX" in d.name.upper()})
    return out


def _sorgente_hud(pack, cartella, nome):
    """File `nome` per la HUD in `cartella`: lì, poi nelle cartelle sopra (varianti), poi nella HUD di base."""
    radice = Path(pack) / "Skins" / "HUDs"
    c = Path(cartella)
    while True:
        if tex(c, nome):
            return tex(c, nome)
        if c == radice or radice not in c.parents:
            break
        c = c.parent
    return tex(radice / HUD_BASE, nome)


def _installato(dolphin, nome_file, voci):
    cart = cartelle_texture(dolphin)[0]
    f = tex(cart, nome_file)
    if not f:
        return None
    h = md5_file(f)
    for v in voci:
        for p in foglie(v["albero"]):
            q = tex(p, nome_file)
            if q and md5_file(q) == h:
                return {"id": v["id"], "path": p}
    return {"id": "?", "path": None}


def installate_hud(dolphin, hud, tasti):
    return {"hud": _installato(dolphin, HUD_FILE[0], hud), "tasti": _installato(dolphin, TASTI_FILE[0], tasti)}


def anteprima_png(file, larg=1024, fondo=(13, 15, 22, 255)):
    """Texture con trasparenze su fondo scuro, ridimensionata (cache)."""
    k = _chiave(str(file)) + f"_{larg}" + ("" if fondo == (13, 15, 22, 255) else "_" + "-".join(map(str, fondo)))
    f = CACHE / "img" / f"prev_{k}.png"
    if not f.exists():
        im = Image.open(file).convert("RGBA")
        im.thumbnail((larg, larg), Image.LANCZOS)
        tela = Image.new("RGBA", im.size, fondo)
        tela.alpha_composite(im)
        f.parent.mkdir(parents=True, exist_ok=True)
        tela.convert("RGB").save(f, optimize=True)
    return "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()


def _installa_hud(self, pack, cartella):
    for n in HUD_FILE:  # le icone "Improvments" ora stanno in Spider-Man 2: RE (pagina Texture)
        self.ops.append((_sorgente_hud(pack, cartella, n), n))
        self.fresco.add(n)


def catalogo_disegni():
    """Disegni del controller per Opzioni > Controller (crea_disegni_controller.py): [{id, nome, fam, predefinito, path}]."""
    base = contenuti() / "Controller"
    try:
        dati = json.loads((base / "tasti.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [{"id": k, "nome": v["nome"], "fam": v["fam"], "predefinito": bool(v.get("predefinito")), "path": str(base / "disegni" / f"{k}.dds")}
            for k, v in dati.items() if not k.startswith("_") and (base / "disegni" / f"{k}.dds").is_file()]


# Disegni della versione di prima (sessione 18: linee gialle disegnate DENTRO la texture): l'app li sostituisce da sola
# con quelli nuovi (solo il controller; le linee del gioco le sposta l'app, linee_gioco.py).
VECCHI_DISEGNI = {
    "2f2318932dfd14931be4ab3c3594b29d": "ps2-black", "48981ae3134e0f978691eeed7ace0a15": "ps3-black",
    "b7bd2e2aa70bc3a1c24f0fe4021e7b75": "ps3-black", "f274dc1035dc8096ecc1bf018dbce3d7": "ps4-black",
    "600a3a8beb09dedc9850ba13e2cf70b9": "ps5-ps1edition", "9548ceea246c598ce671b76079fd446a": "ps5-spiderman_edition",
    "478ff465002f8d486ff82519194364aa": "ps5-white", "d3de9561a944d3d8bde5fbfd7fad0e9c": "xbox360-black",
    "52fd17e9ee2f837b25758ced47fc53b5": "xbox360-white", "09a1fa3667d354665ce4c306ed2304c0": "xboxone-black",
    "3492c2d0fa7612bb02fa8f5cbb0787c7": "xboxseries-black", "a8e0ff6e54cb4826fb019201be73a1b6": "xboxseries-white",
}


def aggiorna_disegno_vecchio(dolphin):
    """Se in Dolphin c'è un disegno del controller della versione di prima, lo sostituisco con quello nuovo dello
    stesso controller (copia fresca: Dolphin lo ricarica anche a gioco aperto). Ritorna l'id aggiornato o None."""
    if not dolphin:
        return None
    nuovi = {d["id"]: d for d in catalogo_disegni()}
    fatto = None
    for cart in cartelle_texture(dolphin):
        f = tex(cart, TASTI_FILE[1])
        did = VECCHI_DISEGNI.get(md5_file(f)) if f else None
        if did in nuovi:
            f.unlink()  # mai scrivere dentro: potrebbe essere un collegamento
            shutil.copyfile(nuovi[did]["path"], f.with_suffix(".dds"))
            fatto = did
    return fatto


def famiglia_tasti(cartella):
    """Famiglia di un layout di tasti a schermo: "ps" (PlayStation) o "xbox" (Xbox e gli altri, es. tastiera)."""
    n = Path(str(cartella)).name.upper() if cartella else ""
    return "ps" if any(x in n for x in ("PLAYSTATION", "PS2", "PS3", "PS4", "PS5")) else "xbox"


def disegno_per(cartella_tasti, scelti=None):
    """Il disegno del controller da mettere con questi tasti: quello scelto per la sua famiglia, se no il predefinito."""
    fam = famiglia_tasti(cartella_tasti)
    voci = [d for d in catalogo_disegni() if d["fam"] == fam]
    scelto = (scelti or carica_config().get("disegno_controller", {})).get(fam)
    d = next((x for x in voci if x["id"] == scelto), None) or next((x for x in voci if x["predefinito"]), None) or (voci[0] if voci else None)
    return d


def _installa_tasti(self, pack, cartella, scelti=None):
    c = Path(cartella)
    self.ops.append((tex(c, TASTI_FILE[0]), TASTI_FILE[0]))
    d = disegno_per(c, scelti)
    disegno = Path(d["path"]) if d else tex(c, TASTI_FILE[1])  # disegni nuovi (Series X, PS5...); se mancano, il vecchio 360
    if not disegno:
        xb = tex(Path(pack) / "Layout Controller" / TASTI_XBOX, TASTI_FILE[1])
        disegno = xb if "XBOX" in str(c).upper() else None
    self.ops.append((disegno, TASTI_FILE[1]))
    self.fresco.update(TASTI_FILE[:2])


Installazione.hud = _installa_hud
Installazione.tasti = _installa_tasti


# ---------------------------------------------------------------- impostazioni di Dolphin (grafica, prestazioni)
# chiave dell'app -> (sezione nell'INI del gioco, chiave, tipo, valore di Dolphin se non scritto da nessuna parte).
# Si scrivono nell'INI del gioco (GameSettings/<ID>.ini): valgono solo per Spider-Man 2, gli altri giochi non cambiano.
GRAFICA = {
    "res": ("Video_Settings", "InternalResolution", "int", 1),
    "formato": ("Video_Settings", "AspectRatio", "int", 0),
    "msaa": ("Video_Settings", "MSAA", "msaa", 1),
    "ssaa": ("Video_Settings", "SSAA", "bool", False),
    "aniso": ("Video_Enhancements", "MaxAnisotropy", "int", 0),
    "vsync": ("Video_Hardware", "VSync", "bool", False),
    "backend": ("Core", "GFXBackend", "str", "D3D"),
    "oc_on": ("Core", "OverclockEnable", "bool", False),
    "oc": ("Core", "Overclock", "float", 1.0),
    "shader": ("Video_Settings", "ShaderCompilationMode", "int", 0),
    "attendi": ("Video_Settings", "WaitForShadersBeforeStarting", "bool", False),
    "hd": ("Video_Settings", "HiresTextures", "bool", False),
    "cache": ("Video_Settings", "CacheHiresTextures", "bool", False),
    "fps": ("Video_Settings", "ShowFPS", "bool", False),
    "jit": ("Core", "JITFollowBranch", "bool", True),  # spento su ARM (Android, PC Snapdragon): via gli scatti
    "dual": ("Core", "CPUThread", "bool", True),  # dual core: CPU e GPU emulate in parallelo (spento = metà velocità)
}
# Overclock della CPU emulata secondo il processore: col codice 60 fps la CPU emulata lavora il doppio. Misurato sul
# portatile di prova (Intel di 8a generazione, 2018): 150% = ~48 fps a velocità quasi piena, 300% = ~45 fps ma tempo rallentato al 75%.
# Un portatile recente (es. quello con la RTX 4050) va a 60 fisso anche in 4K con il 300%.
OC_CPU = {"datato": 1.5, "recente": 2.0, "potente": 3.0}


def processore():
    """{"nome", "livello"}: datato (Intel fino alla 9a generazione, Ryzen 1000-2000/3000 portatili), recente (Intel
    10a-11a, Ryzen 3000-4000), potente (Intel 12a in su / Core Ultra, Ryzen 5000 in su / Ryzen AI). Se non lo riconosco: recente."""
    nome = ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            nome = winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
    except OSError:
        pass
    n = re.sub(r"\s+", " ", nome.replace("(R)", "").replace("(TM)", "")).strip()
    n = re.sub(r"\s*(CPU\s*)?@.*$|\s+with Radeon.*$|\s+\d+-Core Processor$", "", n)  # "i5-8250U CPU @ 1.60GHz" -> "i5-8250U"
    liv = "recente"
    u = n.upper()
    m = re.search(r"\bI[3579]-(\d{4,5})", u)
    if "ULTRA" in u and "CORE" in u:
        liv = "potente"
    elif m:
        num = m.group(1)
        gen = int(num[:2]) if len(num) == 5 else int(num[0])
        liv = "potente" if gen >= 12 else "recente" if gen >= 10 else "datato"
    elif "RYZEN" in u:
        if "RYZEN AI" in u:
            liv = "potente"
        else:
            m = re.search(r"RYZEN \d+ (?:PRO )?(\d)(\d{3})(\w*)", u)
            if m:
                serie, fine = int(m.group(1)), m.group(3)
                liv = "potente" if serie >= 5 else "recente" if serie == 4 or (serie == 3 and not fine.startswith("U")) else "datato"
    elif any(x in u for x in ("PENTIUM", "CELERON", "ATOM", "FX-", "A10", "A8-", "A6-")):
        liv = "datato"
    return {"nome": n or "?", "livello": liv}




def leggi_ini(ini):
    """{sezione: {chiave: valore}} (testo grezzo)."""
    out, sez = {}, None
    L, _ = _righe_ini(ini)
    for r in L:
        s = r.strip()
        if s.startswith("[") and s.endswith("]"):
            sez = out.setdefault(s[1:-1], {})
        elif sez is not None and "=" in s and not s.startswith(("$", "#", ";")):
            k, v = s.split("=", 1)
            sez[k.strip()] = v.strip()
    return out


def _da_testo(tipo, v):
    try:
        if tipo == "bool":
            return v.lower() == "true"
        if tipo == "int":
            return int(v)
        if tipo == "msaa":
            return int(v, 16) if v.lower().startswith("0x") else int(v)
        if tipo == "float":
            return round(float(v), 2)
        return v
    except ValueError:
        return None


def _a_testo(tipo, v):
    if tipo == "bool":
        return "True" if v else "False"
    if tipo == "msaa":
        return f"0x{int(v):08x}"
    if tipo == "float":
        return f"{float(v):.8f}"
    return str(int(v)) if tipo == "int" else str(v)


def grafica_valori(dolphin, gid):
    """Valori in vigore per una versione: INI del gioco > impostazioni generali di Dolphin > default di Dolphin."""
    d = Path(dolphin)
    gioco = leggi_ini(d / "GameSettings" / f"{gid}.ini")
    gfx, main = leggi_ini(d / "Config" / "GFX.ini"), leggi_ini(d / "Config" / "Dolphin.ini")
    out = {}
    for k, (sez, chiave, tipo, std) in GRAFICA.items():
        globale = main.get(sez, {}) if sez == "Core" else gfx.get(sez.replace("Video_", ""), {})
        for fonte in (gioco.get(sez, {}), globale):
            if chiave in fonte and _da_testo(tipo, fonte[chiave]) is not None:
                out[k] = _da_testo(tipo, fonte[chiave])
                break
        else:
            out[k] = std
    return out


@_sotto_lock_ini
def scrivi_ini_valori(ini, valori):
    """valori = {(sezione, chiave): testo}. Cambia la riga se c'è, se no la aggiunge in fondo alla sezione;
    una sezione che manca va dopo le altre [Video_*] (o prima di [Core]), senza righe vuote come nei file di John."""
    ini = Path(ini)
    L, nl = _righe_ini(ini)
    for (sez, chiave), testo in valori.items():
        titolo = f"[{sez}]"
        titoli = [x.strip() for x in L]
        if titolo not in titoli:
            dopo = [n for n, x in enumerate(titoli) if x.startswith("[Video_")]
            if dopo:
                _, pos = _sezione(L, titoli[dopo[-1]])
            elif "[Core]" in titoli:
                pos = titoli.index("[Core]")
            else:
                while L and not L[-1].strip():
                    L.pop()
                pos = len(L)
            L[pos:pos] = [titolo, f"{chiave} = {testo}"]
            continue
        i, j = _sezione(L, titolo)
        for n in range(i, j):
            if "=" in L[n] and L[n].split("=", 1)[0].strip() == chiave:
                L[n] = f"{chiave} = {testo}"
                break
        else:
            L.insert(j, f"{chiave} = {testo}")
    if L and L[-1].strip():
        L.append("")
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_bytes(nl.join(L).encode("utf-8"))


def grafica_scrivi(ini, valori):
    """valori = {chiave app: valore} -> scritti nell'INI del gioco nel formato di Dolphin."""
    scrivi_ini_valori(ini, {(GRAFICA[k][0], GRAFICA[k][1]): _a_testo(GRAFICA[k][2], v) for k, v in valori.items() if k in GRAFICA})


def peso_texture(dolphin, prot=frozenset()):
    """RAM usata dal precaricamento delle texture HD (la cartella più grande fra le versioni): i PNG vengono
    decompressi (larghezza x altezza x 4 byte + mipmap), i DDS restano come sono sul disco.
    Ritorna (adesso, se si comprimesse tutto il comprimibile in BC7 = 1 byte a pixel)."""
    def dim(c):
        # os.scandir: su Windows peso e tipo arrivano con l'elenco della cartella (os.walk + getsize = una lettura del
        # disco per file: 8000 file = 0,7 s a ogni apertura di Grafica)
        tot = dopo = 0
        cartelle = [str(c)]
        while cartelle:
            try:
                voci = list(os.scandir(cartelle.pop()))
            except OSError:
                continue
            for e in voci:
                try:
                    if e.is_dir():
                        cartelle.append(e.path)
                    elif e.name.lower().endswith(".png"):
                        with open(e.path, "rb") as fh:
                            testa = fh.read(24)
                        w, h = int.from_bytes(testa[16:20], "big"), int.from_bytes(testa[20:24], "big")
                        tot += w * h * 4 * 4 // 3
                        dopo += w * h * 4 // 3 if w % 4 == 0 and h % 4 == 0 and e.name not in prot else w * h * 4 * 4 // 3
                    else:
                        tot += e.stat().st_size
                        dopo += e.stat().st_size
                except OSError:
                    pass
        return tot, dopo
    base = Path(dolphin) / "Load" / "Textures"
    return max([dim(base / i) for i in ID_GIOCO if (base / i).is_dir()] or [(0, 0)])


def grafica_proprie(dolphin, gid):
    """Chiavi grafiche scritte nell'INI del gioco (le altre arrivano dalle impostazioni generali di Dolphin)."""
    gioco = leggi_ini(Path(dolphin) / "GameSettings" / f"{gid}.ini")
    return [k for k, (sez, chiave, _, _) in GRAFICA.items() if chiave in gioco.get(sez, {})]


HD_RIGA = ("Video_Settings", "HiresTextures")


@_sotto_lock_ini
def accendi_hd(ini):
    """Texture HD (HiresTextures) accese nell'INI del gioco. Su un PC di prova l'INI c'era già con le texture
    spente (Grafica "Personalizzata") e unisci_ini non tocca i valori grafici dell'utente: l'app diceva "mod installata"
    ma il gioco partiva con le texture originali. L'installer e "Prepara tutto" le accendono sempre."""
    ini = Path(ini)
    if (leggi_ini(ini).get(HD_RIGA[0], {}).get(HD_RIGA[1]) or "").lower() == "true":
        return False
    ini.parent.mkdir(parents=True, exist_ok=True)
    scrivi_ini_valori(ini, {HD_RIGA: "True"})
    return True


def grafica_togli(ini):
    """Toglie dall'INI del gioco tutte le impostazioni grafiche dell'app (e le sezioni [Video_*] rimaste vuote):
    il gioco usa di nuovo quelle generali di Dolphin (anche dual core e JIT, che sono righe di GRAFICA). Le altre righe
    ([Core] EnableCheats, overclock, SlotA...) restano."""
    ini = Path(ini)
    if not ini.exists():
        return
    L, nl = _righe_ini(ini)
    via = {(sez, chiave) for sez, chiave, _, _ in GRAFICA.values()} - {HD_RIGA}  # le texture HD restano: sono la mod
    out, sez = [], None
    for r in L:
        s = r.strip()
        if s.startswith("[") and s.endswith("]"):
            sez = s[1:-1]
        elif sez and "=" in s and (sez, s.split("=", 1)[0].strip()) in via:
            continue
        out.append(r)
    L, out = out, []
    for n, r in enumerate(L):  # sezione [Video_*] vuota: via anche il titolo
        s = r.strip()
        if s.startswith("[Video_") and (n + 1 >= len(L) or L[n + 1].strip().startswith("[") or not L[n + 1].strip()):
            continue
        out.append(r)
    ini.write_bytes(nl.join(out).encode("utf-8"))


# ---------------------------------------------------------------- texture personalizzate (cartelloni, giornali, ...)
# Pacchetti di texture "generiche" dentro il pack (es. Movie-Inspired City Ads di Fresh Start / Fantastic, Custom
# Textures di LifeGeeksYT): ogni file ha lo stesso nome di una texture ufficiale di Spider-Man 2: RE, quindi
# installare = copiare sopra, togliere = rimettere quella ufficiale presa da <lingua>/Load/Textures/<ID> del pack.
def cartella_ufficiale(pack):
    """Le texture ufficiali di Spider-Man 2: RE: Textures/RE della libreria fatta dall'installer, oppure
    <lingua>/Load/Textures/<ID> del pack fatto a mano (preferita la cartella USA)."""
    if pack and (Path(pack) / "Textures" / "RE").is_dir():
        return Path(pack) / "Textures" / "RE"
    trovate = []
    for lingua in sorted(p for p in Path(pack).iterdir() if p.is_dir()):
        for gid in ID_GIOCO:
            c = lingua / "Load" / "Textures" / gid
            if c.is_dir():
                trovate.append((gid != "GK2E52", c))
    return min(trovate)[1] if trovate else None


def catalogo_texture(pack):
    """Cartelle sotto Skins con PNG/DDS che non sono skin, ragnatele, HUD, tasti o icone HD della HUD."""
    noti = file_protetti(pack)
    base = Path(pack) / "Skins"
    out = []
    for radice, cartelle, files in os.walk(base):
        cartelle.sort()
        d = Path(radice)
        if {"HUDs", "Webs"} & set(d.relative_to(base).parts):
            continue
        png = sorted({logico(f) for f in files if f.lower().endswith((".png", ".dds"))} - noti)
        if not png:
            continue
        if d.name.startswith("1-LifeGeeksYT"):
            nome, mod, cred = "Custom Textures", "LifeGeeksYT", CREDITI["LifeGeeksYT"]
        else:
            mod = pulisci(d.parent.name)
            nome, cred = d.name, CREDITI.get(mod, ("ModDB", MODDB))
        out.append({"id": d.relative_to(base).as_posix(), "nome": nome, "mod": mod, "path": str(d), "file": png,
                    "crediti": cred[0], "link": cred[1]})
    # ordine: le texture migliorate dell'Update Pack subito dopo RE, la schermata del titolo in fondo
    out.sort(key=lambda v: (0 if "Updated Textures" in v["nome"] else 3 if "Title Screen" in v["nome"] else 2 if "Spider Eyes" in v["nome"] else 1,
                            v["mod"].lower(), v["nome"].lower()))
    return out


def modi_texture(modi, voci):
    """Per pacchetto "tutte" o "nuove": quello scelto dall'utente, altrimenti di base "nuove" per le Updated Textures
    dell'Update Pack (upscale fatti con l'AI: dove rifarebbero RE resta RE, si aggiungono solo le texture in più)."""
    out = dict(modi or {})
    for v in voci:
        if v["id"] not in out and "Updated Textures" in v.get("nome", ""):
            out[v["id"]] = "nuove"
    return out


def file_protetti(pack):
    """Texture gestite dalle altre sezioni (skin, ragnatele, HUD, tasti, icone HD): qui non si toccano."""
    return set(SKIN_FILE.values()) | set(ALT_FILE.values()) | set(RAGNATELE_FILE) | set(HUD_FILE) | set(TASTI_FILE)


def voce_re(pack):
    """Spider-Man 2: RE come "pacchetto": tutte le sue texture tranne quelle delle altre sezioni."""
    uff = cartella_ufficiale(pack)
    if not uff:
        return None
    prot = file_protetti(pack)
    cred = CREDITI["Collezione"]
    return {"id": "re", "nome": "Spider-Man 2: RE", "mod": "RE Mods", "path": str(uff), "crediti": cred[0], "link": cred[1],
            "file": sorted({logico(f.name) for f in os.scandir(uff) if f.is_file() and f.name.lower().endswith((".png", ".dds"))} - prot)}


_MD5 = None  # "percorso|dimensione|data" -> md5, salvato in cache/md5_indice.json (una lettura sola)


def _md5_veloce(cartella, nome, info):
    global _MD5
    if _MD5 is None:
        try:
            _MD5 = json.loads((CACHE / "md5_indice.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _MD5 = {}
    k = f"{cartella}{os.sep}{nome}|{info[0]}|{info[1]}"
    if k not in _MD5:
        _MD5[k] = hashlib.md5((Path(cartella) / nome).read_bytes()).hexdigest()
        _MD5["_nuovi"] = _MD5.get("_nuovi", 0) + 1
    return _MD5[k]


def _salva_md5():
    if _MD5 and _MD5.pop("_nuovi", 0):
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / "md5_indice.json").write_text(json.dumps(_MD5), encoding="utf-8")


def _indice(cartella):
    """{nome logico: (dimensione, data, nome vero)} di una cartella con una lettura sola (scandir dà già le
    dimensioni). Il nome logico è sempre .png anche per i .dds; se ci sono tutti e due vince il .png."""
    out = {}
    if cartella and Path(cartella).is_dir():
        for e in os.scandir(cartella):
            if e.is_file() and e.name.lower().endswith((".png", ".dds")):
                n = logico(e.name)
                if n not in out or e.name == n:
                    st = e.stat()
                    out[n] = (st.st_size, st.st_mtime_ns, e.name)
    return out


AVANZA_TEXTURE = {"fatti": 0, "tot": 0, "fase": ""}  # per la barra della pagina Texture (stato_texture + conta_texture)


def stato_texture(dolphin, pack, voci):
    """Per ogni file (di RE e dei pacchetti): chi c'è adesso in Dolphin. "re" = Spider-Man 2: RE, id di un pacchetto,
    "gioco" = nessun file (texture originale del gioco), "?" = un file che non riconosco. Riconosciuto dal contenuto."""
    cart = cartelle_texture(dolphin)[0]
    uff = cartella_ufficiale(pack)
    i_cart, i_uff = _indice(cart), _indice(uff)
    pacchetti = [(v, _indice(v["path"])) for v in voci if v["id"] != "re"]

    comp = compressi(cart)  # texture già convertite in DDS dall'app: si confronta il PNG da cui vengono

    def uguale(nome, cartella, indice):
        a, b = i_cart.get(nome), indice.get(nome)
        if not b:
            return False
        mb = _md5_veloce(cartella, b[2], b[:2])
        if a and not (nome in comp and a[2] != nome):  # file vero in Dolphin (png o dds dalla libreria)
            return a[0] == b[0] and _md5_veloce(cart, a[2], a[:2]) == mb
        return nome in comp and comp[nome] == mb   # dds fatto dall'app dal png

    proprietario = {}
    nomi = sorted({f for v in voci for f in v["file"]})
    AVANZA_TEXTURE.update(fatti=0, tot=len(nomi) + sum(len(v["file"]) for v in voci if v["id"] != "re"), fase="dolphin")
    for nome in nomi:
        AVANZA_TEXTURE["fatti"] += 1
        if nome not in i_cart and nome not in comp:
            proprietario[nome] = "gioco"
            continue
        chi = "re" if uguale(nome, uff, i_uff) else None  # prima RE
        chi = chi or next((v["id"] for v, iv in pacchetti if nome in v["file"] and uguale(nome, v["path"], iv)), None)
        proprietario[nome] = chi or "?"
    _salva_md5()
    return proprietario


_DIVERSE = None  # firma del pacchetto -> texture diverse da RE (cache/texture_diverse.json)


def _firma_cartella(p):
    """Cambia quando nella cartella si aggiungono o tolgono file (nella libreria un file si toglie prima di riscriverlo)."""
    try:
        st = os.stat(lungo(p))
        return f"{st.st_mtime_ns}"
    except OSError:
        return "?"


def conta_texture(pack, voci, proprietario):
    """Per pacchetto: le texture che cambia davvero (diverse da quella di RE) e quante sono installate adesso.
    Il confronto con RE (impronta di ~1800 file: 3-12 s a ogni apertura della pagina Texture) si rifà solo se le cartelle
    del pacchetto o di RE sono cambiate: il risultato resta in cache (texture_diverse.json)."""
    global _DIVERSE
    uff = cartella_ufficiale(pack)
    f = CACHE / "texture_diverse.json"
    if _DIVERSE is None:
        try:
            _DIVERSE = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _DIVERSE = {}
    out, nuovi = {}, False
    for v in voci:
        if v["id"] == "re":
            diverse = v["file"]
        else:
            k = f"{v['id']}|{corto(v['path'])}|{_firma_cartella(v['path'])}|{_firma_cartella(uff)}|{len(v['file'])}"
            diverse = _DIVERSE.get(k)
            if diverse is None:
                AVANZA_TEXTURE["fase"] = "pacchetti"
                diverse = []
                for n in v["file"]:
                    AVANZA_TEXTURE["fatti"] += 1
                    if not (tex(uff, n) and tex(v["path"], n) and _uguali(tex(uff, n), tex(v["path"], n))):
                        diverse.append(n)
                for vecchia in [x for x in _DIVERSE if x.startswith(v["id"] + "|")]:  # le firme vecchie di questo pacchetto
                    del _DIVERSE[vecchia]
                _DIVERSE[k], nuovi = diverse, True
        out[v["id"]] = {"tot": len(diverse), "attivi": sum(proprietario.get(n) == v["id"] for n in diverse), "diverse": diverse}
    if nuovi:
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            scrivi_sicuro(f, json.dumps(_DIVERSE))
        except OSError:
            pass
    return out


def miniatura_texture(file, lato=360):
    """Texture rimpicciolita senza deformarla, su fondo scuro (cache)."""
    k = _chiave(file) + f"_t{lato}"
    f = CACHE / "img" / f"tex_{k}.jpg"
    if not f.exists():
        im = Image.open(file).convert("RGBA")
        im.thumbnail((lato, lato), Image.LANCZOS)
        tela = Image.new("RGBA", im.size, (24, 28, 40, 255))
        tela.alpha_composite(im)
        f.parent.mkdir(parents=True, exist_ok=True)
        tela.convert("RGB").save(f, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()


def copertina_texture(voce):
    """Mosaico delle texture di un pacchetto (per la scheda)."""
    k = hashlib.md5(("c1|" + "|".join(_chiave(tex(voce["path"], n)) for n in voce["file"][:8])).encode()).hexdigest()
    f = CACHE / "img" / f"copt_{k}.jpg"
    if not f.exists():
        tela = Image.new("RGBA", (480, 240), (24, 28, 40, 255))
        fs = sorted(voce["file"], key=lambda n: -tex(voce["path"], n).stat().st_size)[:6]  # le più ricche prima
        celle = [(0, 0, 240, 240)] if len(fs) == 1 else [(0, 0, 240, 120), (240, 0, 240, 120), (0, 120, 160, 120),
                                                         (160, 120, 160, 120), (320, 120, 160, 120), (0, 0, 0, 0)]
        if len(fs) == 1:
            celle = [(120, 0, 240, 240)]
        for n, (x, y, w, h) in zip(fs, celle):
            if w:
                _incolla_contenuto(tela, Image.open(tex(voce["path"], n)), x + 3, y + 3, w - 6, h - 6)
        f.parent.mkdir(parents=True, exist_ok=True)
        tela.convert("RGB").save(f, "JPEG", quality=86)
    return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()


def _installa_texture(self, pack, voci, scelte):
    """scelte = {nome file: da dove} con "re", "gioco" (= togli il file) o l'id di un pacchetto."""
    per_id = {v["id"]: v for v in voci}
    prot = file_protetti(pack)
    for nome, chi in scelte.items():
        if nome in prot or (chi not in ("gioco",) and (chi not in per_id or nome not in per_id[chi]["file"])):
            continue
        self.ops.append((None if chi == "gioco" else tex(per_id[chi]["path"], nome), nome))


Installazione.texture = _installa_texture


# ---------------------------------------------------------------- aggiungere roba nuova al pack (per i più esperti)
NOME_TEXTURE = re.compile(r"^tex1_\d+x\d+_.+\.(png|dds)$", re.I)
DEST_AGGIUNTE = {  # tipo -> cartella del pack dove finisce
    "skin": ("Skins", "Suit Mods", "1-Aggiunte"), "ragnatele": ("Skins", "Webs"), "hud": ("Skins", "HUDs"),
    "tasti": ("Layout Controller",), "texture": ("Skins", "Custom Textures"),
}


def _estrattori():
    """Programmi per rar/7z presenti sul PC, in ordine di preferenza."""
    return [Path(p) for p in (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe",
                              r"C:\Program Files\WinRAR\UnRAR.exe", r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
                              os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe"))  # Windows 10/11: apre anche rar e 7z
            if Path(p).is_file()]


def _estrattore():
    e = _estrattori()
    return e[0] if e else None


def _args_estrai(exe, archivio, dest):
    """Riga di comando per 7-Zip, UnRAR o il tar di Windows (gli altri programmi vogliono percorsi senza \\?\)."""
    archivio, dest = corto(archivio), corto(dest)
    if exe.name.lower() == "7z.exe":
        return [str(exe), "x", "-y", f"-o{dest}", archivio]
    if exe.name.lower() == "tar.exe":
        Path(dest).mkdir(parents=True, exist_ok=True)
        return [str(exe), "-x", "-f", archivio, "-C", dest]
    return [str(exe), "x", "-y", archivio, dest + os.sep]


def prepara_aggiunta(percorso):
    """Cartella da analizzare: se è un archivio lo estrae in cache (zip sempre; rar/7z con 7-Zip o WinRAR)."""
    p = Path(percorso)
    if p.is_dir():
        return p
    base = lungo(CACHE / "aggiunta")  # percorsi lunghi: dentro gli archivi di skin (Fresh Start) si superano i 260 caratteri
    for vecchia in base.glob("*") if base.is_dir() else []:  # pulizia (i file estratti da un rar possono essere in sola lettura)
        _rimuovi(vecchia)
    dest = base / datetime.now().strftime("%H%M%S%f")
    dest.mkdir(parents=True)
    _estrai(p, dest)  # zip con Python, rar/7z con 7-Zip, WinRAR o il tar di Windows (prima qui gli argomenti di UnRAR
    # andavano anche a tar.exe: sui PC senza 7-Zip/WinRAR aggiungere un .rar falliva)
    return dest


def analizza_aggiunta(cartella, pack=None):
    """Cosa c'è dentro: skin, ragnatele, HUD, tasti o pacchetto di texture (o niente di Dolphin)."""
    cartella = Path(corto(cartella))
    trovate, altri, dove = [], 0, set()
    for radice, _, files in os.walk(lungo(cartella)):  # (senza prefisso os.walk salta in silenzio le cartelle oltre 260)
        for f in files:
            if NOME_TEXTURE.match(f):
                trovate.append(logico(f))
                dove.add(Path(corto(radice)))
            elif f.lower().endswith((".png", ".dds", ".jpg")):
                altri += 1
    nomi = set(trovate)
    corpo = {CORPO, ALT_FILE["corpo"]}
    if nomi & corpo:
        tipo = "skin"
    elif len(nomi & set(RAGNATELE_FILE)) >= 2:
        tipo = "ragnatele"
    elif HUD_FILE[0] in nomi:
        tipo = "hud"
    elif TASTI_FILE[0] in nomi:
        tipo = "tasti"
    elif nomi:
        tipo = "texture"
    else:
        tipo = "vuoto"
    radice = Path(os.path.commonpath([str(d) for d in dove])) if dove else cartella  # la cartella giusta, senza gusci
    noti = set()
    uff = cartella_ufficiale(pack) if pack else None
    if uff and tipo == "texture":
        noti = {e.name for e in os.scandir(uff)}
    varianti = sum(1 for d in dove if tex(lungo(d), CORPO)) if tipo == "skin" else 0
    hud = sorted(str(d) for d in dove if tex(lungo(d), HUD_FILE[0])) if tipo == "skin" else []
    protetti = set(SKIN_FILE.values()) | set(ALT_FILE.values()) | set(RAGNATELE_FILE) | set(HUD_FILE) | set(TASTI_FILE)
    extra_tex = tipo == "skin" and any(f not in protetti for f in nomi)
    nome = radice.name if radice.parent != CACHE / "aggiunta" else ""  # archivio senza cartella dentro: nome dal file
    return {"tipo": tipo, "radice": str(radice), "nome": pulisci(nome) if tipo == "skin" else nome, "n": len(trovate),
            "cartelle": len(dove), "nuove": len(nomi - noti) if noti else 0, "noti": len(nomi & noti), "altri": altri, "varianti": varianti,
            "hud": hud, "extra_tex": extra_tex}


def aggiungi_al_pack(pack, radice, tipo, nome, hud=()):
    """Copia la cartella nel posto giusto del pack (le HUD dentro una mod di skin vanno anche fra le HUD)."""
    nome = re.sub(r'[<>:"/\|?*]', "", nome).strip().rstrip(".")
    if not nome:
        raise ValueError("nome")
    dest = Path(pack).joinpath(*DEST_AGGIUNTE[tipo]) / nome
    if dest.exists():
        raise FileExistsError("esiste")
    solo_texture = lambda d, fs: [f for f in fs if (Path(d) / f).is_file() and not f.lower().endswith((".png", ".dds"))]
    try:  # percorsi lunghi da tutte e due le parti; se si ferma a metà non resta una copia mezza (poi "esiste")
        shutil.copytree(lungo(radice), lungo(dest), ignore=solo_texture)
    except Exception:
        _rimuovi(lungo(dest))
        raise
    for h in hud:
        dh = Path(pack).joinpath(*DEST_AGGIUNTE["hud"]) / Path(h).name
        if not dh.exists():
            try:
                shutil.copytree(lungo(h), lungo(dh), ignore=solo_texture)
            except Exception:
                _rimuovi(lungo(dh))
                raise
    return dest


# ---------------------------------------------------------------- compressione delle texture (PNG -> DDS BC7)
# In RAM i PNG vengono decompressi (4 byte a pixel); i DDS BC7 restano compressi (1 byte a pixel) e Dolphin li carica
# senza decodificarli. Si comprimono solo le texture di RE e dei pacchetti (skin, ragnatele, HUD e tasti restano PNG,
# così le altre sezioni li riconoscono come prima). Il PNG originale va in un archivio (per md5) per poter tornare indietro.
MANIFESTO = CONF_DIR / "compressione.json"   # {cartella: {nome.png: {"md5": md5 del png, "dim": byte dds, "data": mtime dds}}}
ARCHIVIO_PNG = CONF_DIR / "png_originali"     # <md5>.png
_MAN = None


def texconv():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    p = base / "tools" / "texconv.exe"
    return p if p.is_file() else None


def manifesto():
    global _MAN
    if _MAN is None:
        try:
            _MAN = json.loads(MANIFESTO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _MAN = {}
    return _MAN


def salva_manifesto():
    """Sotto _BLOCCO_MAN: i fili della compressione lo cambiano mentre si salva ("dict changed size")."""
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    with _BLOCCO_MAN:
        dati = json.dumps(manifesto())
        scrivi_sicuro(MANIFESTO, dati)  # dentro il blocco: due salvataggi insieme non si accavallano


def compressi(cart):
    """{nome.png: md5 del png originale} dei DDS fatti dall'app ancora intatti in quella cartella."""
    m = manifesto().get(str(cart), {})
    out = {}
    for nome, e in m.items():
        dds = Path(cart) / (nome[:-4] + ".dds")
        try:
            st = dds.stat()
        except OSError:
            continue
        if st.st_size == e["dim"] and st.st_mtime_ns == e["data"]:
            out[nome] = e["md5"]
    return out


def _dimensioni_png(p):
    with open(p, "rb") as fh:
        t = fh.read(24)
    return int.from_bytes(t[16:20], "big"), int.from_bytes(t[20:24], "big")


def da_comprimere(dolphin, pack, solo=None):
    """[(cartella, nome.png)] che si possono comprimere (dimensioni multiple di 4, non gestite da altre sezioni)."""
    prot = file_protetti(pack) if pack else set()
    out = []
    for cart in cartelle_texture(dolphin):
        if not cart.is_dir():
            continue
        for e in os.scandir(cart):
            n = e.name
            if not n.lower().endswith(".png") or n in prot or (solo is not None and n not in solo):
                continue
            try:
                w, h = _dimensioni_png(e.path)
            except OSError:
                continue
            if w % 4 == 0 and h % 4 == 0:
                out.append((cart, n))
    return out


def _ritenta(fn, volte=8):
    """Windows a volte tiene un file occupato per un attimo (antivirus, indicizzazione): riprovo un po'."""
    import time
    for i in range(volte):
        try:
            return fn()
        except PermissionError:
            if i == volte - 1:
                raise
            time.sleep(0.25 * (i + 1))


class Compressione:
    """Lavoro in sottofondo con avanzamento (lo legge la pagina)."""

    def __init__(self, dolphin, pack, solo=None, indietro=False):
        self.dolphin, self.pack, self.solo, self.indietro = dolphin, pack, solo, indietro
        self.fatti, self.totale, self.finito, self.errore, self.annulla, self.falliti = 0, 0, False, None, False, 0

    def stato(self):
        return {"fatti": self.fatti - self.falliti, "falliti": self.falliti, "totale": self.totale, "finito": self.finito,
                "errore": self.errore, "indietro": self.indietro}

    def esegui(self):
        try:
            self._decomprimi() if self.indietro else self._comprimi()
        except Exception as e:  # noqa: BLE001
            import traceback
            log_errore(traceback.format_exc())
            self.errore = f"{type(e).__name__}: {e}"
        finally:
            salva_manifesto()
            self.finito = True

    def _comprimi(self):
        import subprocess
        from concurrent.futures import ThreadPoolExecutor
        exe = texconv()
        if not exe:
            raise RuntimeError("texconv")
        lista = da_comprimere(self.dolphin, self.pack, self.solo)
        self.totale = len(lista)
        man = manifesto()
        tmp = Path(self.dolphin) / "Load" / "_spidey_dds_tmp"  # non in AppData: il Python dello Store la "dirotta"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        ARCHIVIO_PNG.mkdir(parents=True, exist_ok=True)
        # stesso contenuto in più cartelle (es. GK2E52 e GK2I52): si converte una volta sola
        per_md5 = {}
        for cart, n in lista:
            st = (cart / n).stat()
            per_md5.setdefault(_md5_veloce(cart, n, (st.st_size, st.st_mtime_ns)), []).append((cart, n))
        _salva_md5()
        lavori = list(per_md5.items())

        def converti(blocco):
            d = tmp / f"b{id(blocco)}"
            d.mkdir(parents=True, exist_ok=True)
            elenco = d / "lista.txt"
            elenco.write_text("\n".join(str(copie[0][0] / copie[0][1]) for _, copie in blocco), encoding="utf-8")
            subprocess.run([str(exe), "-nologo", "-y", "-f", "BC7_UNORM", "-m", "0", *texconv_args(), "-o", str(d), "-flist", str(elenco)],
                           capture_output=True, creationflags=0x08000000, env=ambiente_figli())
            for md5, copie in blocco:
                if self.annulla:
                    return
                cart0, n0 = copie[0]
                dds = d / (n0[:-4] + ".dds")
                if not dds.is_file():
                    self.fatti += len(copie)
                    self.falliti += len(copie)
                    continue
                arch = ARCHIVIO_PNG / f"{md5}.png"
                if not arch.is_file():
                    shutil.copyfile(cart0 / n0, arch)
                for cart, n in copie:
                    dest = cart / (n[:-4] + ".dds")
                    try:
                        if dest.exists():
                            dest.unlink()
                        _ritenta(lambda: shutil.copyfile(dds, dest))
                        _ritenta((cart / n).unlink)  # il PNG va via solo se il DDS è a posto
                    except OSError:  # file bloccato (antivirus, Dolphin...): resta il PNG
                        try:
                            dest.unlink()
                        except OSError:
                            pass
                        self.fatti += 1
                        self.falliti += 1
                        continue
                    st = dest.stat()
                    with _BLOCCO_MAN:
                        man.setdefault(str(cart), {})[n] = {"md5": md5, "dim": st.st_size, "data": st.st_mtime_ns}
                    self.fatti += 1
            with _BLOCCO_MAN:  # salvato a ogni blocco: se l'app si chiude a metà, i DDS fatti restano riconosciuti
                salva_manifesto()
            shutil.rmtree(d, ignore_errors=True)

        blocchi = [lavori[i:i + 40] for i in range(0, len(lavori), 40)]
        with ThreadPoolExecutor(TEXCONV_PROCESSI) as ex:
            for _ in ex.map(converti, blocchi):
                if self.annulla:
                    break
        shutil.rmtree(tmp, ignore_errors=True)
        if self.falliti and self.falliti == self.totale:
            raise RuntimeError("texconv non ha convertito niente")

    def _decomprimi(self):
        man = manifesto()
        voci = [(Path(c), n, e) for c, d in man.items() for n, e in d.items()]
        self.totale = len(voci)
        for cart, n, e in voci:
            if self.annulla:
                break
            dds, arch = cart / (n[:-4] + ".dds"), ARCHIVIO_PNG / f"{e['md5']}.png"
            if dds.is_file() and arch.is_file():
                try:
                    _ritenta(lambda: shutil.copyfile(arch, cart / n))
                    _ritenta(dds.unlink)
                except OSError:  # file bloccato: resta il DDS (riprova la prossima volta)
                    self.fatti += 1
                    self.falliti += 1
                    continue
            if arch.is_file() or not dds.is_file():
                man[str(cart)].pop(n, None)
            self.fatti += 1
        # archivio dei PNG: via quelli che non servono più
        usati = {e["md5"] for d in man.values() for e in d.values()}
        for p in ARCHIVIO_PNG.glob("*.png") if ARCHIVIO_PNG.is_dir() else []:
            if p.stem not in usati:
                p.unlink()


# Prove (80 texture, scheda video): normale 13 s, "-bc q" 2,9 s; qualità media 47 contro 45 dB (sopra 40 = invisibile).
TEXCONV_EXTRA = ["-bc", "q", "--ignore-srgb"]  # ignore-srgb: senza, i PNG con gamma/sRGB diventano scurissimi
TEXCONV_PROCESSI = 3
_TEXCONV_GPU = []  # [risultato di texconv_gpu()], calcolato una volta per avvio dell'app


def texconv_gpu():
    """Quale scheda video usa texconv per il BC7: {"args": [...], "gpu": nome o None, "s": secondi della prova}.
    Misurato (150 texture, i7-8750H): scheda video 4,6 s, solo processore 61 s (12 volte di più). Se la scheda 0 non va
    texconv ripiega da solo sul processore, e su alcuni PC la 0 è la "Microsoft Basic Render" (software, 4 volte più lenta
    di una vera): provo le schede 0-3 su una texture piccola e tengo la più veloce; nessuna = processore (gpu None)."""
    if _TEXCONV_GPU:
        return _TEXCONV_GPU[0]
    import subprocess
    import tempfile
    import time
    meglio = {"args": ["-nogpu"], "gpu": None, "s": None}
    exe = texconv()
    if exe:
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "prova.png"
            im = Image.new("RGBA", (512, 512))
            im.putdata([(x % 251, (x * 7) % 253, (x * 13) % 255, 255 - x % 200) for x in range(512 * 512)])
            im.save(img)
            for n in range(4):
                t = time.time()
                try:
                    r = subprocess.run([str(exe), "-nologo", "-y", "-f", "BC7_UNORM", "-m", "0", *TEXCONV_EXTRA, "-gpu", str(n),
                                        "-o", d, str(img)], capture_output=True, text=True, timeout=30,
                                       creationflags=0x08000000, env=ambiente_figli())
                except (OSError, subprocess.SubprocessError):
                    continue
                s = time.time() - t
                m = re.search(r'DirectCompute[^"]*"([^"]+)"', r.stdout or "")
                if not m or "basic render" in m.group(1).lower() or not (Path(d) / "prova.dds").is_file():
                    continue  # quella scheda non c'è / è il software di Windows / non ha convertito
                if meglio["s"] is None or s < meglio["s"]:
                    meglio = {"args": ["-gpu", str(n)], "gpu": m.group(1), "s": round(s, 2)}
                (Path(d) / "prova.dds").unlink()
    _TEXCONV_GPU.append(meglio)
    return meglio


def texconv_args():
    """Opzioni di texconv per il BC7 su questo PC (qualità rapida + scheda video più veloce, se c'è)."""
    return TEXCONV_EXTRA + texconv_gpu()["args"]
_BLOCCO_MAN = __import__("threading").RLock()  # rientrante: salva_manifesto lo prende anche se il chiamante lo ha già


# ---------------------------------------------------------------- libreria dagli archivi di ModDB (installer)
def carica_moddb():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return json.loads((base / "moddb_catalogo.json").read_text(encoding="utf-8"))


def cartella_download():
    """La cartella Download vera di Windows (anche se spostata)."""
    if DA_ZERO:
        return BASE_PROVA / "Download"
    try:
        import uuid
        guid = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")
        buf = ctypes.c_wchar_p()
        g = (ctypes.c_byte * 16).from_buffer_copy(guid.bytes_le)
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(buf)) == 0:
            p = Path(buf.value)
            ctypes.windll.ole32.CoTaskMemFree(buf)
            return p
    except (AttributeError, OSError, ValueError):
        pass
    return Path.home() / "Downloads"


def cartelle_download_browser():
    """Le cartelle di download impostate nei browser (Chrome, Edge, Brave, Opera, Firefox): spesso non sono la
    cartella Download di Windows (es. Chrome che scarica in un'altra cartella)."""
    if DA_ZERO:
        return []
    import glob
    loc, roam = os.environ.get("LOCALAPPDATA", ""), os.environ.get("APPDATA", "")
    pref = [os.path.join(loc, "Google", "Chrome", "User Data", "*", "Preferences"),
            os.path.join(loc, "Microsoft", "Edge", "User Data", "*", "Preferences"),
            os.path.join(loc, "BraveSoftware", "Brave-Browser", "User Data", "*", "Preferences"),
            os.path.join(roam, "Opera Software", "Opera Stable", "Preferences"),
            os.path.join(roam, "Opera Software", "Opera GX Stable", "Preferences")]
    out = []
    for pat in pref:
        for f in glob.glob(pat):
            try:
                d = json.loads(Path(f).read_text(encoding="utf-8")).get("download", {}).get("default_directory")
            except (OSError, ValueError):
                continue
            if d and d not in out:
                out.append(d)
    for f in glob.glob(os.path.join(roam, "Mozilla", "Firefox", "Profiles", "*", "prefs.js")):
        try:
            m = re.search(r'"browser\.download\.dir",\s*"([^"]+)"', Path(f).read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if m:
            d = m.group(1).replace("\\\\", "\\")
            if d not in out:
                out.append(d)
    return out


def cerca_archivi(cartelle=()):
    """{id: percorso} degli archivi del catalogo ModDB già scaricati (nome giusto, o rinominati dal browser tipo
    "file (1).zip"), controllati con dimensione e MD5. Cerca in Download, Desktop e nelle cartelle date."""
    cat = carica_moddb()["file"]
    dove = [cartella_download(), *[Path(c) for c in cartelle_download_browser()], *([] if DA_ZERO else [Path.home() / "Desktop"]),
            *[Path(c) for c in cartelle if c]]
    trovati = {}
    for d in dove:
        if not d.is_dir():
            continue
        try:
            voci = list(os.scandir(d))
        except OSError:
            continue
        for e in voci:
            if not e.is_file():
                continue
            try:
                dim = e.stat().st_size
            except OSError:
                continue
            for c in cat:
                if c["id"] in trovati or dim != c["byte"]:
                    continue
                stem, est = Path(c["file"]).stem, Path(c["file"]).suffix
                if e.name == c["file"] or (e.name.startswith(stem) and e.name.endswith(est)):
                    if md5_file(e.path) == c["md5"]:
                        trovati[c["id"]] = e.path
    return trovati


def _estrai(archivio, dest, avanza=None, ferma=None):
    """avanza(frazione 0-1) durante l'estrazione (per la barra: un archivio grande ci mette minuti); ferma() = annulla."""
    archivio = Path(archivio)
    if archivio.suffix.lower() == ".zip":
        import zipfile
        with zipfile.ZipFile(archivio) as z:
            membri = z.infolist()
            tot, fatto = sum(m.file_size for m in membri) or 1, 0
            for m in membri:
                if ferma and ferma():
                    return
                z.extract(m, lungo(dest))
                fatto += m.file_size
                if avanza:
                    avanza(fatto / tot)
        return
    exes = _estrattori()
    if not exes:
        raise RuntimeError("estrattore")
    import subprocess
    import tempfile
    import time
    peso = max(1, archivio.stat().st_size)
    errori = []
    # se uno fallisce si prova il successivo: i rar di ModDB sono RAR5 e un 7-Zip vecchio (prima del 2015) non li apre
    # (un utente: "CalledProcessError ... exit status 2"); il tar di Windows sì
    for exe in exes:
        if errori and Path(lungo(dest)).is_dir():  # via i pezzi lasciati dal tentativo prima
            for x in Path(lungo(dest)).iterdir():
                _rimuovi(x)
        with tempfile.TemporaryFile() as err:
            pr = subprocess.Popen(_args_estrai(exe, archivio, dest), stdout=subprocess.DEVNULL, stderr=err,
                                  creationflags=0x08000000, env=ambiente_figli())
            while pr.poll() is None:  # rar/7z: quanto è già uscito rispetto al peso dell'archivio (le texture si comprimono poco)
                time.sleep(0.7)
                if ferma and ferma():
                    pr.kill()
                    return
                if avanza:
                    uscito = sum(f.stat().st_size for f in Path(lungo(dest)).rglob("*") if f.is_file())
                    avanza(min(0.97, uscito / peso))
            if not pr.returncode:
                if errori:
                    log_errore(f"estrazione di {archivio.name}: riuscita con {exe.name} dopo {'; '.join(errori)}")
                return
            err.seek(0)
            testo = " ".join(err.read()[-400:].decode("utf-8", "replace").split())
            errori.append(f"{exe.name} codice {pr.returncode}: {testo}")
    log_errore(f"estrazione di {archivio.name} fallita: {' | '.join(errori)}")
    raise RuntimeError(f"estrazione di {archivio.name} fallita ({' | '.join(errori)[:300]})")


def _copia_texture(src, dest, avanza=None):
    """Copia l'albero tenendo solo le texture; se nella destinazione c'era la stessa texture nell'altro formato
    (png/dds) la toglie, così non restano doppioni. avanza(frazione) per la barra."""
    n = 0
    tot = sum(1 for _, _, fs in os.walk(src) for f in fs if f.lower().endswith((".png", ".dds"))) if avanza else 0
    for radice, _, files in os.walk(src):
        rel = Path(radice).relative_to(src)
        for f in files:
            if not f.lower().endswith((".png", ".dds")):
                continue
            d = Path(dest) / rel
            d.mkdir(parents=True, exist_ok=True)
            altro = d / (f[:-4] + (".dds" if f.lower().endswith(".png") else ".png"))
            if altro.is_file():
                altro.unlink()
            if (d / f).exists():  # mai scrivere dentro un file esistente: potrebbe essere un doppione collegato
                (d / f).unlink()
            shutil.copyfile(Path(radice) / f, d / f)
            n += 1
            if avanza and tot and n % 25 == 0:
                avanza(n / tot)
    return n


def _rimuovi(p):
    """Cancella una cartella anche con file in sola lettura (estratti dai rar)."""
    import stat
    if Path(p).exists():
        shutil.rmtree(p, onerror=lambda fn, q, _: (os.chmod(q, stat.S_IWRITE), fn(q)) if os.path.exists(q) else None)


def deduplica(cartella):
    """File identici (stessa dimensione e md5) -> un file solo con più nomi (hard link NTFS): per l'app e per
    Dolphin restano file normali, sul disco occupano lo spazio di uno. Byte risparmiati (0 se il disco non li
    supporta). Chi scrive nella libreria deve sempre togliere il file prima (vedi _copia_texture)."""
    gruppi = {}
    for radice, _, files in os.walk(cartella):
        for f in files:
            if f.lower().endswith((".png", ".dds")):
                p = Path(radice) / f
                try:
                    st = p.stat()
                except OSError:
                    continue
                gruppi.setdefault(st.st_size, []).append(p)
    risparmio = 0
    for dim, lista in gruppi.items():
        if len(lista) < 2:
            continue
        per_md5 = {}
        for p in lista:
            per_md5.setdefault(md5_file(p), []).append(p)
        for copie in per_md5.values():
            primo = copie[0]
            for p in copie[1:]:
                try:
                    if os.path.samefile(primo, p):
                        continue
                    tmp = p.with_name(p.name + ".link")
                    os.link(primo, tmp)
                    os.replace(tmp, p)
                    risparmio += dim
                except OSError:  # disco senza hard link (FAT/exFAT) o file bloccato: resta la copia
                    pass
    return risparmio


# Correzioni nostre a texture del gioco (contenuti/Correzioni, PNG e DDS tinta unita fatti da noi). Vincono anche sulle
# versioni di RE e dell'Update Pack, che hanno lo stesso nome: le metto al loro posto nella libreria (così la pagina
# Texture le conta come quelle del pacchetto) e nelle cartelle texture di Dolphin.
# - 8x8 4b909b163329f9d4: materiale BIANCO dei palazzi "da lontano" (modello semplificato) usato solo nella mappa del gioco:
#   nella mappa 3D il palazzo dove parte il salvataggio 100% (150, 617) e qualche tetto in centro erano bianchi e da
#   vicino tornavano grigi (John). Mai visto giocando. Grigio misurato sul palazzo visto da vicino.
CORREZIONI_TEXTURE = ("tex1_8x8_m_4b909b163329f9d4_fa305e54519ce1da_9",)


def correggi_texture(libreria=None, dolphin=None):
    """Mette le correzioni dove serve (libreria: al posto del file con lo stesso nome, png o dds come quello che c'è;
    Dolphin: nelle cartelle Load/Textures/<ID> se lì c'è quella texture). Ritorna quanti file ha cambiato."""
    import stat
    src = contenuti() / "Correzioni"
    nomi = {b + e: b for b in CORREZIONI_TEXTURE for e in (".png", ".dds")}
    fatti = 0

    def metti(p):
        nonlocal fatti
        nuovo = src / (nomi[p.name] + p.suffix.lower())
        if not nuovo.is_file() or md5_file(p) == md5_file(nuovo):
            return
        try:  # prima tolgo il file (spesso è un hard link: mai scrivere dentro), anche se in sola lettura
            os.chmod(p, stat.S_IWRITE)
        except OSError:
            pass
        p.unlink()
        shutil.copyfile(nuovo, p)  # data di adesso: Dolphin la ricarica anche a gioco aperto
        fatti += 1
    if libreria and Path(libreria).is_dir():
        for radice, cartelle, files in os.walk(lungo(libreria)):
            cartelle[:] = [c for c in cartelle if c != "_t"]
            for f in files:
                if f in nomi:
                    metti(Path(radice) / f)
    if dolphin:
        for cart in cartelle_texture(dolphin):
            for b in CORREZIONI_TEXTURE:
                p = tex(cart, b + ".png")
                if p:
                    metti(p)
    return fatti


class Libreria:
    """Costruisce (o aggiorna) la libreria dagli archivi di ModDB: estrae, mette ogni cartella al suo posto
    (ricetta in moddb_catalogo.json), poi converte in DDS e toglie i PNG. In sottofondo, con avanzamento."""

    def __init__(self, libreria, archivi, formato="dds", cancella_archivi=False):
        self.libreria, self.archivi, self.formato, self.cancella = lungo(libreria), dict(archivi), formato, cancella_archivi
        self.fase, self.fatti, self.totale, self.finito, self.errore, self.annulla, self.falliti = "", 0, 0, False, None, False, 0
        self.pct, self.sub = 0.0, None  # pct = avanzamento di tutto il passo (0-1), sub = dentro il pacchetto attuale (0-1)

    def stato(self):
        return {"fase": self.fase, "fatti": self.fatti, "totale": self.totale, "finito": self.finito, "errore": self.errore,
                "falliti": self.falliti, "pct": self.pct, "sub": self.sub}

    def esegui(self):
        try:
            self._costruisci()
        except Exception as e:  # noqa: BLE001
            import traceback
            log_errore(traceback.format_exc())
            self.errore = f"{type(e).__name__}: {e}"
        finally:
            self.finito = True

    def _costruisci(self):
        cat = {c["id"]: c for c in carica_moddb()["file"]}
        ordine = sorted(self.archivi, key=lambda i: (not cat[i].get("obbligatorio"), bool(cat[i].get("aggiorna"))))
        self.libreria.mkdir(parents=True, exist_ok=True)
        tmp = self.libreria / "_t"
        info = self._leggi_info()
        self.totale = len(ordine)
        _rimuovi(tmp)
        try:
            self._archivi_in_libreria(ordine, cat, tmp, info)
        finally:  # anche con Annulla o un errore: _t (anche GB) non resta nella libreria (C: è spesso quasi pieno)
            _rimuovi(tmp)
        if self.annulla:
            return
        extra = self.libreria / "Skins" / "HUDs" / HUD_EXTRA[0] / HUD_EXTRA[1]
        if extra.is_dir():  # icone migliorate della HD HUD: fanno parte di Spider-Man 2: RE (pagina Texture, con RE)
            _copia_texture(extra, self.libreria / "Textures" / "RE")
        correggi_texture(self.libreria)  # le nostre correzioni al posto delle texture con lo stesso nome (es. palazzi bianchi)
        if self.formato == "dds":
            self._comprimi_tutto()
            if self.annulla:  # niente doppioni, formato "dds" e zip cancellati se hai annullato a metà
                return
        self.fase = "doppioni"
        self.pct, self.sub = 0.96, None
        info["risparmio_doppioni"] = deduplica(self.libreria)
        self.pct = 1.0
        info["formato"] = self.formato
        self._scrivi_info(info)
        if self.cancella:
            for p in self.archivi.values():
                try:
                    Path(p).unlink()
                except OSError:
                    pass

    def _archivi_in_libreria(self, ordine, cat, tmp, info):
        """Estrae ogni archivio in _t e ne copia le cartelle della ricetta nella libreria (barra a peso)."""
        # la barra va a peso: RE (1,4 GB) conta molto più di una skin da 1 MB. Estrarre = 70%, copiare = 30%;
        # se poi c'è la compressione in DDS, gli archivi valgono metà barra e la compressione l'altra metà
        pesi = {i: max(1, Path(self.archivi[i]).stat().st_size) for i in ordine}
        tot_peso, fatto_peso = sum(pesi.values()), 0
        quota = 0.5 if self.formato == "dds" else 0.95

        def segna(i, x):  # x = frazione del pacchetto i
            self.sub = x
            self.pct = quota * (fatto_peso + pesi[i] * x) / tot_peso
        for i in ordine:
            if self.annulla:
                return
            c = cat[i]
            self.fase = "estraggo:" + c["nome"]
            segna(i, 0.0)
            dove = tmp / i  # una cartella per archivio: Windows non libera subito quelle appena cancellate
            dove.mkdir(parents=True, exist_ok=True)
            _estrai(self.archivi[i], dove, lambda x, i=i: segna(i, 0.7 * x), lambda: self.annulla)
            if self.annulla:
                return
            self.fase = "copio:" + c["nome"]
            ric = [(dove / da if da else dove, a) for da, a in c["ricetta"]]
            ric = [(src, a) for src, a in ric if src.is_dir()]
            for k, (src, a) in enumerate(ric):
                _copia_texture(src, self.libreria / a, lambda x, i=i, k=k: segna(i, 0.7 + 0.3 * (k + x) / len(ric)))
            fatto_peso += pesi[i]
            segna(i, 1.0)
            _rimuovi(dove)
            info["componenti"][i] = {"md5": c["md5"], "file": c["file"], "data": datetime.now().strftime("%Y-%m-%d")}
            self._scrivi_info(info)
            self.fatti += 1

    def _comprimi_tutto(self):
        """Tutti i PNG della libreria -> DDS BC7 (stesso contenuto in più posti = convertito una volta sola)."""
        import subprocess
        from concurrent.futures import ThreadPoolExecutor
        exe = texconv()
        if not exe:
            raise RuntimeError("texconv")
        self.fase = "comprimo"
        per_md5 = {}
        for radice, _, files in os.walk(self.libreria):
            for f in files:
                if not f.lower().endswith(".png"):
                    continue
                p = Path(radice) / f
                try:
                    w, h = _dimensioni_png(p)
                except OSError:
                    continue
                if w % 4 == 0 and h % 4 == 0:
                    per_md5.setdefault(md5_file(p), []).append(p)
        lavori = list(per_md5.values())
        self.fatti, self.totale = 0, sum(len(x) for x in lavori)
        self.sub = None
        tmp = self.libreria / "_spidey_dds_tmp"
        shutil.rmtree(tmp, ignore_errors=True)

        def converti(blocco):
            d = tmp / f"b{id(blocco)}"
            d.mkdir(parents=True, exist_ok=True)
            elenco = d / "lista.txt"
            # stesso nome con contenuti diversi (es. il corpo di ogni skin): sottocartelle separate per texconv
            per_nome = {}
            for copie in blocco:
                per_nome.setdefault(copie[0].name, []).append(copie)
            # texconv non regge i percorsi oltre i 260 caratteri: gli passo un collegamento con un nome corto
            entra, esce = d / "in", d / "out"
            entra.mkdir(exist_ok=True)
            esce.mkdir(exist_ok=True)
            for j, copie in enumerate(blocco):
                corta = entra / f"{j}.png"
                try:
                    os.link(copie[0], corta)
                except OSError:
                    shutil.copyfile(copie[0], corta)
            elenco.write_text("\n".join(corto(entra / f"{j}.png") for j in range(len(blocco))), encoding="utf-8")
            subprocess.run([str(exe), "-nologo", "-y", "-f", "BC7_UNORM", "-m", "0", *texconv_args(), "-o", corto(esce),
                            "-flist", corto(elenco)], capture_output=True, creationflags=0x08000000, env=ambiente_figli())
            if True:
                for j, copie in enumerate(blocco):
                    if self.annulla:
                        return
                    dds = esce / f"{j}.dds"
                    for p in copie:
                        if dds.is_file():
                            try:
                                _ritenta(lambda: shutil.copyfile(dds, p.with_suffix(".dds")))
                                _ritenta(p.unlink)
                            except OSError:
                                self.falliti += 1
                        else:
                            self.falliti += 1
                        self.fatti += 1
                        self.pct = 0.5 + 0.45 * self.fatti / max(1, self.totale)
            shutil.rmtree(d, ignore_errors=True)

        blocchi = [lavori[i:i + 40] for i in range(0, len(lavori), 40)]
        with ThreadPoolExecutor(TEXCONV_PROCESSI) as ex:
            list(ex.map(converti, blocchi))
        shutil.rmtree(tmp, ignore_errors=True)

    def _leggi_info(self):
        try:
            return json.loads((self.libreria / "libreria.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"componenti": {}, "formato": None}

    def _scrivi_info(self, info):
        scrivi_sicuro(self.libreria / "libreria.json", json.dumps(info, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- installazione nel gioco (dopo la libreria)
ESTENSIONI_DISCO = (".iso", ".gcm", ".rvz", ".wia", ".gcz", ".ciso", ".tgc")
SCELTE_BASE = {  # cosa mette l'installer di base (le scelte di John); dopo si cambia tutto dalle sezioni dell'app
    "primaria": "Skins/Suit Mods/RAIMI_2004", "alternativa": "Skins/Suit Mods/RAIMI_BLACK_SUIT",
    "ragnatele": "Skins/Webs/Custom Trilogy Webbing", "hud": "Skins/HUDs/HD HUD",
    "tasti": "Layout Controller/XBOX ONE Buttons (RT-LT)",
    "texture": ["Skins/Custom Textures/Unofficial Update Pack V2.3/Updated Textures V2"],  # title screen: spento (John)
}
CARTELLA_SALVATAGGI = {"GK2E52": "USA", "GK2P52": "UK", "GK2I52": "ITA", "GK2D52": "GERMANIA", "GK2F52": "FRANCIA"}


def file_salvataggio(dolphin, gid):
    """Il salvataggio di Spider-Man 2 di quella versione nella memory card A di Dolphin (cartella GCI)."""
    import salvataggio as sv
    return Path(dolphin) / "GC" / ("USA" if gid == "GK2E52" else "EUR") / "Card A" / sv.nome_file(gid)


def leggi_salvataggio(f):
    """Le caselle usate di un salvataggio .gci di Spider-Man 2: [{"slot", "nome", "percento", "tempo" (secondi),
    "punti", "data" ("2026-09-30 06:25")}]. Ogni file ha 2 caselle (la 2a a +0x10000). Percentuale = float a +0x4454
    dei dati (quella che il gioco mostra caricando: 100.96 nel 100%), tempo int +0x204C, punti int +0x207C, nome +0x206E,
    data a +0x2040 (anno, mese, giorno, ora, minuti, secondi: u16)."""
    import struct
    try:
        b = Path(f).read_bytes()
    except OSError:
        return []
    out = []
    for n, base in ((1, 0x40), (2, 0x10040)):
        if len(b) < base + 0x4458:
            break
        nome = b[base + 0x206E:base + 0x206E + 10].rstrip(b"\0")
        tempo = struct.unpack(">i", b[base + 0x204C:base + 0x2050])[0]
        if not nome or not all(32 <= c < 127 for c in nome) or not 0 < tempo < 10_000_000:
            continue  # casella vuota (zeri o resti senza nome)
        a, me, g, o, mi, s = struct.unpack(">6H", b[base + 0x2040:base + 0x204C])
        pc = struct.unpack(">f", b[base + 0x4454:base + 0x4458])[0]
        out.append({"slot": n, "nome": nome.decode("ascii"), "percento": round(pc, 2) if 0 <= pc < 200 else None,
                    "tempo": tempo, "punti": struct.unpack(">i", b[base + 0x207C:base + 0x2080])[0],
                    "data": f"{a:04d}-{me:02d}-{g:02d} {o:02d}:{mi:02d}" if 2000 < a < 2100 and 1 <= me <= 12 else None})
    return out


def stessi_dati_salvataggio(dolphin, da, a):
    """I due salvataggi hanno gli stessi dati di gioco (cioè `a` è già una copia di `da`)?"""
    s, d = file_salvataggio(dolphin, da), file_salvataggio(dolphin, a)
    try:
        return s.read_bytes()[0x40 + 0x2040:-4] == d.read_bytes()[0x40 + 0x2040:-4]
    except OSError:
        return False


def copia_salvataggio(dolphin, da, a):
    """Launcher, "Copia da ITA" (John: sulla USA appena aggiunta mancava il salvataggio della ITA): i dati della partita di
    `da` dentro un file della versione `a` (intestazione, icona e scritte di `a`: dal suo salvataggio se c'è, se no da
    quello del pack; controllo ricalcolato: salvataggio.converti). Il salvataggio che c'era in `a` va prima nei backup.
    Ritorna "copiato" | "uguale" | "manca" (nessun salvataggio da copiare) | "formato"."""
    import salvataggio as sv
    src, dest = file_salvataggio(dolphin, da), file_salvataggio(dolphin, a)
    if not src.is_file():
        return "manca"
    s = src.read_bytes()
    modello = dest.read_bytes() if dest.is_file() else None
    if modello is None or len(modello) != len(s):
        mp = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "pack_salvataggi" / CARTELLA_SALVATAGGI[a] / sv.nome_file(a)
        modello = mp.read_bytes() if mp.is_file() else None
    if not modello or len(modello) != len(s):
        return "formato"
    nuovo = sv.converti(s, modello)
    if dest.is_file():
        if dest.read_bytes()[0x40 + 0x2040:] == nuovo[0x40 + 0x2040:]:
            return "uguale"
        backup_file(dest, "GC")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(nuovo)
    os.replace(tmp, dest)
    return "copiato"


def contenuti():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "contenuti"


def trova_giochi(dolphin):
    """{ID: file del disco} delle versioni di Spider-Man 2 nelle cartelle dei giochi di Dolphin (l'ID è scritto in
    chiaro all'inizio del file, anche negli rvz)."""
    g = leggi_ini(Path(dolphin) / "Config" / "Dolphin.ini").get("General", {})
    cartelle = [g.get(f"ISOPath{i}") for i in range(int(g.get("ISOPaths", "0") or 0))]
    ricorsivo = g.get("RecursiveISOPaths", "False").lower() == "true"
    trovati = {}
    for c in cartelle:
        if not c or not os.path.isdir(c):
            continue
        if ricorsivo:
            files = (os.path.join(r, f) for r, _, fs in os.walk(c) for f in fs)
        else:
            files = (e.path for e in os.scandir(c) if e.is_file())
        for p in files:
            if not p.lower().endswith(ESTENSIONI_DISCO):
                continue
            try:
                with open(p, "rb") as fh:
                    m = re.search(rb"GK2[A-Z]52", fh.read(0x20000))
            except OSError:
                continue
            if m and m.group().decode() in NOMI_VERSIONE:
                trovati.setdefault(m.group().decode(), p)
    return trovati


# ---------------------------------------------------------------- launcher
def _exe_in(cartella):
    """Dolphin.exe dentro una cartella o nelle sue sottocartelle dirette."""
    p = Path(cartella)
    for c in (p, *(x for x in _sottocartelle(p))):
        if (c / "Dolphin.exe").is_file():
            return c / "Dolphin.exe"
    return None


def _sottocartelle(p):
    try:
        return [Path(e.path) for e in os.scandir(p) if e.is_dir()]
    except OSError:
        return []


def trova_exe_dolphin(conf=None, dolphin=None):
    """Dolphin.exe: quello scelto, quello aperto, quello accanto alla cartella utente portable, poi le cartelle con
    "dolphin" nel nome nei posti soliti (Program Files, radice dei dischi, Desktop, Download, Documenti)."""
    if conf and conf.get("dolphin_exe") and Path(conf["dolphin_exe"]).is_file():
        return Path(conf["dolphin_exe"])
    for e in exe_dolphin_aperti():
        if e and Path(e).name.lower() == "dolphin.exe":
            return Path(e)
    if dolphin and (Path(dolphin).parent / "Dolphin.exe").is_file():  # portable: <cartella exe>/User
        return Path(dolphin).parent / "Dolphin.exe"
    if DA_ZERO:
        return None  # prova da zero: solo il Dolphin installato dall'app
    casa = Path.home()
    basi = [casa / "Desktop", casa / "Downloads", cartella_documenti(), casa / "AppData" / "Local" / "Programs"]
    for lettera in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        radice = Path(f"{lettera}:\\")
        if os.path.exists(radice):
            basi += [radice, radice / "Program Files", radice / "Program Files (x86)", radice / "Games", radice / "Giochi", radice / "Emulators"]
    for b in basi:
        for c in _sottocartelle(b):
            if "dolphin" in c.name.lower() and c.name.lower() != "dolphin emulator":  # quella è la cartella utente
                exe = _exe_in(c)
                if exe:
                    return exe
    return None


def mod_versioni(dolphin):
    """Per ogni versione: c'è l'INI del gioco? texture HD, Spider-Cam, 60 fps, niente blur, 60 Hz (PAL), codici accesi."""
    D = Path(dolphin)
    tex = set(versioni_texture(D)) if (D / "Load" / "Textures").is_dir() else set()
    gfx = leggi_ini(D / "Config" / "GFX.ini").get("Settings", {}).get("HiresTextures", "False").lower() == "true"
    out = {}
    for g in ID_GIOCO:
        ini = D / "GameSettings" / f"{g}.ini"
        salv = file_salvataggio(D, g).is_file()
        if not ini.is_file():
            out[g] = {"ini": False, "texture": g in tex and gfx, "hd_spente": g in tex and not gfx, "salv": salv}
            continue
        c = leggi_codici_ini(ini)
        att = c["attivi"]
        hd = leggi_ini(ini).get("Video_Settings", {}).get("HiresTextures")
        db = {x["nome_ini"]: x for x in carica_codici_db()}
        pezzi = {n for n, x in db.items() if x.get("parte_di")}  # pezzi nascosti (Gecko e programma della camera): non contano
        cam = next((x for x in db.values() if x["id"] == "camera"), None)
        gecko = next((n for n, x in db.items() if x["id"] == "camera_moderna"), None)
        hd_on = hd.lower() == "true" if hd else gfx
        out[g] = {"ini": True, "texture": g in tex and hd_on, "hd_spente": g in tex and not hd_on,
                  "codici": len([a for a in att if a not in pezzi]),
                  "camera": bool(cam and cam["nome_ini"] in att), "cam_moderna": bool(gecko and gecko in att),
                  "fps60": "$60fps" in att, "blur": "$No motion blur" in att,
                  "fov": "$d-pad left to increase FOV, d-pad right to decrease" in att,
                  "tuffo": any(x["id"] == "tuffo_l3" and x["nome_ini"] in att for x in db.values()),
                  "hz60": any("60hz" in p.lower() for p in c["patch_attive"]) if g in PAL else None, "salv": salv}
    return out


def finestre_dolphin():
    """[(hwnd, titolo)] delle finestre visibili di Dolphin, dalla più in primo piano."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    pids = {p.pid for p in psutil.process_iter(["name"]) if e_dolphin(p.info["name"])}
    out = []
    if not pids:
        return out

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def guarda(h, _):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value in pids and u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            if b.value:
                out.append((h, b.value))
        return True
    u.EnumWindows(guarda, 0)
    return out


def gioco_in_corso(finestre=None):
    """Dal titolo delle finestre di Dolphin: ID di Spider-Man 2 se è in corso, "?" se gira un altro gioco, None se nessuno.
    (Senza gioco il titolo è solo "Dolphin <versione>"; con un gioco ci aggiunge nome e ID.)"""
    finestre = finestre_dolphin() if finestre is None else finestre
    for _, t in finestre:
        m = re.search(r"GK2[A-Z]52", t) if " | " in t else None  # (la finestra Proprietà ha l'ID ma non " | ")
        if m:
            return m.group()
    if any(" | " in t for _, t in finestre):  # le finestrelle di Dolphin (Proprietà, Grafica...) non hanno " | "
        return "?"
    return None


def _davanti(h):
    """Porta davanti una finestra. Windows lo permette solo a chi ha ricevuto l'ultimo input: un Alt "a vuoto" lo sblocca."""
    import ctypes
    import time
    u = ctypes.windll.user32
    if u.GetForegroundWindow() == h:
        return True
    for n in range(4):
        if u.GetForegroundWindow() == h:
            break
        if n < 2:
            u.keybd_event(0x12, 0x38, 0, 0)
            u.keybd_event(0x12, 0x38, 0x0002, 0)
            u.SetForegroundWindow(h)
        else:  # riserva: mi "attacco" al filo della finestra davanti, così Windows mi lascia passare
            k = ctypes.windll.kernel32
            ora = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
            mio = k.GetCurrentThreadId()
            u.AttachThreadInput(mio, ora, True)
            u.BringWindowToTop(h)
            u.SetForegroundWindow(h)
            u.AttachThreadInput(mio, ora, False)
        time.sleep(0.2)
    time.sleep(0.15)
    return u.GetForegroundWindow() == h


def schermo_intero_al_volo():
    """Mette/toglie lo schermo intero al gioco in corso: porta davanti la sua finestra e preme Alt+Invio (tasto rapido
    di base di Dolphin per lo schermo intero)."""
    import ctypes
    import time
    u = ctypes.windll.user32
    finestre = finestre_dolphin()
    gioco = [x for x in finestre if re.search(r"GK2[A-Z]52", x[1]) or " | " in x[1]] or finestre
    if not gioco:
        return False
    h = gioco[0][0]
    if u.IsIconic(h):
        u.ShowWindow(h, 9)
    if not _davanti(h):
        return False
    # Dolphin legge la tastiera con DirectInput, che guarda i codici fisici dei tasti (scan code): senza, li ignora.
    # I tasti restano giù un attimo, così Dolphin li vede al suo controllo (uno per fotogramma).
    ALT, INVIO, SU = (0x12, 0x38), (0x0D, 0x1C), 0x0002
    u.keybd_event(*ALT, 0, 0)
    time.sleep(0.08)
    u.keybd_event(*INVIO, 0, 0)
    time.sleep(0.15)
    u.keybd_event(*INVIO, SU, 0)
    time.sleep(0.05)
    u.keybd_event(*ALT, SU, 0)
    return True


def chiudi_gioco():
    """Chiede a Dolphin di chiudere il gioco (come la X della finestra): Dolphin mostra la sua conferma."""
    import ctypes
    u = ctypes.windll.user32
    gioco = [h for h, t in finestre_dolphin() if titolo_gioco(t)]
    if not gioco:
        return False
    _davanti(gioco[0])
    u.PostMessageW(gioco[0], 0x0010, 0, 0)  # WM_CLOSE
    return True


def aggiungi_cartella_giochi(dolphin, cartella):
    """Aggiunge la cartella ai percorsi dei giochi di Dolphin (così lo vede anche Dolphin). Solo a Dolphin chiuso."""
    ini = Path(dolphin) / "Config" / "Dolphin.ini"
    g = leggi_ini(ini).get("General", {})
    n = int(g.get("ISOPaths", "0") or 0)
    gia = [os.path.normcase(os.path.normpath(g.get(f"ISOPath{i}", ""))) for i in range(n)]
    if os.path.normcase(os.path.normpath(str(cartella))) in gia:
        return False
    backup_file(ini, "Config")
    scrivi_ini_valori(ini, {("General", f"ISOPath{n}"): str(cartella), ("General", "ISOPaths"): str(n + 1)})
    return True


def trucchi_accesi(dolphin):
    return leggi_ini(Path(dolphin) / "Config" / "Dolphin.ini").get("Core", {}).get("EnableCheats", "False").lower() == "true"


def ora_valore(ini):
    """Ora del giorno fermata in quell'INI (secondi del giorno) o None (nessun codice dell'ora acceso = giorno e notte
    che scorrono). Vale sia il codice nascosto con l'ora precisa sia i 4 orari fissi di Codici > Ora del giorno."""
    import ora
    if not Path(ini).is_file():
        return None
    att = leggi_codici_ini(ini)["attivi"]
    for nome in ora.TUTTI:
        if nome in att:
            sec = ora.da_righe(blocco_codice(ini, nome))
            if sec is not None:
                return sec
    return None


@_sotto_lock_ini
def imposta_ora(ini, gid, secondi):
    """Menu in gioco > Cielo: None = tutti i codici dell'ora tolti (il tempo scorre); secondi = tempo fermo a quell'ora
    (anche nelle prossime partite e senza l'app): uno dei 4 orari fissi di Codici se è proprio quello, se no il codice
    nascosto con l'ora precisa. Un codice dell'ora acceso alla volta."""
    import ora
    ini = Path(ini)
    if not ini.is_file():
        return False
    att = leggi_codici_ini(ini)
    preset = next((n for k, n in ora.PRESET.items() if secondi is not None and ora.ORE[k] == int(secondi) % 86400), None)
    tieni = None if secondi is None else (preset or ora.NOME)
    togli = [(n, True) for n in ora.TUTTI if n != tieni and n in att["presenti"]]
    righe = ora.righe(gid, secondi) if tieni else None
    gia = tieni and tieni in att["attivi"] and [r.strip().upper() for r in blocco_codice(ini, tieni)] == righe
    if not togli and (tieni is None or gia):
        return False
    backup_file(ini, "GameSettings")
    if tieni and not gia and tieni in att["presenti"]:
        sostituisci_codice(ini, tieni, tieni, righe)
    scrivi_codici_ini(ini, [(tieni, righe)] if tieni else [], togli)
    return True


def ora_leggi(gid):
    """Gioco aperto: (secondi del giorno, parola SPENTO) o None se la memoria non è del gioco giusto."""
    import ora
    try:
        with DME_LOCK:
            dme = aggancia_dme()  # (riaggancia se Dolphin è stato chiuso e riaperto: col vecchio hook leggeva un processo morto)
            if not dme or dme.read_bytes(0x80000000, 6).decode("ascii", "replace") != gid:
                return None
            return dme.read_word(ora.indirizzo(gid)) % 86400, dme.read_word(ora.SPENTO)
    except Exception:  # noqa: BLE001
        return None


def ora_scrivi(gid, secondi, spento=1):
    """Gioco aperto: l'ora del cielo subito (+ parola SPENTO = da qui il codice dell'INI non la scrive più: ci pensa l'app;
    spento=0 la rimette com'era, per esempio dopo il giro fotografico della mappa)."""
    import ora
    try:
        with DME_LOCK:
            dme = aggancia_dme()  # (riaggancia se Dolphin è stato chiuso e riaperto: col vecchio hook leggeva un processo morto)
            if not dme or dme.read_bytes(0x80000000, 6).decode("ascii", "replace") != gid:
                return False
            dme.write_word(ora.SPENTO, int(spento))
            if secondi is not None:
                dme.write_word(ora.indirizzo(gid), int(secondi) % 86400)
        return True
    except Exception:  # noqa: BLE001
        return False


class Viaggio:
    """Teletrasporto di Spider-Man (teletrasporto.py; menu in gioco > Mondo > Viaggio). Ogni accesso alla memoria sotto
    DME_LOCK, a piccoli pezzi (gli altri fili continuano a girare)."""

    def __init__(self, gid):
        import teletrasporto as tp
        self.tp, self.gid = tp, gid

    def _dme(self):
        dme = aggancia_dme()  # (riaggancia dopo un riavvio di Dolphin)
        if not dme or dme.read_bytes(0x80000000, 6).decode("ascii", "replace") != self.gid:
            raise RuntimeError("gioco")
        return dme

    def _ind(self, dme):
        o = dme.read_word(dme.read_word(self.tp.camera(self.gid)) + 0x164)
        f, s = dme.read_word(o + 0xC), dme.read_word(o + 0xB0)
        if not (0x80000000 <= f < 0x81800000 and 0x80000000 <= s < 0x81800000):
            raise RuntimeError("spidey")
        return f + 0x30, s + 0x30, f + 0x130

    def stato(self):
        import struct
        with DME_LOCK:
            return struct.unpack(">i", self._dme().read_bytes(self.tp.STATO, 4))[0]

    def posizione(self):
        import struct
        with DME_LOCK:
            dme = self._dme()
            return list(struct.unpack(">3f", dme.read_bytes(self._ind(dme)[0], 12)))

    def centro_mappa(self):
        """(x, quota, z) della telecamera della mappa del gioco se è aperta, se no None. ATTENZIONE: aprendo e chiudendo
        la telecamera vola da/verso un punto fisso fuori città (ITA -1356, -793) con la quota che sale/scende: il centro
        vero è solo con la quota della mappa (>= 499: 500 di base, fino a 2000 allargando) e la mappa aperta da un po'."""
        import struct
        with DME_LOCK:
            dme = self._dme()
            if dme.read_byte(self.tp.mappa_aperta(self.gid)) != 80:
                return None
            x, y, z = struct.unpack(">3f", dme.read_bytes(self.tp.centro_mappa(self.gid), 12))
        return (x, y, z) if abs(x) < 20000 and abs(z) < 20000 else None

    def mappa_aperta(self):
        with DME_LOCK:
            return self._dme().read_byte(self.tp.mappa_aperta(self.gid)) == 80

    def apri_mappa(self, dopo_tasto=None, attesa=3.0):
        """Apre la mappa grande del gioco premendo F15 (su Z e Start nel profilo: app_controller.TASTO_APRI_MAPPA).
        True = aperta (o già aperta)."""
        import time
        if self.mappa_aperta():
            return True
        if not tasto_dolphin(0x7E, 0x66):
            return False
        if dopo_tasto:
            dopo_tasto()
        t = time.time()
        while time.time() - t < attesa:
            time.sleep(0.05)
            if self.mappa_aperta():
                return True
        return False

    def chiudi_mappa(self, dopo_tasto=None, attesa=1.5):
        """Chiude la mappa grande del gioco con F14 (su X nel profilo). True = chiusa (o già chiusa)."""
        import time
        for _ in range(2):
            if not self.mappa_aperta():
                return True
            if not tasto_dolphin(0x7D, 0x65):
                return False
            if dopo_tasto:
                dopo_tasto()
            t = time.time()
            while time.time() - t < attesa:
                time.sleep(0.05)
                if not self.mappa_aperta():
                    return True
        return False

    def _tieni(self, p, secondi, fino=None):
        """Tiene Spidey in p per qualche secondo (o finché fino() è vero: True)."""
        import time
        t = time.time()
        while time.time() - t < secondi:
            self.metti(p)
            if fino and fino():
                return True
            time.sleep(0.01)
        return False

    def _chiudi_tenendo(self, p, attesa=30, dopo_tasto=None):
        """Mappa grande aperta: Spidey già in p (l'icona si sposta sulla mappa: si vede che è partito), poi la chiude
        premendo F14, che il profilo del pad ha su X ("X RIPRENDI"; app_controller.TASTO_MAPPA: i tasti finti in memoria
        non bastano, il menu della mappa legge il controller vero). Con la mappa aperta il gioco NON aggiorna la camera
        (il raggio del tetto non parte) e forse neanche la città: Spidey resta tenuto in p finché la mappa è chiusa.
        Senza F14 nel profilo (gioco avviato da Dolphin con un profilo vecchio) aspetta che la chiuda chi gioca.
        True = chiusa."""
        chiusa = lambda: not self.mappa_aperta()
        self._tieni(p, 0.8)
        for _ in range(2):
            if chiusa():
                return True
            tasto_dolphin(0x7D, 0x65)
            if dopo_tasto:  # il tasto porta davanti il gioco: il menu in gioco torna sopra
                dopo_tasto()
            if self._tieni(p, 1.0, chiusa):
                return True
        return self._tieni(p, attesa, chiusa)

    def metti(self, p):
        """Spidey in p (le due matrici), fermo, senza danno da caduta da lì."""
        import struct
        with DME_LOCK:
            dme = self._dme()
            a, b, v = self._ind(dme)
            for x in (a, b):
                dme.write_bytes(x, struct.pack(">3f", *p))
            dme.write_bytes(v, struct.pack(">3f", 0.0, 0.0, 0.0))
            dme.write_bytes(self.tp.TOP, struct.pack(">f", p[1]))

    def sonda(self, x, z):
        """Altezza del tetto/suolo sotto (x, z) col raggio del gioco (None = niente: acqua o città non ancora caricata,
        o il codice del teletrasporto non c'è)."""
        p = self.raggio((x, 495.0, z), (x, -20.0, z))
        return p[1] if p else None

    def raggio(self, da, a):
        """Primo punto (x, y, z) che il raggio dei muri del gioco tocca da `da` ad `a` (None = niente). Il gioco ha le
        collisioni solo vicino a Spidey (~300-500 m)."""
        import struct
        import time
        with DME_LOCK:
            dme = self._dme()
            if not dme.read_word(self.tp.ROUTINE):
                return None
            dme.write_bytes(self.tp.DA, struct.pack(">3f", *da))
            dme.write_bytes(self.tp.A, struct.pack(">3f", *a))
            dme.write_byte(self.tp.RICHIESTA, 1)
        t = time.time()
        while time.time() - t < 0.5:
            time.sleep(0.005)
            with DME_LOCK:
                dme = self._dme()
                e = dme.read_byte(self.tp.RICHIESTA)
                if e == 2:
                    return tuple(struct.unpack(">3f", dme.read_bytes(self.tp.PUNTO, 12)))
            if e == 3:
                return None
        return None

    def vai(self, x, z, y=None, dopo_tasto=None, terra=None, occhio=None, prima=None):
        """Teletrasporto. y = posto salvato (posizione esatta, tenuta finché la città è caricata); senza y = sopra quello
        che c'è in (x, z): Spidey resta sospeso a 520 m mentre il gioco carica la città, il raggio trova il tetto (stesso
        risultato 6 volte di fila, così non lo appoggio su un pavimento con il palazzo ancora da caricare) e ce lo metto.
        Con la mappa del gioco aperta prima la chiude (_chiudi_tenendo).
        occhio = punto scelto sulla mappa della città (foto in prospettiva, mappa_citta.occhio): invece del raggio dritto
        in giù, il raggio dall'occhio della foto attraverso (x, 0, z): tocca il tetto che si vedeva in quel punto (prima
        si finiva spesso sulla strada accanto ai palazzi alti, John 2026-10-19).
        Ritorna "ok", "acqua" (niente sotto: rimesso dov'era), "lento" (senza il codice: caduta da 500 m senza danno) o
        "mappa" (la mappa è rimasta aperta: rimesso dov'era). self.arrivo = dove è atterrato (x, y, z) con "ok".
        prima = dove rimetterlo se non arriva (mappa 3D: Spidey intanto è a 520 m sotto la telecamera, non dov'era)."""
        import math
        import time
        self.arrivo = None
        prima = tuple(prima) if prima else self.posizione()
        if y is not None:
            if self.mappa_aperta() and not self._chiudi_tenendo((x, y, z), dopo_tasto=dopo_tasto):
                self.metti(prima)
                return "mappa"
            self._tieni_finche_caricato(x, y, z)
            return "ok"
        with DME_LOCK:
            c_e = bool(self._dme().read_word(self.tp.ROUTINE))
        if not c_e:
            if self.mappa_aperta() and not self._chiudi_tenendo((x, self.tp.QUOTA, z), dopo_tasto=dopo_tasto):
                self.metti(prima)
                return "mappa"
            return self._caduta(x, z)
        da, a, sx, sz = (x, 495.0, z), (x, -20.0, z), x, z
        if occhio:
            ex, ey, ez = occhio
            ey = max(ey, 1.0)
            lungo = lambda h: (x + (ex - x) * h / ey, h, z + (ez - z) * h / ey)  # punto del raggio all'altezza h
            # il raggio parte dall'occhio se è più basso di 495 (mappa 3D inclinata): da più in alto partirebbe dietro la
            # telecamera e potrebbe toccare un palazzo che non si vedeva
            da, a = lungo(min(495.0, ey)), lungo(-20.0)
            sx, _, sz = lungo(150.0)  # Spidey sospeso a metà del pezzo dove possono stare i tetti (collisioni vicine)
            lontano = math.hypot(sx - x, sz - z)
            if lontano > 150.0:  # vista molto inclinata: non oltre 150 m dal punto (collisioni caricate solo vicino)
                sx, sz = x + (sx - x) * 150.0 / lontano, z + (sz - z) * 150.0 / lontano
        if self.mappa_aperta() and not self._chiudi_tenendo((sx, 520.0, sz), dopo_tasto=dopo_tasto):
            self.metti(prima)
            return "mappa"
        # terra = la mappa della città dice che lì c'è terra: lontano la città si carica piano (anche 5-8 s), quindi aspetto
        # di più, e se il raggio non trova ancora niente cado da 500 m (protetto) invece di dire "acqua" (John, 2026-10-19)
        t0, ultimi, colpo = time.time(), [], None
        while time.time() - t0 < (10.0 if terra else 3.5):
            self.metti((sx, 520.0, sz))
            ultimi = (ultimi + [self.raggio(da, a)])[-6:]
            if time.time() - t0 > 0.6 and len(ultimi) == 6 and None not in ultimi and                     max(max(abs(p[k] - ultimi[-1][k]) for k in range(3)) for p in ultimi) < 0.01:
                colpo = ultimi[-1]
                break
            time.sleep(0.03)
        if colpo is None:
            if terra:
                return self._caduta(x, z)
            self.metti(prima)
            return "acqua"
        gx, gy, gz = colpo
        if occhio:
            # il raggio storto può toccare una FACCIATA (quella verso il centro della foto): 1 m più in là lungo il raggio
            # si è dentro il palazzo -> raggio dritto da sopra: se trova un tetto più alto ci si mette lì
            dx, dz = x - ex, z - ez
            n = math.hypot(dx, dz) or 1.0
            qx, qz = gx + dx / n, gz + dz / n
            sopra = self.raggio((qx, 495.0, qz), (qx, gy - 1.0, qz))
            if sopra and sopra[1] > gy + 1.5:
                gx, gy, gz = qx, sopra[1], qz
        self._tieni((gx, gy + 0.97, gz), 0.4)
        self.arrivo = (gx, gy, gz)
        return "ok"

    def _tieni_finche_caricato(self, x, y, z, massimo=12.0):
        """Posto salvato (posizione esatta): Spidey tenuto lì finché sotto di lui ci sono le collisioni (lo stesso punto
        toccato dal raggio 6 volte di fila). Lontano la città si carica piano: prima lo lasciavo dopo 1,6 s e, con la
        statua della Libertà non ancora caricata, cadeva nel vuoto e il gioco lo rimetteva in un punto a caso della città
        (John; riprodotto: da (150, 617) alla testa della statua -> finito a (1, 115, 6))."""
        import time
        with DME_LOCK:
            c_e = bool(self._dme().read_word(self.tp.ROUTINE))
        if not c_e:  # senza il codice del raggio: come prima
            self._tieni((x, y, z), 1.6)
            return
        t0, ultimi = time.time(), []
        while time.time() - t0 < massimo:
            self.metti((x, y, z))
            ultimi = (ultimi + [self.raggio((x, y + 2.0, z), (x, -20.0, z))])[-6:]
            if time.time() - t0 > 0.6 and len(ultimi) == 6 and None not in ultimi and                     max(abs(p[1] - ultimi[-1][1]) for p in ultimi) < 0.01:
                break
            time.sleep(0.03)
        self._tieni((x, y, z), 0.4)

    def _caduta(self, x, z):
        """Riserva senza il raggio: da 500 m (sopra tutti i palazzi), x/z tenuti finché scende, punto più alto = altezza
        attuale (niente danno), x/z lasciati appena tocca qualcosa (se no resta incastrato su un bordo)."""
        import struct
        import time
        self.metti((x, self.tp.QUOTA, z))
        t0, caduto, ferma, y_prima = time.time(), False, 0, None
        while time.time() - t0 < 25:
            time.sleep(0.02)
            p, s = self.posizione(), self.stato()
            caduto = caduto or s in (4, 5)
            scende = y_prima is None or p[1] < y_prima - 0.05
            ferma = 0 if scende else ferma + 1
            y_prima = p[1]
            with DME_LOCK:
                dme = self._dme()
                dme.write_bytes(self.tp.TOP, struct.pack(">f", p[1]))
                if s in (1, 4, 5) and ferma < 10:
                    a, b, _ = self._ind(dme)
                    for i in (a, b):
                        dme.write_bytes(i, struct.pack(">3f", x, p[1], z))
            if caduto and s not in (4, 5):
                break
        return "lento"


@_sotto_lock_ini
def unisci_ini(dest, sorgente, forza=False):
    """Mette nell'INI dell'utente i codici accesi, le patch e le impostazioni dell'INI del pack, senza
    togliere niente di suo (i codici con lo stesso nome restano i suoi; le impostazioni grafiche e [Core] che ha già
    restano le sue, si aggiungono solo quelle che mancano, a meno di forza=True). Prima "Ripara" e "Prepara tutto"
    rimettevano per esempio l'overclock al 300% e il backend Vulkan del pack sopra le scelte dell'utente."""
    Ls, _ = _righe_ini(sorgente)
    blocchi, accesi, patch, patch_on, sez, nome = {}, [], {}, [], None, None
    for r in Ls:
        s = r.strip()
        if s.startswith("[") and s.endswith("]"):
            sez, nome = s, None
        elif sez in ("[ActionReplay]", "[Gecko]", "[OnFrame]") and s.startswith("$"):
            nome = s
            (patch if sez == "[OnFrame]" else blocchi)[nome] = []
        elif sez in ("[ActionReplay]", "[Gecko]", "[OnFrame]") and nome and s:
            (patch if sez == "[OnFrame]" else blocchi)[nome].append(s)
        elif sez in ("[ActionReplay_Enabled]", "[Gecko_Enabled]") and s.startswith("$"):  # anche i Gecko (prima: Web zip
            # e gli altri Gecko essenziali non arrivavano mai a chi aveva già un INI, es. quello del profilo del controller)
            accesi.append(s)
        elif sez == "[OnFrame_Enabled]" and s.startswith("$"):
            patch_on.append(s)
    if Path(dest).exists():
        aggiorna_codici_vecchi(dest, Path(dest).stem.upper())  # es. vecchio codice HUD -> quello con l'interruttore
    gia = leggi_codici_ini(dest)["presenti"] if Path(dest).exists() else set()  # i tuoi (accesi o spenti) restano come sono
    scrivi_codici_ini(dest, [(n, blocchi[n]) for n in accesi if n in blocchi and n not in gia], [])
    if patch:  # patch (es. 60Hz delle PAL): sezione [OnFrame] + accese
        L, nl = _righe_ini(dest)
        tit = [x.strip() for x in L]
        for t in ("[OnFrame]", "[OnFrame_Enabled]"):
            if t not in tit:
                while L and not L[-1].strip():
                    L.pop()
                L += [t]
                tit = [x.strip() for x in L]
        i, j = _sezione(L, "[OnFrame]")
        presenti = {L[x].strip() for x in range(i, j)}
        L[j:j] = [r for n, righe in patch.items() if n not in presenti for r in [n, *righe]]
        i, j = _sezione(L, "[OnFrame_Enabled]")
        gia = {L[x].strip() for x in range(i, j)}
        # (le patch si riaccendono anche se spente apposta: la 60Hz delle PAL serve ai codici, i loro indirizzi sono
        # quelli coi 60Hz; senza, camera/HUD scriverebbero nei posti sbagliati)
        L[j:j] = [n for n in patch_on if n not in gia]
        Path(dest).write_bytes(nl.join(L).encode("utf-8"))
    # impostazioni ([Video_*], [Core]) del pack
    ini_s = leggi_ini(sorgente)
    suoi = leggi_ini(dest) if not forza else {}
    valori = {(sz, k): v for sz, d in ini_s.items() if sz.startswith("Video_") or sz == "Core" for k, v in d.items()
              if k not in suoi.get(sz, {})}
    if valori:
        scrivi_ini_valori(dest, valori)


@_sotto_lock_ini
def prepara_ini(dolphin, gid, conf=None, cam_modi=None, cam_opzioni=None, oc=None):
    """L'INI di una versione pronto per giocare con la mod (installer, "Prepara tutto", codici essenziali): se non c'è
    è quello dell'installer, se c'è vi si uniscono codici e impostazioni che mancano (backup prima). Poi: codici di serie
    di Dolphin spenti, camera allineata (classica + Gecko + programma, con le camere scelte), profilo del controller e
    PadProfile1. oc = overclock della CPU emulata da mettere se l'INI è nuovo (dipende dal processore: OC_CPU).
    Ritorna il percorso dell'INI, None se l'installer non ha l'INI di questa versione."""
    import app_controller
    D = Path(dolphin)
    src = contenuti() / "GameSettings" / f"{gid}.ini"
    if not src.is_file():
        return None
    dest = D / "GameSettings" / f"{gid}.ini"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        backup_file(dest, "GameSettings")
        unisci_ini(dest, src)
    else:
        shutil.copyfile(src, dest)
        if oc:
            scrivi_ini_valori(dest, {("Core", "Overclock"): f"{oc:.8f}", ("Core", "OverclockEnable"): "True"})
    accendi_hd(dest)  # anche se l'INI c'era già con le texture spente
    spegni_di_serie(D, trova_exe_dolphin(conf, D), gid)
    allinea_camera(dest, gid, cam_modi, cam_opzioni)
    aggiorna_codici_vecchi(dest, gid)  # dopo la camera: i codici "nuovo_con" (tuffo) seguono il Gecko appena messo
    app_controller.assicura(D, gid)
    return dest


class InstallaGioco:
    """Dalla libreria a Dolphin: texture (una cartella sola + file <ID>.txt per le altre versioni), skin, HUD,
    tasti, ragnatele, INI con codici e impostazioni, salvataggi 100% (solo se non c'è già un salvataggio)."""

    def __init__(self, dolphin, libreria, versioni, salvataggi=False, mantieni=False, modi=None, conf=None,
                 cam_modi=None, cam_opzioni=None, oc=None):
        """mantieni = c'è già un'installazione: tengo le scelte attuali (skin, HUD, pacchetti) invece di quelle di John.
        modi = {id pacchetto: "nuove"}: di quel pacchetto solo le texture che RE non ha. conf/cam_modi/cam_opzioni/oc:
        per gli INI (vedi prepara_ini)."""
        self.dolphin, self.libreria, self.versioni, self.salvataggi = Path(dolphin), lungo(libreria), list(versioni), salvataggi
        self.mantieni, self.modi = mantieni, modi or {}
        self.conf, self.cam_modi, self.cam_opzioni, self.oc = conf, cam_modi, cam_opzioni, oc
        self.fase, self.fatti, self.totale, self.finito, self.errore, self.annulla = "", 0, 0, False, None, False
        self.risultato = {}

    def stato(self):
        return {"fase": self.fase, "fatti": self.fatti, "totale": self.totale, "finito": self.finito, "errore": self.errore,
                "risultato": self.risultato}

    def esegui(self):
        try:
            self._installa()
        except Exception as e:  # noqa: BLE001
            import traceback
            log_errore(traceback.format_exc())
            self.errore = f"{type(e).__name__}: {e}"
        finally:
            self.finito = True

    def _installa(self):
        L, D = self.libreria, self.dolphin
        # 0. contenuti di John nella libreria (tasti RT/LT)
        tasti_gio = contenuti() / "Layout Controller"
        if tasti_gio.is_dir():
            _copia_texture(tasti_gio, L / "Layout Controller")
        # 1. cartella delle texture: quelle che ci sono già, altrimenti una sola + <ID>.txt per le altre versioni
        base = D / "Load" / "Textures"
        esistenti = [g for g in self.versioni if (base / g).is_dir()]
        principale = esistenti[0] if esistenti else self.versioni[0]
        (base / principale).mkdir(parents=True, exist_ok=True)
        for g in self.versioni:
            if not (base / g).is_dir():
                (base / principale / f"{g}.txt").write_text("", encoding="utf-8")
        # 2. texture: Spider-Man 2: RE dappertutto, poi i pacchetti scelti, poi skin / ragnatele / HUD / tasti
        self.fase = "texture"
        voci = [voce_re(L)] + catalogo_texture(L)
        scelte = {f: "re" for f in voci[0]["file"]}
        per_path = {Path(v["path"]).relative_to(L).as_posix(): v for v in voci[1:]}
        dove = {k: (L / v if isinstance(v, str) else None) for k, v in SCELTE_BASE.items()}
        if self.mantieni and any(p.is_dir() for p in cartelle_texture(D)):
            # le scelte di adesso: per ogni texture chi c'è, e skin / ragnatele / HUD / tasti installati
            ids = {v["id"] for v in voci}
            for f, chi in stato_texture(D, L, voci).items():
                scelte[f] = chi if chi in ids or chi == "gioco" else "re"
            att = installate(D, catalogo_skin(L), catalogo_ragnatele(L))
            hud = installate_hud(D, catalogo_hud(L), catalogo_tasti(L))
            for k, v in (("primaria", att["primaria"]), ("alternativa", att["alternativa"]), ("hud", hud["hud"]), ("tasti", hud["tasti"])):
                if v and v.get("path"):
                    dove[k] = Path(v["path"])
            if att["ragnatele"] == "vanilla":
                dove["ragnatele"] = None
            elif att["ragnatele"] not in (None, "?"):
                dove["ragnatele"] = L / "Skins" / "Webs" / att["ragnatele"]
        else:
            for rel in SCELTE_BASE["texture"]:
                v = per_path.get(rel)
                if v:
                    modi = modi_texture(self.modi, [v])
                    scelte.update({f: v["id"] for f in v["file"] if modi.get(v["id"]) != "nuove" or f not in scelte})
        ins = Installazione(D)
        ins.texture(L, voci, scelte)
        uff = cartella_ufficiale(L)
        for slot in ("primaria", "alternativa"):
            if dove[slot] and dove[slot].is_dir():
                ins.skin(dove[slot], alternativa=slot == "alternativa", base=uff)
        ins.ragnatele(dove["ragnatele"] if dove["ragnatele"] and dove["ragnatele"].is_dir() else None)
        if dove["hud"] and dove["hud"].is_dir():
            ins.hud(L, dove["hud"])
        if dove["tasti"] and dove["tasti"].is_dir():
            ins.tasti(L, dove["tasti"])
        self.totale = len(ins.ops)
        ris = ins.esegui()
        self.fatti = self.totale
        # 3. INI del gioco: nuovo = quello del pack; se c'è già = uniti (backup prima)
        if self.annulla:
            return
        self.fase = "codici"
        ini_fatti = []
        for g in self.versioni:
            if self.annulla:
                return
            if prepara_ini(D, g, self.conf, self.cam_modi, self.cam_opzioni, self.oc):
                ini_fatti.append(NOMI_VERSIONE[g])
        # 4. trucchi accesi in Dolphin (solo a Dolphin chiuso: quando si chiude riscrive Dolphin.ini)
        trucchi = False
        if not exe_dolphin_aperti():
            ini = D / "Config" / "Dolphin.ini"
            backup_file(ini, "Config")
            scrivi_ini_valori(ini, {("Core", "EnableCheats"): "True"})
            trucchi = True
        # 5. salvataggio 100% (cartella GCI della memory card A), solo dove non c'è già un salvataggio
        salv = []
        if self.salvataggi:
            pack_s = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "pack_salvataggi"
            for g in self.versioni:
                regione = "USA" if g == "GK2E52" else "EUR"
                for f in (pack_s / CARTELLA_SALVATAGGI[g]).glob("*.gci"):
                    dest = D / "GC" / regione / "Card A" / f.name
                    if not dest.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(f, dest)
                        salv.append(NOMI_VERSIONE[g])
        self.risultato = {"copiati": ris["copiati"], "cartella": principale, "ini": ini_fatti, "trucchi": trucchi, "salvataggi": salv}


# ---------------------------------------------------------------- esportazione della mod pronta (zip da copiare)
# Lo zip ha la stessa struttura della cartella utente di Dolphin: si estrae lì e basta (PC, Android, Xbox).
ANDROID_BASE = {  # grafica dello zip per Android: base Snapdragon 8 Gen 2 (Retroid Pocket 6)
    "res": 3, "formato": 1, "msaa": 1, "ssaa": False, "aniso": 0, "vsync": False, "backend": "Vulkan", "oc_on": True, "oc": 3.0,
    "shader": 2, "attendi": True, "hd": True, "cache": True, "fps": False, "fps30": False, "tex": "png", "jit": False,
}
MAC_BASE = {  # grafica dello zip per Mac: base Apple Silicon (M1-M4), Metal; si cambia in Grafica > Mac
    "res": 4, "formato": 1, "msaa": 1, "ssaa": False, "aniso": 2, "vsync": True, "backend": "Metal", "oc_on": True, "oc": 3.0,
    "shader": 2, "attendi": True, "hd": True, "cache": True, "fps": False, "tex": "dds", "jit": False,
}
PIATTAFORME = {  # id -> controller possibili (cartella in contenuti/Profiles)
    "pc": ["pc"], "pcarm": ["pc"], "mac": [], "android": ["android_retroid", "android_kishi"], "xbox": ["xbox"],
}


def _togli_attivi(ini, nomi):
    """Toglie dei codici dall'elenco di quelli accesi (es. $60fps per la versione Android a 30 fps)."""
    L, nl = _righe_ini(ini)
    if "[ActionReplay_Enabled]" not in [x.strip() for x in L]:
        return
    i, j = _sezione(L, "[ActionReplay_Enabled]")
    L[i:j] = [r for r in L[i:j] if r.strip() not in nomi]
    Path(ini).write_bytes(nl.join(L).encode("utf-8"))


def _togli_chiavi(ini, coppie):
    L, nl = _righe_ini(ini)
    sez, out = None, []
    for r in L:
        s = r.strip()
        if s.startswith("[") and s.endswith("]"):
            sez = s[1:-1]
        elif sez and "=" in s and (sez, s.split("=", 1)[0].strip()) in coppie:
            continue
        out.append(r)
    Path(ini).write_bytes(nl.join(out).encode("utf-8"))


class Esportazione:
    """Prepara lo zip: texture in uso (da Load/Textures di Dolphin), INI delle versioni scelte adattati alla
    piattaforma, profilo del controller, salvataggio 100% (se chiesto) e un LEGGIMI corto."""

    def __init__(self, dolphin, dest_zip, piattaforma, controller, versioni, formato="dds", fps30=False,
                 salvataggi=False, leggimi="", grafica=None, parti=("texture", "ini", "controller")):
        self.dolphin, self.dest = Path(dolphin), Path(dest_zip)
        self.piattaforma, self.controller, self.versioni = piattaforma, controller, list(versioni)
        self.formato, self.fps30, self.salvataggi, self.leggimi = formato, fps30, salvataggi, leggimi
        self.grafica = grafica or {}  # impostazioni grafiche da scrivere negli INI (es. preset Android)
        self.parti = set(parti)  # cosa mettere nello zip: texture / ini / controller (+ salvataggi a parte)
        self.fase, self.fatti, self.totale, self.finito, self.errore, self.annulla = "", 0, 0, False, None, False

    def stato(self):
        return {"fase": self.fase, "fatti": self.fatti, "totale": self.totale, "finito": self.finito, "errore": self.errore,
                "file": str(self.dest), "esporta": True}

    def esegui(self):
        try:
            self._esporta()
            if self.annulla:  # annullato a metà: niente zip parziale
                self.dest.unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001
            import traceback
            log_errore(traceback.format_exc())
            self.errore = f"{type(e).__name__}: {e}"
            try:
                self.dest.unlink()
            except OSError:
                pass
        finally:
            _rimuovi(self.dolphin / "Load" / "_spidey_export_tmp")  # anche se annullato o andato storto
            self.finito = True

    def _esporta(self):
        import zipfile
        D = self.dolphin
        cart = cartelle_texture(D)[0]
        tmp = D / "Load" / "_spidey_export_tmp"
        _rimuovi(tmp)
        tmp.mkdir(parents=True)
        # 1. texture: quelle in uso adesso; per Android (o se chiesto) in PNG, più compatibile
        files = sorted(e.path for e in os.scandir(cart) if e.is_file() and e.name.lower().endswith((".png", ".dds")))
        if "texture" not in self.parti:
            files = []
        if self.formato == "png" and files:
            dds = [f for f in files if f.lower().endswith(".dds")]
            self.fase, self.totale = "png", len(dds)
            exe = texconv()
            if dds and not exe:
                raise RuntimeError("texconv")
            (tmp / "png").mkdir()
            for i in range(0, len(dds), 200):
                if self.annulla:
                    return
                elenco = tmp / "lista.txt"
                elenco.write_text("\n".join(dds[i:i + 200]), encoding="utf-8")
                import subprocess
                subprocess.run([str(exe), "-nologo", "-y", "-ft", "png", "-f", "R8G8B8A8_UNORM", "-m", "1", "-o", str(tmp / "png"),
                                "-flist", str(elenco)], capture_output=True, creationflags=0x08000000, env=ambiente_figli())
                self.fatti = min(i + 200, len(dds))
            nuovi = {Path(f).stem: str(tmp / "png" / (Path(f).stem + ".png")) for f in dds}
            files = [f if f.lower().endswith(".png") else nuovi[Path(f).stem] for f in files if
                     f.lower().endswith(".png") or Path(nuovi[Path(f).stem]).is_file()]
        # 2. INI adattati
        self.fase = "ini"
        ini_dir = tmp / "GameSettings"
        ini_dir.mkdir()
        for g in self.versioni:
            src = D / "GameSettings" / f"{g}.ini"
            if not src.exists():
                src = contenuti() / "GameSettings" / f"{g}.ini"
            if not src.exists():
                continue
            dst = ini_dir / f"{g}.ini"
            shutil.copyfile(src, dst)
            # pezzi che servono solo con l'app aperta (teletrasporto e mappa 3D del menu in gioco): nello zip costerebbero
            # ~200 byte di Gecko e ~120 righe AR a ogni fotogramma per niente (anche su Android/Xbox/Mac)
            solo_app = {c["nome_ini"] for c in carica_codici_db() if c["id"] in ("teletrasporto", "teletrasporto_aggancio")}
            solo_app &= leggi_codici_ini(dst)["presenti"]
            if solo_app:
                scrivi_codici_ini(dst, [], [(n, True) for n in solo_app])
            valori = {("Controls", "PadType0"): "6", ("Controls", "PadProfile1"): "spiderman 2"} if self.controller else {}
            for k, v in self.grafica.items():
                if k in GRAFICA:
                    valori[(GRAFICA[k][0], GRAFICA[k][1])] = _a_testo(GRAFICA[k][2], v)
            if self.piattaforma in ("android", "pcarm"):  # ARM: senza questo il gioco va a scatti
                valori[("Core", "JITFollowBranch")] = "False"
                if self.fps30:
                    valori.update({("Video_Settings", "InternalResolution"): "2", ("Core", "OverclockEnable"): "False"})
                    _togli_attivi(dst, {"$60fps"})
            if self.piattaforma == "xbox":
                _togli_chiavi(dst, {("Core", "GFXBackend")})
                valori.update({("Core", "OverclockEnable"): "True", ("Core", "Overclock"): _a_testo("float", 3.0)})  # 300%: fluido, ventole tranquille
            if valori:
                scrivi_ini_valori(dst, valori)
        # 3. zip
        self.fase, self.fatti, self.totale = "zip", 0, len(files)
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        principale = cart.name if cart.name in self.versioni else self.versioni[0]
        with zipfile.ZipFile(self.dest, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for f in files:
                if self.annulla:
                    return
                z.write(f, f"Load/Textures/{principale}/{Path(f).name}",
                        compress_type=zipfile.ZIP_STORED if f.lower().endswith(".png") else zipfile.ZIP_DEFLATED)
                self.fatti += 1
            for g in self.versioni if files else []:
                if g != principale:
                    z.writestr(f"Load/Textures/{principale}/{g}.txt", "")
            for f in sorted(ini_dir.iterdir()) if "ini" in self.parti else []:
                z.write(f, f"GameSettings/{f.name}")
            if self.controller and "controller" in self.parti:
                prof = contenuti() / "Profiles" / self.controller / "spiderman 2.ini"
                mio = D / "Config" / "Profiles" / "GCPad" / "spiderman 2.ini"
                if self.controller == "pc" and mio.is_file():  # sul PC: il profilo che usi adesso
                    prof = mio
                if prof.is_file():
                    z.write(prof, "Config/Profiles/GCPad/spiderman 2.ini")
            if self.salvataggi:
                pack_s = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "pack_salvataggi"
                for g in self.versioni:
                    regione = "USA" if g == "GK2E52" else "EUR"
                    for f in (pack_s / CARTELLA_SALVATAGGI[g]).glob("*.gci"):
                        z.write(f, f"GC/{regione}/Card A/{f.name}")
            if self.leggimi:
                z.writestr("LEGGIMI - README.txt", self.leggimi.replace("\n", "\r\n"))
        _rimuovi(tmp)


# ---------------------------------------------------------------- stati salvati (savestate di Dolphin) con foto
# File di Dolphin: StateSaves/<ID>.s01..s10. Intestazione: ID del gioco, "cookie" 0xBAADBABE + versione del formato
# (Dolphin carica SOLO stati con lo stesso formato) e la versione di Dolphin che l'ha creato ("Dolphin 2609").
# Le foto e i codici attivi al momento del salvataggio li tiene l'app in STATI_INFO (Dolphin non salva miniature).
STATI_INFO = CONF_DIR / "stati"
SLOT_STATI = range(1, 11)
SLOT_TASTI = range(1, 9)  # tasti rapidi di base di Dolphin: F1..F8 carica, Maiusc+F1..F8 salva
_VER_EXE = {}


def file_stato(dolphin, gid, n):
    return Path(dolphin) / "StateSaves" / f"{gid}.s{n:02d}"


def testa_stato(p):
    """{"gid", "formato", "versione"} dall'intestazione del file (None se non si capisce)."""
    try:
        with open(p, "rb") as f:
            b = f.read(256)
    except OSError:
        return None
    for i in range(6, 64):
        if b[i + 2:i + 4] == b"\xad\xba":
            lung = int.from_bytes(b[i + 4:i + 8], "little")
            testo = b[i + 8:i + 8 + lung]
            if 0 < lung < 80 and testo.startswith(b"Dolphin"):
                return {"gid": b[:6].decode("ascii", "replace"), "formato": int.from_bytes(b[i:i + 4], "little") - 0xBAADBABE,
                        "versione": testo.decode("ascii", "replace")}
    return None


def versione_exe_dolphin(exe):
    """ "Dolphin 2609": la versione è scritta dentro l'exe (come "Dolphin/2609", lo user agent)."""
    if not exe or not Path(exe).is_file():
        return None
    k = (str(exe), Path(exe).stat().st_mtime_ns)
    if k not in _VER_EXE:
        m = re.search(rb"Dolphin/([0-9][0-9A-Za-z.\-]*)\x00", Path(exe).read_bytes())
        _VER_EXE[k] = "Dolphin " + m.group(1).decode() if m else None
    return _VER_EXE[k]


def formato_attuale(dolphin, versione):
    """Formato degli stati della versione di Dolphin installata: lo prendo da uno stato fatto con quella versione."""
    for p in (Path(dolphin) / "StateSaves").glob("*.s[0-9][0-9]"):
        t = testa_stato(p)
        if t and t["versione"] == versione:
            return t["formato"]
    return None


def codici_in_uso(dolphin, gid):
    """Codici accesi e patch dell'INI del gioco, con un'impronta delle righe di ogni codice (per vedere se è cambiato)."""
    ini = Path(dolphin) / "GameSettings" / f"{gid}.ini"
    if not ini.is_file():
        return {"codici": {}, "patch": []}
    c = leggi_codici_ini(ini)
    L, _ = _righe_ini(ini)
    righe, nome = {}, None
    for sez in ("[ActionReplay]", "[Gecko]"):
        if sez not in [x.strip() for x in L]:
            continue
        i, j = _sezione(L, sez)
        for r in L[i:j]:
            s = r.strip()
            if s.startswith("$"):
                nome = s
                righe[nome] = []
            elif nome and s:
                righe[nome].append(s.upper())
    return {"codici": {n: hashlib.md5("\n".join(righe.get(n, [])).encode()).hexdigest()[:10] for n in sorted(c["attivi"])},
            "patch": sorted(c["patch_attive"])}


def foto_finestra(h, larg=480, immagine=False):
    """Foto della SOLA finestra del gioco (JPEG base64; immagine=True: immagine Pillow a grandezza vera). PrintWindow vede
    anche Vulkan/D3D sui Windows recenti; se esce nera e il gioco è davanti, prendo il riquadro della sua finestra."""
    import ctypes
    from ctypes import wintypes
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    try:  # misure in pixel veri (schermi con scala 125%, 150%...), solo per questo filo: le finestre dell'app non cambiano
        prima = u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    except AttributeError:
        prima = None
    try:
        return _foto_finestra(h, larg, u, g, wintypes, immagine)
    finally:
        if prima:
            u.SetThreadDpiAwarenessContext(ctypes.c_void_p(prima))


def _foto_finestra(h, larg, u, g, wintypes, immagine=False):
    import ctypes
    r = wintypes.RECT()
    u.GetClientRect(h, ctypes.byref(r))
    w, a = r.right, r.bottom
    if w < 16 or a < 16:
        return None
    im = None
    hdc = u.GetDC(h)
    mem = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, a)
    g.SelectObject(mem, bmp)
    if u.PrintWindow(h, mem, 3):  # 1 = solo l'area client, 2 = PW_RENDERFULLCONTENT
        class BIH(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
        bi = BIH(ctypes.sizeof(BIH), w, -a, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * a * 4)
        g.GetDIBits(mem, bmp, 0, a, buf, ctypes.byref(bi), 0)
        im = Image.frombuffer("RGB", (w, a), buf, "raw", "BGRX", 0, 1)
    g.DeleteObject(bmp)
    g.DeleteDC(mem)
    u.ReleaseDC(h, hdc)
    if (im is None or max(im.convert("L").getextrema()) < 8) and u.GetForegroundWindow() == h:
        from PIL import ImageGrab
        p = wintypes.POINT(0, 0)
        u.ClientToScreen(h, ctypes.byref(p))
        im = ImageGrab.grab(bbox=(p.x, p.y, p.x + w, p.y + a), all_screens=True)
    if im is None or max(im.convert("L").getextrema()) < 8:
        return None
    if immagine:
        return im.convert("RGB")
    im.thumbnail((larg, larg))
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=84)
    return base64.b64encode(b.getvalue()).decode()


def titolo_gioco(t):
    """Il titolo è quello della finestra del GIOCO ("Dolphin 2609 | JIT64 DC | ... | Spider-Man 2 (GK2E52)")? Anche la
    finestra Proprietà di Dolphin ha l'ID nel titolo, ma non " | ": scambiata per il gioco = menu, primo piano, Alt+Invio
    sulla finestra sbagliata."""
    return " | " in t and re.search(r"GK2[A-Z]52", t) is not None


def finestra_gioco():
    return next((h for h, t in finestre_dolphin() if titolo_gioco(t)), None)


def _rett(h):
    import ctypes
    from ctypes import wintypes
    r = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(h, ctypes.byref(r))
    return r


def _monitor(h):
    """(rettangolo del monitor, area di lavoro senza barra delle applicazioni) del monitor della finestra."""
    import ctypes
    from ctypes import wintypes

    class MI(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
    u = ctypes.windll.user32
    mi = MI()
    mi.cbSize = ctypes.sizeof(MI)
    u.GetMonitorInfoW(u.MonitorFromWindow(h, 2), ctypes.byref(mi))
    return mi.rcMonitor, mi.rcWork


def finestrelle_sopra():
    """Le finestrelle di Dolphin (conferma di chiusura, impostazioni...) sopra al gioco "sempre in primo piano":
    senza, la domanda "Vuoi chiudere?" dopo Esc resterebbe nascosta dietro il gioco (a schermo intero Dolphin la crea
    senza "padre" e non in primo piano). Finestrelle = titolo senza " | " e che non comincia con "Dolphin" (il gioco è
    "Dolphin 2609 | JIT64 ... | Spider-Man 2 (ID)", la finestra principale "Dolphin 2609")."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    swp = u.SetWindowPos
    swp.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    finestre = finestre_dolphin()
    gioco = next((h for h, t in finestre if titolo_gioco(t)), None)

    def sotto_al_gioco(h):  # il gioco sta sopra questa finestra nell'ordine delle finestre?
        x = u.GetWindow(h, 3)  # GW_HWNDPREV: quella subito sopra
        while x:
            if x == gioco:
                return True
            x = u.GetWindow(x, 3)
        return False
    fatte = 0
    viste, alzate = set(), []
    for h, t in finestre:
        t = t.strip()
        if not t or " | " in t or t.startswith("Dolphin"):
            continue
        viste.add(h)
        nuova = h not in _FINESTRELLE_VISTE
        if nuova or not u.GetWindowLongW(h, -20) & 0x8 or (gioco and sotto_al_gioco(h)):
            swp(h, wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002)  # HWND_TOPMOST, in cima
            alzate.append(h)
            if nuova:  # davanti una volta sola (poi, se clicchi altrove, non le rubo il primo piano ogni mezzo secondo)
                _davanti(h)
            fatte += 1
    # il gioco in primo piano (soprattutto a schermo intero) resta davanti anche a una finestra TOPMOST alzata da un altro
    # programma (John: "la finestrella di Esc spawna sotto il gioco"): metto IL GIOCO sotto la più bassa delle finestrelle
    # alzate (una sola volta: con due finestrelle, mettendolo sotto a ciascuna, si coprivano a turno ogni mezzo secondo)
    if gioco and alzate:
        swp(gioco, alzate[0], 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # NOMOVE | NOSIZE | NOACTIVATE
    _FINESTRELLE_VISTE.intersection_update(viste)
    _FINESTRELLE_VISTE.update(viste)
    return fatte


_FINESTRELLE_VISTE = set()  # finestrelle di Dolphin già portate davanti (finestrelle_sopra)


def stato_finestra_gioco():
    """{"sopra": sempre in primo piano, "intero": a schermo intero} della finestra del gioco, None se non c'è."""
    import ctypes
    h = finestra_gioco()
    if not h:
        return None
    ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # coordinate vere anche con lo zoom di Windows
    r, (m, _) = _rett(h), _monitor(h)
    return {"sopra": bool(ctypes.windll.user32.GetWindowLongW(h, -20) & 0x8),  # WS_EX_TOPMOST
            "intero": (r.left, r.top, r.right, r.bottom) == (m.left, m.top, m.right, m.bottom)}


def gioco_sopra(si, sistema=False, app=None):
    """Tiene la finestra del gioco sopra le altre (resta visibile anche quando clicchi l'app) o la rimette normale.
    sistema = la mette sul monitor dell'app, in alto a destra sopra la colonna "Dal vivo", grande circa un terzo dello
    schermo: vedi il gioco e intanto muovi gli slider."""
    import ctypes
    u = ctypes.windll.user32
    h = finestra_gioco()
    if not h:
        return False
    u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    x = y = w = hh = 0
    flag = 0x0010 | 0x0001 | 0x0002  # SWP_NOACTIVATE | NOSIZE | NOMOVE
    if si and sistema and not (stato_finestra_gioco() or {}).get("intero"):
        a = u.FindWindowW(None, app) if app else 0
        _, lav = _monitor(a or h)
        W, H = lav.right - lav.left, lav.bottom - lav.top
        w = int(W * 0.29)
        hh = int(w * 9 / 16) + 38  # + barra del titolo
        x, y = lav.right - w - 16, lav.top + int(H * 0.30)
        flag = 0x0010
    from ctypes import wintypes
    swp = u.SetWindowPos
    swp.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    swp(h, wintypes.HWND(-1 if si else -2), x, y, w, hh, flag)  # HWND_TOPMOST / HWND_NOTOPMOST (-1 va passato come HWND a 64 bit)
    return True


def salva_info_stato(dolphin, gid, n, foto, codici, versione):
    """Dati dell'app per uno slot: foto, codici accesi quando è stato salvato, versione di Dolphin, data del file."""
    p = file_stato(dolphin, gid, n)
    STATI_INFO.mkdir(parents=True, exist_ok=True)
    info = {"mtime": p.stat().st_mtime if p.exists() else 0, "versione": versione, "codici": codici["codici"],
            "patch": codici["patch"], "foto": foto}
    (STATI_INFO / f"{gid}.s{n:02d}.json").write_text(json.dumps(info), encoding="utf-8")


def info_stato(dolphin, gid, n):
    """Dati dell'app solo se valgono per il file di adesso (se lo stato è stato rifatto senza l'app, la foto è vecchia)."""
    p, f = file_stato(dolphin, gid, n), STATI_INFO / f"{gid}.s{n:02d}.json"
    try:
        info = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return info if p.exists() and abs(info.get("mtime", 0) - p.stat().st_mtime) < 3 else None


def stati_salvati(dolphin, gid, versione=None):
    """Gli slot di una versione: data, foto, versione di Dolphin, compatibilità e codici cambiati da allora."""
    formato = formato_attuale(dolphin, versione) if versione else None
    ora = codici_in_uso(dolphin, gid)
    out = []
    for n in SLOT_STATI:
        p = file_stato(dolphin, gid, n)
        if not p.is_file():
            continue
        t = testa_stato(p) or {}
        info = info_stato(dolphin, gid, n)
        if formato is not None and t.get("formato") is not None:
            comp = t["formato"] == formato
        else:
            comp = None if not versione or not t.get("versione") else (True if t["versione"] == versione else None)
        voce = {"n": n, "data": p.stat().st_mtime, "versione": t.get("versione"), "compatibile": comp,
                "foto": info.get("foto") if info else None, "tasto": n in SLOT_TASTI}
        if info:
            prima, adesso = info.get("codici", {}), ora["codici"]
            voce["accesi"] = sorted(set(adesso) - set(prima))
            voce["spenti"] = sorted(set(prima) - set(adesso))
            voce["cambiati"] = sorted(x for x in set(prima) & set(adesso) if prima[x] != adesso[x])
            voce["patch"] = sorted(set(info.get("patch", [])) ^ set(ora["patch"]))
        out.append(voce)
    return out


def elimina_stato(dolphin, gid, n):
    """Nel Cestino (si può recuperare), insieme alla foto dell'app."""
    import ctypes
    from ctypes import wintypes
    p = file_stato(dolphin, gid, n)
    if p.exists():
        class SHFILEOP(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", ctypes.c_uint), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                        ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                        ("lpszProgressTitle", wintypes.LPCWSTR)]
        op = SHFILEOP(None, 3, str(p) + "\0", None, 0x0040 | 0x0010 | 0x0004 | 0x0400, False, None, None)  # cestino, senza domande
        if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) != 0 or p.exists():
            return False
    try:
        (STATI_INFO / f"{gid}.s{n:02d}.json").unlink()
    except OSError:
        pass
    return True


def tasto_stato(n, salva):
    """Maiusc+F<n> (salva) o F<n> (carica) al gioco: tasti rapidi di base di Dolphin, con gli scan code (DirectInput)."""
    import ctypes
    import time
    h = finestra_gioco()
    if not h or n not in SLOT_TASTI or not _davanti(h):
        return False
    u = ctypes.windll.user32
    fk = (0x70 + n - 1, 0x3B + n - 1)
    if salva:
        u.keybd_event(0x10, 0x2A, 0, 0)
        time.sleep(0.08)
    u.keybd_event(*fk, 0, 0)
    time.sleep(0.15)
    u.keybd_event(*fk, 0x0002, 0)
    if salva:
        time.sleep(0.05)
        u.keybd_event(0x10, 0x2A, 0x0002, 0)
    return True


def tasto_dolphin(vk, scan, h=None):
    """Un tasto alla finestra del gioco: la porta davanti e lo preme con lo scan code (Dolphin legge la tastiera con
    DirectInput). Lo usano Viaggio.chiudi_mappa (F14 = X nel profilo del pad) e gli script di prova (tasti della
    tastiera aggiunti per un momento al profilo, per guidare Spidey senza controller)."""
    import ctypes
    import time
    h = h or finestra_gioco()
    if not h or not _davanti(h):
        return False
    u = ctypes.windll.user32
    u.keybd_event(vk, scan, 0, 0)
    time.sleep(0.12)
    u.keybd_event(vk, scan, 0x0002, 0)
    return True


# contatore dei fotogrammi del gioco (.bss): fermo mentre carica, poi +60/s (+30 senza il codice 60 fps). Trovato
# confrontando foto della RAM all'avvio; UK/DE/FR hanno lo stesso programma dell'USA, l'ITA ha la .bss spostata di +0x80.
CONTA_FOTOGRAMMI = {"GK2E52": 0x8056BB50, "GK2P52": 0x8056BB50, "GK2D52": 0x8056BB50, "GK2F52": 0x8056BB50, "GK2I52": 0x8056BBD0}


def luce_gioco(h):
    """Luminosità media (0-255) del centro della finestra del gioco: 0 = schermo nero (sta ancora caricando).
    Il centro esclude il contatore FPS di Dolphin in alto."""
    import base64
    import io
    f = foto_finestra(h, 160)
    if not f:
        return None
    im = Image.open(io.BytesIO(base64.b64decode(f))).convert("L")
    w, a = im.size
    centro = im.crop((w // 5, a // 5, w * 4 // 5, a * 4 // 5))
    return sum(centro.getdata()) / (centro.width * centro.height)


def aspetta_gioco_pronto(gid, max_s=90):
    """Aspetta che il gioco abbia finito di caricare: appena lo schermo smette di essere nero (compaiono i crediti,
    ~10 s dall'avvio) per due controlli di fila. Riserva: il contatore dei fotogrammi del gioco che corre a velocità
    piena (parte un po' dopo, col titolo). True = pronto, False = tempo scaduto."""
    import time
    import dolphin_memory_engine as dme
    inizio, storia, accesi = time.time(), [], 0
    while time.time() - inizio < max_s:
        time.sleep(0.4)
        h = finestra_gioco()
        if not h:
            continue
        try:
            luce = luce_gioco(h)
        except Exception:  # noqa: BLE001 - foto non riuscita: resta il contatore
            luce = None
        accesi = accesi + 1 if luce is not None and luce > 6 else 0
        if accesi >= 2:
            return True
        try:
            with DME_LOCK:
                if aggancia_dme() and dme.read_bytes(0x80000000, 6).decode("ascii", "ignore") == gid:
                    storia.append(dme.read_word(CONTA_FOTOGRAMMI[gid]))
        except Exception:  # noqa: BLE001 - Dolphin non ancora pronto
            storia = []
        passi = [b - a for a, b in zip(storia[-4:-1], storia[-3:])] if len(storia) >= 4 else []
        if passi and all(10 <= x <= 32 for x in passi):  # contatore a velocità piena (0,4 s = 24 a 60 fps)
            return True
    return False


class GuardiaStati:
    """Mentre gira Spider-Man 2 guarda la cartella degli stati: quando uno slot cambia (salvato dall'app, da Dolphin o dal
    pad) fa subito la foto della finestra del gioco e salva i codici accesi a inizio partita (quelli che girano davvero)."""

    def __init__(self, dolphin_fn, exe_fn):
        self.dolphin_fn, self.exe_fn = dolphin_fn, exe_fn
        self.gid, self.sessione, self.noti, self.foto_pronte = None, None, {}, {}
        self.stop, self.rev = False, 0  # rev cresce a ogni stato fotografato: la pagina sa quando ricaricare

    def dimentica(self, gid, n):
        if gid == self.gid:
            self.noti.pop(n, None)
            self.rev += 1

    def _mtime(self, D, gid):
        return {n: file_stato(D, gid, n).stat().st_mtime for n in SLOT_STATI if file_stato(D, gid, n).exists()}

    def giro(self):
        import time
        D = self.dolphin_fn()
        if not D:
            return
        gid = gioco_in_corso()
        gid = gid if gid and gid != "?" else None
        if gid != self.gid:  # partita nuova: i codici in uso sono quelli dell'INI di adesso
            self.gid = gid
            self.sessione = codici_in_uso(D, gid) if gid else None
            self.noti = self._mtime(D, gid) if gid else {}
            return
        if not gid:
            return
        for n, mt in self._mtime(D, gid).items():
            if self.noti.get(n) == mt:
                continue
            foto = None
            pronta = self.foto_pronte.pop((gid, n), None)
            if pronta and time.time() - pronta[0] < 15:
                foto = pronta[1]
            else:
                h = finestra_gioco()
                foto = foto_finestra(h) if h else None
            p = file_stato(D, gid, n)
            for _ in range(40):  # aspetto che Dolphin finisca di scrivere (il file smette di cambiare)
                time.sleep(0.25)
                try:
                    if p.stat().st_mtime == mt:
                        break
                    mt = p.stat().st_mtime
                except OSError:
                    break
            self.noti[n] = mt
            try:
                salva_info_stato(D, gid, n, foto, self.sessione or codici_in_uso(D, gid), versione_exe_dolphin(self.exe_fn()))
                self.rev += 1
            except OSError as e:
                log_errore(f"stato {gid} {n}: {e}")

    def esegui(self):
        import time
        while not self.stop:
            try:
                self.giro()
            except Exception:  # noqa: BLE001
                import traceback
                log_errore(traceback.format_exc())
            time.sleep(0.4 if self.gid else 1.5)


# ---------------------------------------------------------------- primo avvio: Dolphin installato dall'app, gioco trovato nel PC
DOLPHIN_API = "https://dolphin-emu.org/update/latest/beta"  # quello che usa l'aggiornamento automatico di Dolphin
UA = {"User-Agent": "Mozilla/5.0 (SM2 Enhanced launcher)"}


def cartella_dolphin_app():
    """Dove l'app installa il suo Dolphin (portable: la cartella utente sta accanto all'exe, non tocca il resto del PC)."""
    return cartella_app() / "Dolphin"


def dolphin_dell_app(exe):
    return bool(exe) and cartella_dolphin_app() in Path(exe).parents


def ultima_dolphin():
    """{"versione": "2609", "url": <7z Windows>} dell'ultima release di Dolphin, None se il sito non risponde."""
    import platform
    import urllib.request
    try:
        with urllib.request.urlopen(urllib.request.Request(DOLPHIN_API, headers=UA), timeout=8) as r:
            d = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    arm = platform.machine().upper() in ("ARM64", "AARCH64")
    url = next((a["url"] for a in d.get("artifacts", []) if a.get("system") == ("Windows arm64" if arm else "Windows x64")), None)
    return {"versione": d.get("shortrev"), "url": url} if url else None


# ---------------------------------------------------------------- aggiornamenti dell'app
# Manifesto pubblico dell'ultima versione (JSON). Esempio:
#   {"versione": "1.1", "data": "2026-10-20", "note": {"it": ["...", "..."], "en": ["..."]},
#    "pagina": "https://www.patreon.com/...",            <- dove scaricarla a mano (si apre nel browser)
#    "exe": "https://github.com/.../Spider-Man.2.DE.exe", "sha256": "...", "byte": 24000000,   <- facoltativi: aggiorna da sola
#    "trasloco": "https://raw.githubusercontent.com/.../ultima.json"}   <- facoltativo: il manifesto si è spostato
# Repository PUBBLICO JohnSwingMods/launcher-updates (account del nome d'arte) (nome neutro, senza marchi; il codice dell'app sta in quello privato).
# TRASLOCO: l'indirizzo è scritto dentro ogni copia dell'app distribuita. Per spostare il manifesto (repository o nome
# utente rinominati) si lascia nel posto vecchio un manifesto con "trasloco": ogni app che lo legge salva il nuovo
# indirizzo (config agg_url) e da lì in poi guarda quello. SPIDEY_AGG_URL = altro indirizzo o un file locale (prove).
AGGIORNAMENTI_URL = "https://raw.githubusercontent.com/JohnSwingMods/launcher-updates/main/ultima.json"
HOST_EXE = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com", "raw.githubusercontent.com")


def versione_tupla(v):
    """"1.10.2" -> (1, 10, 2): confronto numerico (come stringhe "1.10" < "1.9")."""
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:4])


def _host_ok(url, host=HOST_EXE):
    from urllib.parse import urlparse
    u = urlparse(str(url or ""))
    if u.scheme == "file" and os.environ.get("SPIDEY_AGG_URL"):  # solo per le prove (manifesto locale)
        return True
    return u.scheme == "https" and any(u.hostname == h or (u.hostname or "").endswith("." + h) for h in host)


def _leggi_manifesto(url):
    import urllib.request
    try:
        if Path(url).is_file():
            d = json.loads(Path(url).read_text(encoding="utf-8"))
        else:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=8) as r:
                d = json.loads(r.read(200_000).decode("utf-8"))
    except Exception:  # noqa: BLE001 - rete, file rotto, IncompleteRead (non è un OSError): niente avviso
        return None
    return d if isinstance(d, dict) else None


def sostenitori_da(d):
    """Nomi dei sostenitori Swing++ dal manifesto pubblico ("sostenitori": [...]) per Impostazioni > Crediti: solo testo
    (niente < > e caratteri di controllo), max 40 caratteri l'uno, senza doppioni, max 500. None = il campo non c'è."""
    v = (d or {}).get("sostenitori")
    if not isinstance(v, list):
        return None
    out = []
    for x in v:
        s = re.sub(r"[\x00-\x1f<>]", "", str(x)).strip()[:40]
        if s and s not in out:
            out.append(s)
    return out[:500]


def ultima_app(url=None, trasloco=None, sostenitori=None):
    """Il manifesto dell'ultima versione dell'app se è PIÙ NUOVA di questa, altrimenti None (anche senza rete o se il file
    non c'è ancora). url = quello salvato da un trasloco (config agg_url); trasloco(nuovo_url) = da chiamare se il
    manifesto dice che si è spostato (lo salva nella config), poi lo rileggo da lì (un passo solo). Tiene solo i campi
    sicuri: exe solo da GitHub con sha256, pagina e trasloco solo https."""
    url = os.environ.get("SPIDEY_AGG_URL") or url or AGGIORNAMENTI_URL
    d = _leggi_manifesto(url)
    nuovo = str((d or {}).get("trasloco") or "")
    if nuovo.startswith("https://") and nuovo != url and not os.environ.get("SPIDEY_AGG_URL"):
        if trasloco:
            trasloco(nuovo)
        d = _leggi_manifesto(nuovo)
    if sostenitori and d is not None and (nomi := sostenitori_da(d)) is not None:  # i nomi valgono anche senza versione nuova
        sostenitori(nomi)
    if not d or versione_tupla(d.get("versione")) <= versione_tupla(VERSIONE_APP):
        return None
    note = d.get("note") if isinstance(d.get("note"), dict) else {}
    out = {"versione": str(d["versione"])[:20], "data": str(d.get("data") or "")[:20],
           "note": {str(k)[:5]: [str(x)[:300] for x in v][:12] for k, v in note.items() if isinstance(v, list)},
           "pagina": d.get("pagina") if str(d.get("pagina") or "").startswith("https://") else None, "exe": None}
    sha = str(d.get("sha256") or "").lower()
    if _host_ok(d.get("exe")) and re.fullmatch(r"[0-9a-f]{64}", sha):
        out.update(exe=d["exe"], sha256=sha, byte=int(d.get("byte") or 0))
    return out


class AggiornaApp:
    """Scarica la versione nuova dell'exe ACCANTO a quello in uso ("<nome>.nuovo.exe"), controlla peso e sha256, poi
    applica(): l'exe in uso si può rinominare anche aperto -> "<nome>.vecchio.exe", il nuovo prende il suo nome e parte
    con --aggiornato (aspetta che questo si chiuda e cancella il vecchio). Se qualcosa va storto rimette tutto com'era."""

    def __init__(self, info, exe):
        self.info, self.exe = info, Path(exe)
        self.nuovo = self.exe.with_name(self.exe.stem + ".nuovo.exe")
        self.vecchio = self.exe.with_name(self.exe.stem + ".vecchio.exe")
        self.fatti, self.totale, self.finito, self.errore, self.annulla = 0, int(info.get("byte") or 0), False, None, False
        self.app = True  # (per il JS: distingue questo lavoro dagli altri)

    def stato(self):
        return {"app": True, "fatti": self.fatti, "totale": self.totale, "finito": self.finito, "errore": self.errore,
                "versione": self.info["versione"]}

    def esegui(self):
        try:
            self._scarica()
        except Exception as e:  # noqa: BLE001
            import traceback
            log_errore(traceback.format_exc())
            self.errore = f"{type(e).__name__}: {e}"
            self.nuovo.unlink(missing_ok=True)
        finally:
            self.finito = True

    def _scarica(self):
        import urllib.request
        h = hashlib.sha256()
        with urllib.request.urlopen(urllib.request.Request(self.info["exe"], headers=UA), timeout=30) as r:
            if not _host_ok(r.geturl()):  # anche dopo i reindirizzamenti di GitHub
                raise RuntimeError("indirizzo non valido")
            self.totale = int(r.headers.get("Content-Length") or self.totale or 0)
            with open(self.nuovo, "wb") as out:
                while not self.annulla:
                    blocco = r.read(256 * 1024)
                    if not blocco:
                        break
                    out.write(blocco)
                    h.update(blocco)
                    self.fatti += len(blocco)
        if self.annulla:
            self.nuovo.unlink(missing_ok=True)
            raise RuntimeError("annullato")
        if h.hexdigest() != self.info["sha256"] or (self.info.get("byte") and self.fatti != self.info["byte"]):
            self.nuovo.unlink(missing_ok=True)
            raise RuntimeError("file scaricato non valido")

    def applica(self):
        """Scambia gli exe. Ritorna il percorso da avviare (None se non si può: tutto rimesso com'era)."""
        if not self.nuovo.is_file():
            return None
        try:
            self.vecchio.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            os.replace(self.exe, self.vecchio)
        except OSError:
            log_errore("aggiornamento: non riesco a rinominare l'exe in uso")
            return None
        try:
            os.replace(self.nuovo, self.exe)
        except OSError:
            os.replace(self.vecchio, self.exe)
            log_errore("aggiornamento: non riesco a mettere il nuovo exe")
            return None
        return self.exe


def dopo_aggiornamento(argv):
    """Exe appena aggiornato (--aggiornato <vecchio> <pid>): aspetta che la versione di prima si chiuda (se no la regola
    "un'app sola" farebbe chiudere questa) e cancella il vecchio exe. Ritorna True se l'app è stata appena aggiornata."""
    if "--aggiornato" not in argv:
        return False
    import time
    i = argv.index("--aggiornato")
    vecchio = Path(argv[i + 1]) if len(argv) > i + 1 else None
    pid = int(argv[i + 2]) if len(argv) > i + 2 and argv[i + 2].isdigit() else 0
    t0 = time.time()
    while pid and psutil.pid_exists(pid) and time.time() - t0 < 30:
        time.sleep(0.2)
    if vecchio and vecchio.name.endswith(".vecchio.exe"):
        def via():
            for _ in range(60):  # la cartella temporanea della versione di prima si libera qualche secondo dopo
                try:
                    vecchio.unlink(missing_ok=True)
                    return
                except OSError:
                    time.sleep(1)
        threading.Thread(target=via, daemon=True).start()
    return True


def id_disco(p):
    """ID del gioco scritto all'inizio del file del disco (anche negli rvz), None se non è Spider-Man 2."""
    try:
        with open(p, "rb") as fh:
            m = re.search(rb"GK2[A-Z]52", fh.read(0x20000))
    except OSError:
        return None
    return m.group().decode() if m and m.group().decode() in NOMI_VERSIONE else None


def cerca_dischi(cartelle, profondita=3, limite=25.0):
    """{ID: file} di Spider-Man 2 nelle cartelle date, al massimo 'limite' secondi. Prima le cartelle che sembrano di
    giochi (Giochi, Games, ROM, GameCube, Dolphin...), dove scende fino a 7 livelli; nelle altre solo fino a 'profondita'."""
    import heapq
    import time
    salta = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "appdata", "system volume information",
             "node_modules", ".git", "steamapps", "windowsapps", "recovery", "perflogs", "$winreagent", "msocache", "drivers",
             "site-packages", "__pycache__", "cache", "temp", "tmp", "library"}
    indizi = ("gioc", "game", "rom", "iso", "gamecube", "gcn", "nintendo", "dolphin", "retro", "emu", "spider", "console")
    t0, trovati, visti, n = time.time(), {}, set(), 0
    coda = []
    for base in cartelle:
        if Path(base).is_dir():
            heapq.heappush(coda, (0, n, Path(base), 0, False))
            n += 1
    while coda and time.time() - t0 < limite and len(trovati) < len(NOMI_VERSIONE):
        _, _, d, liv, giochi = heapq.heappop(coda)
        try:
            voci = list(os.scandir(d))
        except OSError:
            continue
        for e in voci:
            try:
                nome = e.name.lower()
                if e.is_dir(follow_symlinks=False):
                    if nome in salta or nome.startswith((".", "$")):
                        continue
                    g = giochi or any(x in nome for x in indizi)
                    if liv < (7 if g else profondita):
                        heapq.heappush(coda, ((liv + 1) - (4 if g else 0), n, Path(e.path), liv + 1, g))
                        n += 1
                elif nome.endswith(ESTENSIONI_DISCO) and e.path not in visti and e.stat().st_size > 50_000_000:
                    visti.add(e.path)
                    gid = id_disco(e.path)
                    if gid:
                        trovati.setdefault(gid, e.path)
            except OSError:
                continue
    return trovati


def cartelle_da_cercare():
    """Posti dove di solito si tengono i giochi: Desktop, Download, Documenti e le radici dei dischi."""
    casa = Path.home()
    out = [casa / "Desktop", cartella_download(), casa / "Documents", cartella_documenti(), casa / "Videos"]
    out += [Path(c) for c in cartelle_download_browser()]
    for lettera in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        radice = Path(f"{lettera}:\\")
        if os.path.exists(radice):
            out.append(radice)
    vista, res = set(), []
    for c in out:
        k = str(c).lower()
        if k not in vista:
            vista.add(k)
            res.append(c)
    return res


class InstallaDolphin:
    """Scarica l'ultima Dolphin dal sito ufficiale e la mette in cartella_dolphin_app() in modalità portable, già pronta:
    niente domanda sulle statistiche al primo avvio (risposta "no"), trucchi accesi. Aggiornando, la cartella User resta."""

    def __init__(self):
        self.fase, self.fatti, self.totale, self.finito, self.errore, self.annulla = "", 0, 0, False, None, False
        self.exe, self.versione = None, None

    def stato(self):
        return {"fase": self.fase, "fatti": self.fatti, "totale": self.totale, "finito": self.finito, "errore": self.errore,
                "dolphin": True, "exe": str(self.exe) if self.exe else None, "versione": self.versione}

    def esegui(self):
        try:
            self._installa()
        except Exception as e:  # noqa: BLE001
            import traceback
            log_errore(traceback.format_exc())
            self.errore = f"{type(e).__name__}: {e}"
        finally:
            self.finito = True

    def _installa(self):
        import subprocess
        import urllib.request
        self.fase = "cerco"
        info = ultima_dolphin()
        if not info:
            raise RuntimeError("sito Dolphin non raggiungibile")
        self.versione = info["versione"]
        base = cartella_dolphin_app()
        base.mkdir(parents=True, exist_ok=True)
        arch = base / Path(info["url"]).name
        self.fase = "scarico"
        with urllib.request.urlopen(urllib.request.Request(info["url"], headers=UA), timeout=30) as r, open(arch, "wb") as out:
            self.totale = int(r.headers.get("Content-Length") or 0)
            while True:
                if self.annulla:
                    break
                blocco = r.read(256 * 1024)
                if not blocco:
                    break
                out.write(blocco)
                self.fatti += len(blocco)
        if self.annulla:
            arch.unlink(missing_ok=True)
            return
        if self.totale and self.fatti != self.totale:  # download troncato: prima dava un errore dell'estrattore che non c'entrava
            arch.unlink(missing_ok=True)
            raise RuntimeError("download di Dolphin incompleto")
        try:
            self._metti(base, arch)
        finally:
            arch.unlink(missing_ok=True)  # anche se qualcosa va storto non resta un .7z da 20 MB in Documenti

    def _metti(self, base, arch):
        import subprocess
        self.fase = "estraggo"
        tmp = base / "_nuovo"
        _rimuovi(tmp)
        tmp.mkdir()
        tar = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"  # Windows apre i .7z da solo
        ok = tar.is_file() and subprocess.run([str(tar), "-xf", str(arch), "-C", str(tmp)], capture_output=True,
                                              creationflags=0x08000000, env=ambiente_figli()).returncode == 0
        if not ok:
            _estrai(arch, tmp)  # 7-Zip / WinRAR se ci sono
        exe = next(tmp.rglob("Dolphin.exe"), None)
        if not exe:
            raise RuntimeError("Dolphin.exe non trovato nell'archivio")
        # la nuova versione prende il posto della vecchia, la cartella User (impostazioni, salvataggi, texture) resta.
        # Prima la vecchia viene solo RINOMINATA (se cancellarla si fermava a metà, es. antivirus, restava una cartella
        # mezza vuota e User in _User: l'app non vedeva più Dolphin); User torna al suo posto anche se qualcosa va storto
        dest = base / "Dolphin-x64"
        utente = dest / "User"
        vecchio = base / "_vecchio"
        _rimuovi(vecchio)
        if dest.exists():
            dest.rename(vecchio)
        try:
            exe.parent.rename(dest)
        except OSError:
            if vecchio.exists() and not dest.exists():
                vecchio.rename(dest)  # rimetto quella di prima, User compreso
            raise
        if (vecchio / "User").exists():
            if utente.exists():
                _rimuovi(utente)  # (una User dentro l'archivio nuovo: vale quella dell'utente)
            (vecchio / "User").rename(utente)
        if not (vecchio / "User").exists():  # la vecchia si cancella solo se User è davvero passata alla nuova
            _rimuovi(vecchio)
        _rimuovi(tmp)
        (dest / "portable.txt").write_text("", encoding="utf-8")
        for sotto in ("Config", "GameSettings", "Load/Textures", "StateSaves"):
            (utente / sotto).mkdir(parents=True, exist_ok=True)
        ini = utente / "Config" / "Dolphin.ini"
        if not ini.exists():
            scrivi_ini_valori(ini, {("Analytics", "PermissionAsked"): "True", ("Analytics", "Enabled"): "False",
                                    ("Core", "EnableCheats"): "True", ("Interface", "ConfirmStop"): "False"})
        self.exe = dest / "Dolphin.exe"
        self.fase = "fatto"


class Musica:
    """Cosa sta suonando sul PC (Windows: qualsiasi app, Spotify compreso, anche senza account Premium) e comandi
    play/pausa, avanti, indietro. Usa contenuti/musica.ps1 (PowerShell + WinRT), tenuto aperto: niente librerie da
    installare e niente login."""

    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()

    def _avvia(self):
        import subprocess
        if self.proc and self.proc.poll() is None:
            return
        self.proc = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(contenuti() / "musica.ps1")],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     creationflags=0x08000000, text=True, encoding="utf-8", bufsize=1, env=ambiente_figli())

    def comando(self, cmd, attesa=6.0):
        import queue
        with self.lock:
            try:
                self._avvia()
                self.proc.stdin.write(cmd + "\n")
                self.proc.stdin.flush()
                q = queue.Queue()
                threading.Thread(target=lambda: q.put(self.proc.stdout.readline()), daemon=True).start()
                riga = q.get(timeout=attesa)
                return json.loads(riga) if riga.strip() else {"errore": "vuoto"}
            except Exception as e:  # noqa: BLE001 - la musica è un extra: mai bloccare il menu
                if self.proc:
                    self.proc.kill()
                self.proc = None
                return {"errore": str(e)}
