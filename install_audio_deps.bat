@echo off
setlocal

echo ========================================
echo  IP Speaker audio dependency installer
echo ========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Cannot find python in PATH.
    echo Please install Python or run this from the same environment used by app.py.
    echo.
    pause
    exit /b 1
)

python -c "import sounddevice, numpy" >nul 2>nul
if not errorlevel 1 (
    echo [OK] sounddevice and numpy are already installed.
    echo.
    pause
    exit /b 0
)

echo Some audio dependencies are missing.
echo Checking details...
echo.

python -c "import sounddevice; print('sounddevice OK')" >nul 2>nul
if errorlevel 1 (
    echo [MISSING] sounddevice
) else (
    echo [OK] sounddevice
)

python -c "import numpy; print('numpy OK')" >nul 2>nul
if errorlevel 1 (
    echo [MISSING] numpy
) else (
    echo [OK] numpy
)

echo.
echo Installing missing packages...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to upgrade pip.
    echo Trying to install packages anyway...
)

python -m pip install sounddevice numpy
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install sounddevice/numpy.
    echo Please try manually:
    echo python -m pip install sounddevice numpy
    echo.
    pause
    exit /b 1
)

echo.
python -c "import sounddevice, numpy; print('[OK] sounddevice and numpy are ready')"
if errorlevel 1 (
    echo [ERROR] Install finished, but Python still cannot import the packages.
    echo Please check whether app.py uses a different Python environment.
    echo.
    pause
    exit /b 1
)

echo.
echo Done.
pause
exit /b 0
