@echo off
chcp 65001 >nul
title BIST Hibrit v4.2 PWA - GitHub'a Tek Tikla Yukleyici
cd /d "%~dp0"

echo ============================================================================
echo   BIST HIBRIT ANALIZ v4.2 PWA — GITHUB PAGES VE BULUT YUKLEYICI
echo ============================================================================
echo.
echo Bu arac, projeyi GitHub deponuza yukler. Boylece bilgisayariniz kapali olsa
echo bile telefonunuzdan 7/24 acabilir ve Turkce sesli portfoy uyarisi alabilirsiniz.
echo.

python uygulama_motoru.py --snapshot-uret

if not exist ".git" (
    git init
    git branch -M main
)

git add .
git commit -m "feat: BIST Hibrit v4.2 PWA - 42 Hisse Tam Evren, Ilk 5 Oneri ve Turkce Sesli Portfoy Asistani"

echo.
set /p REPO_URL="Lutfen GitHub depo adresinizi yapistirin (Orn: https://github.com/kullanici/bist-pwa.git): "
if "%REPO_URL%"=="" (
    echo [UYARI] Depo adresi girilmedi. Daha sonra 'git remote add origin URL' ve 'git push -u origin main' yapabilirsiniz.
    pause
    exit /b
)

git remote remove origin >nul 2>&1
git remote add origin %REPO_URL%
git push -u origin main

echo.
echo ============================================================================
echo [BASARILI] Dosyalar GitHub'a yuklendi!
echo Simdi GitHub deponuzda Settings -> Pages -> Branch: main (Save) secin.
echo 1 dakika icinde telefonunuzdan https://KULLANICI_ADINIZ.github.io/DEPO_ADI/
echo adresine girip 'Ana Ekrana Ekle (PWA)' ve 'Sesli Uyari' ozelligini kullanabilirsiniz!
echo ============================================================================
pause
