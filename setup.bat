@echo off
rem Setup de AutoViral AI para Windows (CMD o PowerShell).
rem Equivalente a setup.sh: crea el .venv, instala dependencias, prepara .env y verifica.
rem Requisitos: Python 3.11+ (python.org, marcar "Add to PATH") y ffmpeg (winget install ffmpeg).

setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo No se encontro Python. Instala Python 3.11+ desde https://www.python.org/downloads/
    echo y marca "Add python.exe to PATH" durante la instalacion.
    exit /b 1
)

echo ==^> Python:
py -3 --version

echo ==^> Creando entorno virtual en .venv ...
if not exist .venv (
    py -3 -m venv .venv
) else (
    echo     (.venv ya existe; se reutiliza^)
)

echo ==^> Instalando dependencias (requirements.txt) ...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo ==^> Preparando .env ...
if not exist .env (
    copy .env.example .env >nul
    echo     Se creo .env desde .env.example. Editalo y pega tus claves API.
) else (
    echo     .env ya existe; no se sobreescribe.
)

echo ==^> Configurando FFmpeg (imageio-ffmpeg fallback) ...
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo     ffmpeg no encontrado en PATH; intentando vincular desde imageio-ffmpeg...
    .venv\Scripts\python.exe -c "import imageio_ffmpeg, pathlib, shutil; p=imageio_ffmpeg.get_ffmpeg_exe(); print(p)" > "%TEMP%\ffmpeg_path.txt" 2>nul
    if exist "%TEMP%\ffmpeg_path.txt" (
        for /f "usebackq delims=" %%p in ("%TEMP%\ffmpeg_path.txt") do (
            if exist "%%p" (
                copy /y "%%p" ".venv\Scripts\ffmpeg.exe" >nul 2>nul
                rem NOTA: no copiamos ffprobe.exe (imageio-ffmpeg solo trae ffmpeg; son distintos).
                rem El pipeline usa mutagen + ffmpeg directo, ffprobe del sistema es opcional.
                echo     ffmpeg vinculado desde imageio-ffmpeg a .venv\Scripts\ffmpeg.exe
            )
        )
    )
    where ffmpeg >nul 2>nul
    if errorlevel 1 (
        if not exist ".venv\Scripts\ffmpeg.exe" (
            echo     AVISO: ffmpeg NO esta en el PATH ni en imageio-ffmpeg.
            echo     En Windows:  winget install ffmpeg     (o choco install ffmpeg)
            echo     Cierra y reabre la terminal despues de instalarlo.
        ) else (
            echo     ffmpeg OK (via .venv\Scripts\ffmpeg.exe con libass)
        )
    ) else (
        echo     ffmpeg OK
    )
) else (
    echo     ffmpeg OK
)

echo ==^> Chequeo del entorno ...
.venv\Scripts\python.exe scripts\verificar_entorno.py

echo.
echo ^✓ Listo. Siguientes pasos:
echo    1. Edita .env y pega tus claves API (GEMINI_API_KEY, QWEN_API_KEY, GCP_TTS_API_KEY).
echo    2. Abre tu agente (Claude Code / OpenCode) en esta carpeta y pide crear un video.

endlocal
