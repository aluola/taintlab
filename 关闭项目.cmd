@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo 缺少项目虚拟环境："%~dp0.venv\Scripts\python.exe"
  if not exist "%~dp0results\v2\launcher" mkdir "%~dp0results\v2\launcher"
  >>"%~dp0results\v2\launcher\entry_errors.log" echo [%date% %time%] Missing environment: "%~dp0.venv\Scripts\python.exe"
  echo 首次准备：powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
  echo 模型准备：.venv\Scripts\python.exe scripts/model_prepare.py
  if /i not "%~1"=="--non-interactive" pause
  exit /b 1
)
if not exist "%~dp0scripts\project_lifecycle.py" (
  echo 缺少 scripts\project_lifecycle.py，请重新解压完整的项目轻量包。
  if not exist "%~dp0results\v2\launcher" mkdir "%~dp0results\v2\launcher"
  >>"%~dp0results\v2\launcher\entry_errors.log" echo [%date% %time%] Missing script: scripts\project_lifecycle.py
  if /i not "%~1"=="--non-interactive" pause
  exit /b 1
)
if not exist "%~dp0scripts\launch_model.py" (
  echo 缺少 scripts\launch_model.py，请从轻量包恢复该脚本。
  if not exist "%~dp0results\v2\launcher" mkdir "%~dp0results\v2\launcher"
  >>"%~dp0results\v2\launcher\entry_errors.log" echo [%date% %time%] Missing script: scripts\launch_model.py
  if /i not "%~1"=="--non-interactive" pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -u "%~dp0scripts\project_lifecycle.py" stop %*
set "launcher_exit=%errorlevel%"
if not "%launcher_exit%"=="0" (
  echo 详细错误见上方及 results\v2\launcher\。
  if /i not "%~1"=="--non-interactive" pause
)
exit /b %launcher_exit%
