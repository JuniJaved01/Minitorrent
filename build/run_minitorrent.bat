@echo off
title MiniTorrent
cd /d "%~dp0"
echo ==============================================
echo   MiniTorrent P2P File Sharing System
echo ==============================================
echo.
echo Starting application...
echo Default URL: http://localhost:9090
echo (If that port is blocked, the app will
echo  automatically find the next free port.)
echo.
minitorrent.exe
echo.
echo Application stopped.
pause
