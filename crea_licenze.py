"""Scrive contenuti/LICENZE.txt: le licenze dei programmi e delle librerie che finiscono dentro SM2 Enhanced.exe (le licenze
MIT/BSD chiedono di distribuire il loro testo insieme al programma). La lancia build_app.bat prima di PyInstaller; nell'app
si apre da Impostazioni > Crediti e licenze."""
import importlib.metadata as md
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parent
USCITA = QUI / "contenuti" / "LICENZE.txt"
# (pacchetto, a cosa serve)
PACCHETTI = [
    ("pywebview", "finestra dell'app"),
    ("pythonnet", "pywebview su Windows"),
    ("clr_loader", "pywebview su Windows"),
    ("bottle", "pywebview (server delle pagine)"),
    ("proxy_tools", "pywebview"),
    ("pillow", "immagini e texture"),
    ("psutil", "processi di Dolphin"),
    ("lz4", "stati salvati di Dolphin"),
    ("dolphin-memory-engine", "lettura della memoria del gioco"),
    ("cffi", "dipendenza"),
    ("pycparser", "dipendenza"),
    ("typing_extensions", "dipendenza"),
    ("pyinstaller", "crea l'eseguibile (licenza GPL con eccezione: il programma creato non è vincolato dalla GPL)"),
]
MIT_PROXY = """MIT License (proxy_tools, https://github.com/jtushman/proxy_tools)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE."""


def testo_licenza(nome):
    for f in md.files(nome) or []:
        n = str(f).upper()
        if ("LICEN" in n or "COPYING" in n) and not n.endswith((".PY", ".PYC")):
            try:
                return Path(f.locate()).read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                pass
    return MIT_PROXY if nome == "proxy_tools" else "(testo della licenza non trovato nel pacchetto)"


def main():
    sep = "=" * 78
    parti = [
        "SM2 ENHANCED - LICENZE DEI COMPONENTI / THIRD-PARTY LICENSES",
        sep,
        "SM2 Enhanced è un progetto di fan non ufficiale, non affiliato né approvato da Marvel, Activision o Treyarch.",
        "Unofficial fan project, not affiliated with or endorsed by Marvel, Activision or Treyarch.",
        "",
        "NON inclusi nell'app / NOT included in the app:",
        "  - Dolphin Emulator (GPL-2.0-or-later): l'app lo scarica dal sito ufficiale dolphin-emu.org se lo chiedi.",
        "  - Microsoft Edge WebView2 Runtime: già presente in Windows 10/11, usato per mostrare l'app.",
        "  - Il gioco: serve il tuo disco originale. Modello 3D e costume originale vengono ricavati dal tuo disco.",
        "  - Le mod della community: si scaricano dalle loro pagine su ModDB.",
        "",
    ]
    tex = QUI / "tools" / "texconv_LICENSE.txt"
    parti += [sep, "texconv (Microsoft DirectXTex) - conversione delle texture in DDS", sep,
              tex.read_text(encoding="utf-8", errors="replace").strip() if tex.is_file() else "MIT License (Microsoft)", ""]
    py_lic = Path(sys.base_prefix) / "LICENSE.txt"
    parti += [sep, f"Python {sys.version.split()[0]} (Python Software Foundation License)", sep,
              py_lic.read_text(encoding="utf-8", errors="replace").strip() if py_lic.is_file() else "PSF License Version 2", ""]
    for nome, uso in PACCHETTI:
        try:
            v = md.version(nome)
        except md.PackageNotFoundError:
            continue
        parti += [sep, f"{nome} {v} - {uso}", sep, testo_licenza(nome), ""]
    USCITA.write_text("\n".join(parti).replace("\r\n", "\n").replace("\n", "\r\n"), encoding="utf-8")
    print("scritto", USCITA, USCITA.stat().st_size, "byte")


if __name__ == "__main__":
    main()
