@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if not %errorlevel%==0 (
    echo Please run this file as Administrator.
    echo Right-click start_capture.bat and choose "Run as administrator".
    pause
    exit /b 1
)

if not exist captures mkdir captures

echo Stopping old pktmon session if any...
pktmon stop >nul 2>&1

echo Removing old pktmon filters...
pktmon filter remove

echo Adding filter: UDP packets to/from IP Speaker 192.168.6.120
pktmon filter add IP_Speaker_UDP -i 192.168.6.120 -t UDP

echo.
echo Starting capture...
echo Now run python app.py and press Test Call / Play Test Audio.
echo After the test finishes, run stop_capture.bat as Administrator.
echo.
pktmon start --capture --comp nics --pkt-size 0 --file-name "%~dp0captures\ip_speaker_trace.etl"

pause
