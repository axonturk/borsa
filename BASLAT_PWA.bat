@echo off
chcp 65001 >nul
title BIST Hibrit Analiz v4.0 PWA Sunucusu
cd /d "%~dp0"
echo ============================================================================
echo   BIST HIBRIT ANALIZ, ADIL DEGER VE 4 SENARYOLU PORTFOY SIMULATORU v4.0 PWA
echo ============================================================================
echo Sunucu baslatiliyor (http://127.0.0.1:8765)...
start "" "http://127.0.0.1:8765/index.html"
python uygulama_motoru.py
pause
