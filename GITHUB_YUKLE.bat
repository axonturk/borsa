@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================================
echo   BIST HİBRİT ANALİZ v4.5 PWA — CANLI VERİ ÇEK VE GITHUB BULUTA YÜKLE
echo   Canlı Adres: https://axonturk.github.io/borsa/
echo ============================================================================
echo.
echo [1/3] 42 BIST hissesi için güncel canlı Borsa İstanbul verileri çekiliyor...
python uygulama_motoru.py --snapshot-uret
echo.
echo [2/3] Değişiklikler Git paketine ekleniyor...
git add index.html uygulama_motoru.py dogrulanmis_piyasa_snapshot.json senaryo_defteri_v4.json manifest.json sw.js GITHUB_YUKLE.bat
git commit -m "Canli BIST Snapshot Guncellemesi (%DATE% %TIME%)"
echo.
echo [3/3] https://github.com/axonturk/borsa deposuna gönderiliyor...
git push origin main
echo.
echo ============================================================================
echo   TAMAMLANDI! Canlı PWA Uygulama Adresiniz:
echo   https://axonturk.github.io/borsa/
echo ============================================================================
pause
