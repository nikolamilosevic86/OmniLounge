@echo off
REM Single-command local dev bootstrap for Windows: creates .env if
REM missing, installs Node + Python dependencies if needed, then starts
REM the database, backend, and frontend together (same as `npm run dev`).
REM
REM Usage: run.bat
setlocal

cd /d "%~dp0"

if not exist ".env" (
  echo No .env found -- generating one from .env.example ^(random dev JWT secret, local registration enabled^).
  where python3 >nul 2>nul
  if errorlevel 1 (
    call python scripts\generate_env.py
  ) else (
    call python3 scripts\generate_env.py
  )
  echo Edit .env to add real secrets/OAuth2 credentials before deploying anywhere but localhost.
)

REM Activating an existing .venv (if present) puts its python/pip on PATH,
REM so the `python3 -m server.main` call inside `npm run dev` picks up the
REM right interpreter too -- this script doesn't create a venv itself, it
REM only uses one if you've already set one up.
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
)

if not exist "node_modules" (
  echo Installing Node dependencies...
  call npm install
  if errorlevel 1 exit /b 1
)

echo Installing Python dependencies...
call pip install -q -r requirements.txt
if errorlevel 1 exit /b 1

echo Starting OmniLaunge (Postgres + backend + frontend)...
call npm run dev
