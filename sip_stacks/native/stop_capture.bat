@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if not %errorlevel%==0 (
    echo Please run this file as Administrator.
    echo Right-click stop_capture.bat and choose "Run as administrator".
    pause
    exit /b 1
)

if not exist captures mkdir captures

echo Stopping capture...
pktmon stop

echo Converting ETL to PCAPNG...
pktmon etl2pcap "%~dp0captures\ip_speaker_trace.etl" --out "%~dp0captures\ip_speaker_trace.pcapng"

echo Removing pktmon filters...
pktmon filter remove

echo.
echo Capture file:
echo %~dp0captures\ip_speaker_trace.pcapng
echo.
echo Open this file with Wireshark and use display filters from TROUBLESHOOTING_NATIVE_RTP.md.
echo.
pause
