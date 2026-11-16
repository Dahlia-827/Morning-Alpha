@echo off
cd /d "%~dp0"
set "PYTHON_EXE="
where py >nul 2>nul && set "PYTHON_EXE=py -3"
if not defined PYTHON_EXE where python >nul 2>nul && set "PYTHON_EXE=python"
if not defined PYTHON_EXE if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not defined PYTHON_EXE (
  echo 未找到 Python 3。请安装 Python 3 后重新运行此文件。
  pause
  exit /b 1
)
%PYTHON_EXE% server.py
pause
