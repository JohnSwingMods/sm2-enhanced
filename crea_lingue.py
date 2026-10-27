"""Crea app_web/lingue.js (testi dell'app in 5 lingue) da testi_it_en.json + traduzioni_app.py.
Per aggiungere un testo: mettilo in testi_it_en.json (it/en) e in DE/FR/ES di traduzioni_app.py, poi rilancia."""
import json

from traduzioni_app import DE, ES, FR

base = json.load(open("testi_it_en.json", encoding="utf-8"))
lingue = {"it": base["it"], "en": base["en"], "de": DE, "fr": FR, "es": ES}
chiavi = list(base["it"])
for nome, d in lingue.items():
    mancano = [k for k in chiavi if k not in d]
    in_piu = [k for k in d if k not in chiavi]
    if mancano or in_piu:
        print(f"{nome}: mancano {mancano}  in più {in_piu}")
    for k in chiavi:  # controllo segnaposto {0} {1} uguali
        if k in d and sorted(set(__import__('re').findall(r"\{\d\}", d[k]))) != sorted(set(__import__('re').findall(r"\{\d\}", base["it"][k]))):
            print(f"{nome}.{k}: segnaposto diversi")
js = "// Generato da crea_lingue.py: non modificare a mano.\n\"use strict\";\nconst TESTI = " + json.dumps(
    lingue, ensure_ascii=False, indent=1) + ";\n"
open("app_web/lingue.js", "w", encoding="utf-8").write(js)
print("lingue.js:", {k: len(v) for k, v in lingue.items()})
