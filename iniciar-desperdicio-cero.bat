@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    py -3 -m venv .venv
    if errorlevel 1 goto error
)

if not exist ".venv\.deps-ready" (
    echo Instalando dependencias...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto error
    type nul > ".venv\.deps-ready"
)

if not exist ".env" copy ".env.example" ".env" >nul
echo.
echo DESPERDICIO CERO estara disponible en:
echo   - En esta PC: http://localhost:5000 (o http://127.0.0.1:5000)
echo   - En tu celular (conectado al mismo WiFi): http://192.168.1.14:5000
echo.
echo Deja esta ventana abierta. Pulsa Ctrl+C para detener el servidor.
echo.
".venv\Scripts\python.exe" run.py
goto end

:error
echo.
echo No se pudo preparar el entorno. Revisa que Python 3 este instalado y disponible como py.
pause
:end
endlocal
