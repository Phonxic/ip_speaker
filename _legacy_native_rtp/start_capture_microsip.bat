@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if not %errorlevel%==0 (
    echo Please run this file as Administrator.
    echo Right-click start_capture_microsip.bat and choose "Run as administrator".
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
echo Starting MicroSIP success-call capture...
echo Now use MicroSIP manually to call sip:4267@192.168.6.120 and play audio successfully.
echo After the successful test finishes, run stop_capture_microsip.bat as Administrator.
echo.
pktmon start --capture --comp nics --pkt-size 0 --file-name "%~dp0captures\microsip_success_trace.etl"

pause
