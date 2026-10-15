@echo off
chcp 65001 >nul
set "APP_DIR=%~dp0"
set "PYTHON_EXE=D:\mamba\python.exe"

if not exist "%PYTHON_EXE%" (
  echo [错误] 找不到 %PYTHON_EXE%
  echo 请编辑本文件，把 PYTHON_EXE 改成可用的 Python 路径。
  pause
  exit /b 1
)

"%PYTHON_EXE%" "%APP_DIR%dds_dac_scope_tester.py"
if errorlevel 1 (
  echo.
  echo 程序异常退出，请保留上面的错误信息。
  pause
)
