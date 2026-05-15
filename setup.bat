@echo off
setlocal enabledelayedexpansion
title MengPo Setup

echo.
echo   ============================================
echo     MengPo - Memory Evolution Orchestrator
echo     v0.12.0
echo   ============================================
echo.

:: ── Step 0: find Python ──
set PYTHON=
for %%p in (python3 python python3.11 python3.10) do (
    where %%p >nul 2>&1
    if !errorlevel!==0 (
        %%p -c "import sys; exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
        if !errorlevel!==0 set PYTHON=%%p
    )
    if defined PYTHON goto :found_python
)
echo [ERROR] Python 3.10+ not found. Install from https://www.python.org/downloads/
pause & exit /b 1

:found_python
!PYTHON! --version
echo.

:: ── Step 1: pip mirror auto-select ──
set MIRROR=
for %%m in (
    "https://mirrors.aliyun.com/pypi/simple/"
    "https://pypi.tuna.tsinghua.edu.cn/simple/"
    "https://pypi.org/simple/"
) do (
    echo Trying mirror: %%~m
    !PYTHON! -m pip install --quiet --upgrade pip -i %%~m >nul 2>&1
    if !errorlevel!==0 (
        set MIRROR=%%~m
        goto :mirror_ok
    )
)
echo [WARN] No mirror reachable, falling back to default PyPI
set MIRROR=

:mirror_ok
echo Mirror: !MIRROR!
echo.

:: ── Step 2: install deps ──
echo [2/3] Installing dependencies...
if defined MIRROR (
    !PYTHON! -m pip install -r requirements.txt -i !MIRROR! --quiet
) else (
    !PYTHON! -m pip install -r requirements.txt --quiet
)
if !errorlevel!==0 (
    echo   Done.
) else (
    echo   [WARN] pip install had errors. Trying offline fallback...
    if exist "python\Lib\site-packages\" (
        echo   python/ runtime detected, skipping.
    ) else (
        echo   [ERROR] Cannot install dependencies. Check network.
        pause & exit /b 1
    )
)
echo.

:: ── Step 3: verify MengPo server ──
echo [3/3] Verifying MengPo server...
!PYTHON! -c "from memory_mcp.server import mcp; print('  MengPo ready,', len(mcp._tool_manager._tools), 'tools loaded')" 2>nul
if !errorlevel!==0 goto :done

echo   [WARN] Direct import failed (expected if CWD != repo root).
echo   Trying with PYTHONPATH...
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
!PYTHON! -c "from memory_mcp.server import mcp; print('  MengPo ready,', len(mcp._tool_manager._tools), 'tools loaded')" 2>nul
if !errorlevel!==0 goto :done

echo   [ERROR] MengPo import failed. Check that you are in the repo root.
pause & exit /b 1

:done
echo.
echo   ============================================
echo     MengPo setup complete.
echo     Run: !PYTHON! -m memory_mcp.server
echo   ============================================
echo.
endlocal
