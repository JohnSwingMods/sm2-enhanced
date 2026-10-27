"""Scrive versione_exe.txt (proprietà dell'exe: tasto destro > Proprietà > Dettagli) da app_core.VERSIONE_APP, così la
versione si cambia in un posto solo (la usa anche l'avviso di aggiornamento). Lo lancia build_app.bat."""
from pathlib import Path

import app_core

v = [int(x) for x in app_core.versione_tupla(app_core.VERSIONE_APP)]
v = (v + [0, 0, 0, 0])[:4]
testo = f"""# Proprietà del file .exe (tasto destro > Proprietà > Dettagli). Generato da crea_versione_exe.py: NON modificarlo a mano,
# cambia VERSIONE_APP in app_core.py.
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({v[0]}, {v[1]}, {v[2]}, {v[3]}), prodvers=({v[0]}, {v[1]}, {v[2]}, {v[3]}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041004B0', [
      StringStruct('CompanyName', 'John Swing'),
      StringStruct('FileDescription', '{app_core.NOME_APP} - unofficial fan launcher'),
      StringStruct('FileVersion', '{v[0]}.{v[1]}.{v[2]}'),
      StringStruct('InternalName', '{app_core.NOME_APP}'),
      StringStruct('OriginalFilename', '{app_core.NOME_APP}.exe'),
      StringStruct('ProductName', '{app_core.NOME_APP}'),
      StringStruct('ProductVersion', '{v[0]}.{v[1]}.{v[2]}')])]),
    VarFileInfo([VarStruct('Translation', [1040, 1200])])
  ]
)
"""
if __name__ == "__main__":
    Path(__file__).with_name("versione_exe.txt").write_text(testo, encoding="utf-8")
    print("versione_exe.txt:", app_core.NOME_APP, app_core.VERSIONE_APP)
