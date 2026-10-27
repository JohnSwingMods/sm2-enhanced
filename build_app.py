"""Crea l'app in dist/"SM2 Enhanced.exe" (un solo file, con icona, pagine, contenuti, salvataggi 100% e texconv).
Una sola edizione, tutto gratis (la "Plus" è stata tolta il 2026-10-27). Un exe in uso (aperto) viene rinominato
"(vecchia, cancellala)" e quello nuovo va al suo posto. Uso: python build_app.py"""
import subprocess
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parent
NOME = "SM2 Enhanced"


def py(*a):
    subprocess.run([sys.executable, *a], cwd=QUI, check=True)


def build():
    nome = NOME
    py("crea_versione_exe.py")
    exe = QUI / "dist" / f"{nome}.exe"
    if exe.exists():
        try:
            exe.unlink()
        except PermissionError:  # aperto: un exe in uso si può rinominare, non cancellare
            k = 1
            while (vecchio := exe.with_name(f"{nome} (vecchia, cancellala){'' if k == 1 else f' {k}'}.exe")).exists():
                k += 1
            exe.rename(vecchio)
            print("in uso, rinominato:", vecchio.name)
    py("-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed", "--name", nome, "--icon", "spidey_app.ico",
       "--version-file", "versione_exe.txt",
       "--add-data", "app_web;app_web", "--add-data", "contenuti;contenuti",
       # salvataggi 100% (facoltativi: non sono nel codice pubblico; senza, l'installer non li mette)
       *(["--add-data", "pack_salvataggi;pack_salvataggi"] if (QUI / "pack_salvataggi").is_dir() else []),
       "--add-data", "tools/texconv.exe;tools", "--add-data", "tools/texconv_LICENSE.txt;tools",
       "--add-data", "codici_db.json;.", "--add-data", "moddb_catalogo.json;.", "--add-data", "spidey_app.ico;.",
       *[x for m in ("numpy", "unittest", "pytest", "customtkinter", "tkinter", "PIL.AvifImagePlugin", "PIL._avif") for x in ("--exclude-module", m)],
       "--hidden-import", "lz4.block", "--hidden-import", "modello_disco", "--hidden-import", "ora", "--hidden-import", "teletrasporto", "--hidden-import", "mirino", "spidey_app.py")
    print("fatto:", exe)


if __name__ == "__main__":
    py("crea_icona_app.py")
    py("crea_lingue.py")
    py("crea_licenze.py")
    build()
    # solo per lo sviluppo (non va distribuito): apre l'app in "prova da zero", come su un PC dove non c'è niente
    (QUI / "dist" / "Prova da zero (solo sviluppo).bat").write_text('@start "" "%~dp0SM2 Enhanced.exe" --da-zero\n', encoding="utf-8")
