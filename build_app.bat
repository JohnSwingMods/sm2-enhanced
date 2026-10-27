@echo off
rem Crea dist\SM2 Enhanced.exe (una sola edizione, tutto gratis). Vedi build_app.py.
cd /d "%~dp0"
python build_app.py %*
