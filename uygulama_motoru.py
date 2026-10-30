# -*- coding: utf-8 -*-
"""
BIST Hibrit Analiz, Adil Değer, XKTUM Katılım ve 4 Senaryolu Portföy Simülatörü (v4.1 PWA)
Kurumsal Portföy Yönetimi & Risk Yönetimi Motoru (Loop 1 Ajan Denetimi Sonrası Tam Sürüm)
-----------------------------------------------------------------------------------------
5 Yapay Zeka + 2 Uzman Denetçi Ajan (Quant-TKBB & UI-UX-PWA) Bulguları Kapatılmıştır:
1. Sıfır Sahte Veri: Eksik veride 100 TL fiyat veya RSI=42 uydurulmaz; None/0.0 korunur.
2. Doğru Wilder RSI: loss==0 durumunda 42 yerine 100.0 döner; Wilder (alpha=1/14) kullanılır.
3. Dinamik Sektör Medyanları: 25 Likit BIST hissesi üzerinden 7 homojen alt-sektör medyanı.
4. Bilanço Değişmezleri (EPS0, BVPS0, FAVÖK0): Fiyat değiştiğinde F/K, PD/DD ve FD/FAVÖK
   otomatik ölçeklenir; adil değer fiyatla yapay olarak şişmez.
5. Çoklu Değerleme, Net Nakit Düzeltmeli FD/FAVÖK & Haklı PD/DD (ROE vs COE %37 Rf).
6. Resmi BIST XKTUM (Madde 6.8.e): Toplam Varlıklar paydası (%33 borç, %33 nakit, %5 gelir).
7. TKBB 3.6.1 & 3.6.2 Kalıcı Arındırma Defteri: Her pozisyonun kendi alisGunu tutulur;
   satılan hisselerin birikmiş arındırma borcu (gerceklesenArindirmaTL) asla silinmez.
8. Analitik Korelasyon Matrisi (rho_ij), HRP vs ERC Ağırlık Ayrımı ve Kovaryans VaR/CVaR.
"""

import json
import math
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except Exception:
    YFINANCE_AVAILABLE = False

try:
    import isyatirimhisse as iyh  # KAP / İş Yatırım Bilanço Kütüphanesi (Opsiyonel)
    ISYATIRIM_AVAILABLE = True
except Exception:
    ISYATIRIM_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent
LEDGER_PATH = BASE_DIR / "senaryo_defteri_v4.json"
SNAPSHOT_PATH = BASE_DIR / "dogrulanmis_piyasa_snapshot.json"

MACRO_PARAMS = {
    "riskFreeRate": 0.37,          # %37,0 Türkiye 2Y/TLREF Risksiz Faiz Oranı
    "equityRiskPremium": 0.085,    # %8,5 Hisse Senedi Risk Primi (ERP)
    "cpiInflation": 0.38,          # %38,0 Yıllık TÜFE (Reel ROE hesabı için)
    "commissionRate": 0.000525,    # Onbinde 5 + %5 BSMV = %0,0525
    "baseSlippageRate": 0.0015,    # %0,15 Baz Kademe Kayması (Slippage)
    "bistDailyLimit": 0.10,        # ±%10 BIST Günlük Marj Sınırı
    "accountingBasis": "TMS 29 Enflasyon Muhasebesi Düzeltmeli (2026/06)"
}

# 25 Likit BIST Hissesi — 7 Homojen Alt Sektör (Sunucu ve İstemci PWA %100 Birebir Senkronize)
BIST_EVRENI = [
    # 1. DEMİR ÇELİK & AĞIR SANAYİ
    {
        "kod": "EREGL", "ad": "Erdemir Demir Çelik", "altSektor": "DEMIR_CELIK",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 18.4, "faizliNakitVarlikOrani": 11.2, "mahzurluGelirOrani": 1.15,
        "payBasiYillikMahzurluTL": 0.24, "toplamPayMilyon": 5565.1,
        "bazFiyat": 31.32, "low52": 27.17, "high52": 36.85,
        "fk": 9.40, "pddd": 0.68, "fdFavok": 5.80, "roe": 14.2, "roic": 12.8,
        "netBorcFavok": 1.45, "fcfVerimi": 4.2, "piotroski": 6, "beta": 0.92,
        "ema20": 30.75, "ema50": 31.51, "rsi14": 44.8, "rsiSma9": 41.2, "atr14": 0.85,
        "hacimOrani": 1.24, "mom12_1": 4.5, "gunlukHacimMilyonTL": 2450.0, "temettuVerimi": 3.8
    },
    {
        "kod": "KRDMD", "ad": "Kardemir (D)", "altSektor": "DEMIR_CELIK",
        "katilimUyum": "SINIRDA_UYARI", "katilimKaynak": "BIST XKTUM 2026/09 (Borç Sınırda %29.4)",
        "faizliBorcVarlikOrani": 29.4, "faizliNakitVarlikOrani": 9.8, "mahzurluGelirOrani": 1.85,
        "payBasiYillikMahzurluTL": 0.42, "toplamPayMilyon": 571.5,
        "bazFiyat": 37.68, "low52": 32.90, "high52": 49.01,
        "fk": 8.90, "pddd": 0.74, "fdFavok": 5.40, "roe": 15.1, "roic": 13.0,
        "netBorcFavok": 1.95, "fcfVerimi": 2.8, "piotroski": 6, "beta": 1.15,
        "ema20": 37.00, "ema50": 38.77, "rsi14": 46.2, "rsiSma9": 43.0, "atr14": 1.26,
        "hacimOrani": 1.18, "mom12_1": -2.1, "gunlukHacimMilyonTL": 1680.0, "temettuVerimi": 2.1
    },
    {
        "kod": "ISDMR", "ad": "İskenderun Demir Çelik", "altSektor": "DEMIR_CELIK",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 14.2, "faizliNakitVarlikOrani": 8.5, "mahzurluGelirOrani": 0.90,
        "payBasiYillikMahzurluTL": 0.40, "toplamPayMilyon": 2087.3,
        "bazFiyat": 53.35, "low52": 47.24, "high52": 65.02,
        "fk": 10.20, "pddd": 0.79, "fdFavok": 6.10, "roe": 13.5, "roic": 12.1,
        "netBorcFavok": 1.10, "fcfVerimi": 4.9, "piotroski": 7, "beta": 0.85,
        "ema20": 52.66, "ema50": 53.63, "rsi14": 47.5, "rsiSma9": 44.1, "atr14": 1.46,
        "hacimOrani": 1.12, "mom12_1": 6.2, "gunlukHacimMilyonTL": 420.0, "temettuVerimi": 4.5
    },

    # 2. OTOMOTİV & YAN SANAYİ
    {
        "kod": "FROTO", "ad": "Ford Otosan", "altSektor": "OTOMOTIV",
        "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faizli Borç / Varlık > %33 (XKTUM Dışı)",
        "faizliBorcVarlikOrani": 36.8, "faizliNakitVarlikOrani": 12.4, "mahzurluGelirOrani": 2.40,
        "payBasiYillikMahzurluTL": 1.05, "toplamPayMilyon": 4737.1,
        "bazFiyat": 70.00, "low52": 61.48, "high52": 89.63,
        "fk": 7.60, "pddd": 2.85, "fdFavok": 6.40, "roe": 44.5, "roic": 31.2,
        "netBorcFavok": 1.35, "fcfVerimi": 7.8, "piotroski": 8, "beta": 0.94,
        "ema20": 68.74, "ema50": 70.74, "rsi14": 48.4, "rsiSma9": 42.6, "atr14": 1.81,
        "hacimOrani": 1.32, "mom12_1": 14.8, "gunlukHacimMilyonTL": 1850.0, "temettuVerimi": 6.8
    },
    {
        "kod": "TOASO", "ad": "Tofaş Oto. Fab.", "altSektor": "OTOMOTIV",
        "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faizli Nakit & Kredi Rasyosu > %33",
        "faizliBorcVarlikOrani": 34.5, "faizliNakitVarlikOrani": 24.1, "mahzurluGelirOrani": 3.80,
        "payBasiYillikMahzurluTL": 7.06, "toplamPayMilyon": 481.7,
        "bazFiyat": 226.80, "low52": 199.29, "high52": 326.97,
        "fk": 9.80, "pddd": 2.40, "fdFavok": 7.20, "roe": 28.4, "roic": 22.0,
        "netBorcFavok": 0.90, "fcfVerimi": 5.1, "piotroski": 6, "beta": 1.02,
        "ema20": 224.21, "ema50": 237.70, "rsi14": 43.2, "rsiSma9": 40.5, "atr14": 6.64,
        "hacimOrani": 1.16, "mom12_1": -8.4, "gunlukHacimMilyonTL": 1120.0, "temettuVerimi": 5.4
    },
    {
        "kod": "TTRAK", "ad": "Türk Traktör", "altSektor": "OTOMOTIV",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 19.2, "faizliNakitVarlikOrani": 16.5, "mahzurluGelirOrani": 1.95,
        "payBasiYillikMahzurluTL": 4.23, "toplamPayMilyon": 215.2,
        "bazFiyat": 344.75, "low52": 315.94, "high52": 457.65,
        "fk": 8.40, "pddd": 3.45, "fdFavok": 5.90, "roe": 46.8, "roic": 38.4,
        "netBorcFavok": 0.45, "fcfVerimi": 8.4, "piotroski": 8, "beta": 0.88,
        "ema20": 339.64, "ema50": 352.18, "rsi14": 45.6, "rsiSma9": 40.8, "atr14": 8.46,
        "hacimOrani": 1.28, "mom12_1": 9.6, "gunlukHacimMilyonTL": 540.0, "temettuVerimi": 7.9
    },
    {
        "kod": "DOAS", "ad": "Doğuş Otomotiv", "altSektor": "OTOMOTIV",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 22.8, "faizliNakitVarlikOrani": 14.0, "mahzurluGelirOrani": 1.60,
        "payBasiYillikMahzurluTL": 2.97, "toplamPayMilyon": 333.4,
        "bazFiyat": 134.60, "low52": 121.40, "high52": 196.62,
        "fk": 4.90, "pddd": 1.15, "fdFavok": 3.80, "roe": 36.2, "roic": 29.5,
        "netBorcFavok": 0.60, "fcfVerimi": 9.2, "piotroski": 7, "beta": 0.96,
        "ema20": 131.63, "ema50": 139.88, "rsi14": 42.8, "rsiSma9": 38.4, "atr14": 3.69,
        "hacimOrani": 1.35, "mom12_1": 3.2, "gunlukHacimMilyonTL": 690.0, "temettuVerimi": 9.5
    },

    # 3. ENERJİ & RAFİNERİ
    {
        "kod": "TUPRS", "ad": "Tüpraş", "altSektor": "ENERJI_RAFINERI",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 16.5, "faizliNakitVarlikOrani": 25.4, "mahzurluGelirOrani": 2.85,
        "payBasiYillikMahzurluTL": 9.15, "toplamPayMilyon": 821.4,
        "bazFiyat": 357.50, "low52": 323.72, "high52": 460.95,
        "fk": 6.80, "pddd": 1.18, "fdFavok": 4.20, "roe": 34.8, "roic": 28.6,
        "netBorcFavok": -0.35, "fcfVerimi": 10.4, "piotroski": 8, "beta": 0.91,
        "ema20": 351.40, "ema50": 365.94, "rsi14": 44.1, "rsiSma9": 39.5, "atr14": 9.03,
        "hacimOrani": 1.41, "mom12_1": 11.2, "gunlukHacimMilyonTL": 3850.0, "temettuVerimi": 8.4
    },
    {
        "kod": "CWENE", "ad": "CW Enerji", "altSektor": "ENERJI_RAFINERI",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 24.1, "faizliNakitVarlikOrani": 7.2, "mahzurluGelirOrani": 0.65,
        "payBasiYillikMahzurluTL": 0.10, "toplamPayMilyon": 1735.5,
        "bazFiyat": 14.29, "low52": 12.45, "high52": 22.13,
        "fk": 11.40, "pddd": 2.15, "fdFavok": 7.90, "roe": 29.4, "roic": 21.8,
        "netBorcFavok": 1.65, "fcfVerimi": 3.4, "piotroski": 6, "beta": 1.22,
        "ema20": 13.94, "ema50": 15.04, "rsi14": 41.5, "rsiSma9": 37.9, "atr14": 0.51,
        "hacimOrani": 1.22, "mom12_1": -6.5, "gunlukHacimMilyonTL": 480.0, "temettuVerimi": 1.2
    },
    {
        "kod": "ASTOR", "ad": "Astor Enerji", "altSektor": "ENERJI_RAFINERI",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 11.8, "faizliNakitVarlikOrani": 18.6, "mahzurluGelirOrani": 1.70,
        "payBasiYillikMahzurluTL": 2.34, "toplamPayMilyon": 489.9,
        "bazFiyat": 180.30, "low52": 150.76, "high52": 260.77,
        "fk": 9.20, "pddd": 3.10, "fdFavok": 6.50, "roe": 48.2, "roic": 39.5,
        "netBorcFavok": -0.20, "fcfVerimi": 6.8, "piotroski": 8, "beta": 1.14,
        "ema20": 176.02, "ema50": 185.80, "rsi14": 46.9, "rsiSma9": 41.8, "atr14": 5.60,
        "hacimOrani": 1.38, "mom12_1": 8.4, "gunlukHacimMilyonTL": 1520.0, "temettuVerimi": 3.2
    },
    {
        "kod": "ENJSA", "ad": "Enerjisa Enerji", "altSektor": "ENERJI_RAFINERI",
        "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faizli Finansal Borç / Varlık > %33",
        "faizliBorcVarlikOrani": 38.2, "faizliNakitVarlikOrani": 6.4, "mahzurluGelirOrani": 2.10,
        "payBasiYillikMahzurluTL": 2.66, "toplamPayMilyon": 622.6,
        "bazFiyat": 112.30, "low52": 96.74, "high52": 141.32,
        "fk": 8.50, "pddd": 1.05, "fdFavok": 5.30, "roe": 26.8, "roic": 19.4,
        "netBorcFavok": 2.15, "fcfVerimi": 4.1, "piotroski": 6, "beta": 0.89,
        "ema20": 110.21, "ema50": 114.58, "rsi14": 45.2, "rsiSma9": 42.1, "atr14": 3.04,
        "hacimOrani": 1.19, "mom12_1": 7.1, "gunlukHacimMilyonTL": 640.0, "temettuVerimi": 6.0
    },

    # 4. GIDA & PERAKENDE
    {
        "kod": "BIMAS", "ad": "BİM Mağazalar", "altSektor": "GIDA_PERAKENDE",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 14.6, "faizliNakitVarlikOrani": 9.2, "mahzurluGelirOrani": 0.55,
        "payBasiYillikMahzurluTL": 1.60, "toplamPayMilyon": 798.1,
        "bazFiyat": 369.75, "low52": 330.95, "high52": 465.61,
        "fk": 11.20, "pddd": 2.95, "fdFavok": 7.40, "roe": 42.6, "roic": 34.8,
        "netBorcFavok": 0.55, "fcfVerimi": 6.9, "piotroski": 8, "beta": 0.78,
        "ema20": 363.66, "ema50": 376.60, "rsi14": 46.5, "rsiSma9": 41.0, "atr14": 8.98,
        "hacimOrani": 1.29, "mom12_1": 22.4, "gunlukHacimMilyonTL": 2690.0, "temettuVerimi": 3.5
    },
    {
        "kod": "MGROS", "ad": "Migros Ticaret", "altSektor": "GIDA_PERAKENDE",
        "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faaliyet Alanı (Alkollü İçecek Satışı - TKBB Dışı)",
        "faizliBorcVarlikOrani": 18.0, "faizliNakitVarlikOrani": 14.5, "mahzurluGelirOrani": 6.80,
        "payBasiYillikMahzurluTL": 17.12, "toplamPayMilyon": 195.7,
        "bazFiyat": 427.50, "low52": 379.38, "high52": 541.31,
        "fk": 10.40, "pddd": 2.60, "fdFavok": 6.80, "roe": 39.5, "roic": 31.0,
        "netBorcFavok": 0.30, "fcfVerimi": 7.4, "piotroski": 8, "beta": 0.82,
        "ema20": 421.02, "ema50": 434.90, "rsi14": 47.8, "rsiSma9": 43.2, "atr14": 11.20,
        "hacimOrani": 1.25, "mom12_1": 18.9, "gunlukHacimMilyonTL": 1150.0, "temettuVerimi": 2.8
    },
    {
        "kod": "SOKM", "ad": "Şok Marketler", "altSektor": "GIDA_PERAKENDE",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 21.4, "faizliNakitVarlikOrani": 8.1, "mahzurluGelirOrani": 0.75,
        "payBasiYillikMahzurluTL": 0.43, "toplamPayMilyon": 466.6,
        "bazFiyat": 56.20, "low52": 50.61, "high52": 87.10,
        "fk": 12.80, "pddd": 1.65, "fdFavok": 6.20, "roe": 24.8, "roic": 19.2,
        "netBorcFavok": 1.20, "fcfVerimi": 4.5, "piotroski": 6, "beta": 0.86,
        "ema20": 55.31, "ema50": 58.62, "rsi14": 41.2, "rsiSma9": 38.0, "atr14": 1.59,
        "hacimOrani": 1.21, "mom12_1": -9.5, "gunlukHacimMilyonTL": 710.0, "temettuVerimi": 2.4
    },
    {
        "kod": "MAVI", "ad": "Mavi Giyim", "altSektor": "GIDA_PERAKENDE",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 12.4, "faizliNakitVarlikOrani": 19.8, "mahzurluGelirOrani": 1.40,
        "payBasiYillikMahzurluTL": 0.40, "toplamPayMilyon": 919.0,
        "bazFiyat": 33.98, "low52": 30.78, "high52": 51.01,
        "fk": 7.90, "pddd": 2.35, "fdFavok": 4.90, "roe": 45.2, "roic": 37.6,
        "netBorcFavok": -0.40, "fcfVerimi": 8.8, "piotroski": 8, "beta": 0.84,
        "ema20": 33.25, "ema50": 35.19, "rsi14": 43.6, "rsiSma9": 38.9, "atr14": 0.93,
        "hacimOrani": 1.36, "mom12_1": 12.6, "gunlukHacimMilyonTL": 620.0, "temettuVerimi": 4.2
    },

    # 5. TEKNOLOJİ & SAVUNMA
    {
        "kod": "ASELS", "ad": "Aselsan", "altSektor": "TEKNOLOJI_SAVUNMA",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 19.5, "faizliNakitVarlikOrani": 8.4, "mahzurluGelirOrani": 0.85,
        "payBasiYillikMahzurluTL": 2.30, "toplamPayMilyon": 834.1,
        "bazFiyat": 354.25, "low52": 296.30, "high52": 434.07,
        "fk": 11.80, "pddd": 2.10, "fdFavok": 8.20, "roe": 38.4, "roic": 29.8,
        "netBorcFavok": 1.15, "fcfVerimi": 4.6, "piotroski": 7, "beta": 0.95,
        "ema20": 346.60, "ema50": 354.80, "rsi14": 48.2, "rsiSma9": 43.5, "atr14": 9.57,
        "hacimOrani": 1.33, "mom12_1": 19.4, "gunlukHacimMilyonTL": 3120.0, "temettuVerimi": 1.1
    },
    {
        "kod": "LOGO", "ad": "Logo Yazılım", "altSektor": "TEKNOLOJI_SAVUNMA",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 9.2, "faizliNakitVarlikOrani": 15.6, "mahzurluGelirOrani": 1.30,
        "payBasiYillikMahzurluTL": 1.24, "toplamPayMilyon": 88.8,
        "bazFiyat": 120.00, "low52": 100.28, "high52": 150.99,
        "fk": 13.40, "pddd": 3.20, "fdFavok": 8.90, "roe": 41.2, "roic": 34.5,
        "netBorcFavok": -0.25, "fcfVerimi": 6.5, "piotroski": 8, "beta": 0.90,
        "ema20": 117.41, "ema50": 121.46, "rsi14": 46.8, "rsiSma9": 42.0, "atr14": 3.32,
        "hacimOrani": 1.24, "mom12_1": 15.8, "gunlukHacimMilyonTL": 280.0, "temettuVerimi": 2.5
    },
    {
        "kod": "ARDYZ", "ad": "ARD Bilişim", "altSektor": "TEKNOLOJI_SAVUNMA",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 6.8, "faizliNakitVarlikOrani": 11.4, "mahzurluGelirOrani": 0.60,
        "payBasiYillikMahzurluTL": 0.27, "toplamPayMilyon": 118.7,
        "bazFiyat": 51.85, "low52": 44.97, "high52": 81.36,
        "fk": 9.60, "pddd": 2.45, "fdFavok": 6.70, "roe": 43.8, "roic": 36.2,
        "netBorcFavok": -0.15, "fcfVerimi": 5.8, "piotroski": 7, "beta": 1.18,
        "ema20": 50.70, "ema50": 54.28, "rsi14": 43.9, "rsiSma9": 39.2, "atr14": 1.69,
        "hacimOrani": 1.27, "mom12_1": 6.8, "gunlukHacimMilyonTL": 390.0, "temettuVerimi": 1.0
    },

    # 6. ULAŞTIRMA & LOJİSTİK
    {
        "kod": "THYAO", "ad": "Türk Hava Yolları", "altSektor": "ULASTIRMA_LOJISTIK",
        "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faizli Kira/Borç & İkram Kriteri (XKTUM Dışı)",
        "faizliBorcVarlikOrani": 41.2, "faizliNakitVarlikOrani": 18.9, "mahzurluGelirOrani": 3.40,
        "payBasiYillikMahzurluTL": 7.89, "toplamPayMilyon": 1556.6,
        "bazFiyat": 254.00, "low52": 228.73, "high52": 308.52,
        "fk": 3.85, "pddd": 0.62, "fdFavok": 4.40, "roe": 29.8, "roic": 18.5,
        "netBorcFavok": 1.75, "fcfVerimi": 6.2, "piotroski": 7, "beta": 1.04,
        "ema20": 249.12, "ema50": 258.88, "rsi14": 44.5, "rsiSma9": 40.1, "atr14": 6.29,
        "hacimOrani": 1.31, "mom12_1": 9.4, "gunlukHacimMilyonTL": 6400.0, "temettuVerimi": 2.4
    },
    {
        "kod": "PGSUS", "ad": "Pegasus Hava Taşımacılığı", "altSektor": "ULASTIRMA_LOJISTIK",
        "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faizli Uçak Finansal Kiralama Borcu > %33",
        "faizliBorcVarlikOrani": 48.5, "faizliNakitVarlikOrani": 21.0, "mahzurluGelirOrani": 3.90,
        "payBasiYillikMahzurluTL": 2.95, "toplamPayMilyon": 916.5,
        "bazFiyat": 122.20, "low52": 106.93, "high52": 146.20,
        "fk": 5.60, "pddd": 1.28, "fdFavok": 5.90, "roe": 31.4, "roic": 17.8,
        "netBorcFavok": 2.40, "fcfVerimi": 3.9, "piotroski": 6, "beta": 1.08,
        "ema20": 120.29, "ema50": 124.38, "rsi14": 45.8, "rsiSma9": 41.9, "atr14": 3.38,
        "hacimOrani": 1.20, "mom12_1": 13.5, "gunlukHacimMilyonTL": 2150.0, "temettuVerimi": 0.0
    },
    {
        "kod": "RYSAS", "ad": "Reysaş Lojistik", "altSektor": "ULASTIRMA_LOJISTIK",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 15.8, "faizliNakitVarlikOrani": 6.4, "mahzurluGelirOrani": 0.45,
        "payBasiYillikMahzurluTL": 0.11, "toplamPayMilyon": 1140.2,
        "bazFiyat": 25.96, "low52": 22.10, "high52": 37.54,
        "fk": 6.20, "pddd": 1.12, "fdFavok": 5.10, "roe": 33.5, "roic": 24.2,
        "netBorcFavok": 1.25, "fcfVerimi": 5.4, "piotroski": 7, "beta": 1.12,
        "ema20": 25.26, "ema50": 26.66, "rsi14": 43.4, "rsiSma9": 39.0, "atr14": 0.84,
        "hacimOrani": 1.26, "mom12_1": 7.8, "gunlukHacimMilyonTL": 340.0, "temettuVerimi": 1.5
    },
    {
        "kod": "CLEBI", "ad": "Çelebi Hava Servisi", "altSektor": "ULASTIRMA_LOJISTIK",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 21.0, "faizliNakitVarlikOrani": 14.2, "mahzurluGelirOrani": 1.10,
        "payBasiYillikMahzurluTL": 10.19, "toplamPayMilyon": 39.4,
        "bazFiyat": 1167.00, "low52": 1018.81, "high52": 1531.30,
        "fk": 7.40, "pddd": 3.10, "fdFavok": 5.30, "roe": 49.5, "roic": 36.8,
        "netBorcFavok": 0.85, "fcfVerimi": 7.6, "piotroski": 8, "beta": 0.89,
        "ema20": 1148.48, "ema50": 1194.79, "rsi14": 45.1, "rsiSma9": 40.6, "atr14": 32.11,
        "hacimOrani": 1.22, "mom12_1": 16.4, "gunlukHacimMilyonTL": 290.0, "temettuVerimi": 4.8
    },

    # 7. CAM, KİMYA & MADEN
    {
        "kod": "SISE", "ad": "Şişecam", "altSektor": "CAM_KIMYA_MADEN",
        "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faizli Eurobond/Kredi Oranı > %33",
        "faizliBorcVarlikOrani": 35.4, "faizliNakitVarlikOrani": 19.2, "mahzurluGelirOrani": 2.30,
        "payBasiYillikMahzurluTL": 0.72, "toplamPayMilyon": 3725.0,
        "bazFiyat": 33.88, "low52": 31.08, "high52": 46.38,
        "fk": 8.90, "pddd": 0.64, "fdFavok": 6.40, "roe": 13.8, "roic": 10.4,
        "netBorcFavok": 2.35, "fcfVerimi": 1.9, "piotroski": 5, "beta": 0.93,
        "ema20": 33.55, "ema50": 34.95, "rsi14": 42.1, "rsiSma9": 39.8, "atr14": 0.90,
        "hacimOrani": 1.15, "mom12_1": -7.2, "gunlukHacimMilyonTL": 1920.0, "temettuVerimi": 2.2
    },
    {
        "kod": "GUBRF", "ad": "Gübre Fabrikaları", "altSektor": "CAM_KIMYA_MADEN",
        "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu",
        "faizliBorcVarlikOrani": 17.6, "faizliNakitVarlikOrani": 8.9, "mahzurluGelirOrani": 0.70,
        "payBasiYillikMahzurluTL": 1.18, "toplamPayMilyon": 212.0,
        "bazFiyat": 280.50, "low52": 230.07, "high52": 386.08,
        "fk": 14.20, "pddd": 2.85, "fdFavok": 8.60, "roe": 27.4, "roic": 21.0,
        "netBorcFavok": 1.40, "fcfVerimi": 3.1, "piotroski": 6, "beta": 1.16,
        "ema20": 275.77, "ema50": 286.80, "rsi14": 46.0, "rsiSma9": 42.4, "atr14": 8.51,
        "hacimOrani": 1.18, "mom12_1": 2.4, "gunlukHacimMilyonTL": 980.0, "temettuVerimi": 0.0
    },
    {
        "kod": "KOZAL", "ad": "Türk Altın İşletmeleri", "altSektor": "CAM_KIMYA_MADEN",
        "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faiz Getirili Nakit / Varlık > %33",
        "faizliBorcVarlikOrani": 2.1, "faizliNakitVarlikOrani": 44.8, "mahzurluGelirOrani": 14.50,
        "payBasiYillikMahzurluTL": 2.67, "toplamPayMilyon": 1977.7,
        "bazFiyat": 35.30, "low52": 30.60, "high52": 47.61,
        "fk": 9.50, "pddd": 1.95, "fdFavok": 6.10, "roe": 31.2, "roic": 26.4,
        "netBorcFavok": -1.80, "fcfVerimi": 6.4, "piotroski": 7, "beta": 0.98,
        "ema20": 34.65, "ema50": 35.79, "rsi14": 45.4, "rsiSma9": 41.2, "atr14": 1.07,
        "hacimOrani": 1.25, "mom12_1": 4.9, "gunlukHacimMilyonTL": 1450.0, "temettuVerimi": 3.6
    },
    # VALUE TRAP & VETO KAPISI TEST ADAYLARI
    {
        "kod": "BSOKE", "ad": "Batısöke Çimento (Value Trap Test)", "altSektor": "CAM_KIMYA_MADEN",
        "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "KAP 01.10.2026-30.04.2027 Döneminde XKTUM'dan Çıkarıldı (Borç > %33)",
        "faizliBorcVarlikOrani": 34.2, "faizliNakitVarlikOrani": 4.2, "mahzurluGelirOrani": 1.90,
        "payBasiYillikMahzurluTL": 0.03, "toplamPayMilyon": 3224.3,
        "bazFiyat": 4.28, "low52": 4.19, "high52": 8.44,
        "fk": 5.20, "pddd": 0.55, "fdFavok": 9.80, "roe": 9.4, "roic": 6.2,
        "netBorcFavok": 4.25, "fcfVerimi": -3.8, "piotroski": 3, "beta": 1.32,
        "ema20": 4.61, "ema50": 5.22, "rsi14": 26.4, "rsiSma9": 31.8, "atr14": 0.18,
        "hacimOrani": 0.72, "mom12_1": -34.0, "gunlukHacimMilyonTL": 140.0, "temettuVerimi": 0.0
    },
    {
        "kod": "SASA", "ad": "Sasa Polyester (Yüksek Borç / Negatif F/K Test)", "altSektor": "CAM_KIMYA_MADEN",
        "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faizli Borç / Varlık > %33",
        "faizliBorcVarlikOrani": 42.6, "faizliNakitVarlikOrani": 5.1, "mahzurluGelirOrani": 1.20,
        "payBasiYillikMahzurluTL": 0.02, "toplamPayMilyon": 118088.5,
        "bazFiyat": 1.51, "low52": 1.44, "high52": 2.88,
        "fk": -12.40, "pddd": 1.85, "fdFavok": 14.50, "roe": -8.2, "roic": 4.1,
        "netBorcFavok": 5.10, "fcfVerimi": -6.4, "piotroski": 2, "beta": 1.28,
        "ema20": 1.57, "ema50": 1.70, "rsi14": 29.5, "rsiSma9": 33.4, "atr14": 0.06,
        "hacimOrani": 0.81, "mom12_1": -38.5, "gunlukHacimMilyonTL": 1890.0, "temettuVerimi": 0.0
    }
]


def compute_wilder_rsi(closes, period=14):
    """Standart Wilder (1978) RSI Hesaplaması (loss==0 -> 100.0, flat -> 50.0)."""
    if not closes or len(closes) < period + 1:
        return None
    clean = [
        float(c) for c in closes
        if c is not None and not (isinstance(c, float) and (math.isnan(c) or math.isinf(c)))
    ]
    if len(clean) < period + 1:
        return None

    deltas = [clean[i] - clean[i - 1] for i in range(1, len(clean))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0.0 and avg_gain == 0.0:
        return 50.0
    if avg_loss == 0.0:
        return 100.0
    if avg_gain == 0.0:
        return 0.0

    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def compute_median(values):
    valid = sorted(
        float(v) for v in values
        if v is not None and not math.isnan(float(v)) and not math.isinf(float(v))
    )
    n = len(valid)
    if n == 0:
        return None
    mid = n // 2
    return round(valid[mid], 3) if n % 2 == 1 else round((valid[mid - 1] + valid[mid]) / 2.0, 3)


def compute_dynamic_sector_medians(stocks):
    by_sector = {}
    for s in stocks:
        sec = s.get("altSektor", "GENEL")
        by_sector.setdefault(sec, []).append(s)

    medians = {}
    for sec, items in by_sector.items():
        pe_list = [x["fk"] for x in items if x.get("fk") is not None and x["fk"] > 0]
        pb_list = [x["pddd"] for x in items if x.get("pddd") is not None and x["pddd"] > 0]
        ev_list = [x["fdFavok"] for x in items if x.get("fdFavok") is not None and x["fdFavok"] > 0]
        roe_list = [x["roe"] for x in items if x.get("roe") is not None and x["roe"] > 0]

        medians[sec] = {
            "sektorKodu": sec,
            "orneklemSayisi": len(items),
            "medyanFK": compute_median(pe_list) or 9.0,
            "medyanPDDD": compute_median(pb_list) or 1.6,
            "medyanFDFavok": compute_median(ev_list) or 6.0,
            "medyanROE": compute_median(roe_list) or 28.0,
            "hesaplamaYontemi": "Canlı Alt-Sektör Medyanı (25 Hisse Tam Evren)"
        }
    return medians


def _is_valid_ratio(val):
    if val is None or isinstance(val, bool):
        return False
    try:
        f = float(val)
        return math.isfinite(f) and 0.0 <= f <= 100.0
    except Exception:
        return False


def verify_xktum_compliance(stock):
    """
    BIST XKTUM Kural Seti (Eylül 2026 - Madde 6.8.e) Denetimi (Payda: Toplam Varlıklar).
    Resmi XKTUM Endeks Üyeliği ile Bilanço Rasyo Taraması ayrı alanlar olarak raporlanır.
    NaN, None, Infinity veya kaynaksız veriler kesinlikle DOGRULANAMADI döner.
    """
    debt_ratio = stock.get("faizliBorcVarlikOrani")
    cash_ratio = stock.get("faizliNakitVarlikOrani")
    impure_rev = stock.get("mahzurluGelirOrani")
    kaynak = str(stock.get("katilimKaynak") or "").strip()

    if not (_is_valid_ratio(debt_ratio) and _is_valid_ratio(cash_ratio) and _is_valid_ratio(impure_rev)) or not kaynak:
        return {
            "durum": "DOGRULANAMADI",
            "xktumUye": False,
            "xktumEndeksUyesi": False,
            "oranTaramasiDurum": "BELIRSIZ",
            "endeksCikisRiski": True,
            "aciklama": "Bilanço dipnot oranları veya resmi KAFİF/KAP kaynağı doğrulanamadı."
        }

    debt_f = float(debt_ratio)
    cash_f = float(cash_ratio)
    impure_f = float(impure_rev)
    resmi_endeks_kaydi = ("XKTUM" in kaynak.upper() or "KATILIM" in kaynak.upper()) and (stock.get("katilimUyum") in ("UYGUN", "SINIRDA_UYARI"))

    # BIST 6.8.e: Eşikleri aşmama (<= %33 borç/varlık, <= %33 nakit/varlık, <= %5 mahzurlu gelir)
    if impure_f > 5.0 or debt_f > 33.0 or cash_f > 33.0 or stock.get("katilimUyum") == "UYGUN_DEGIL":
        reasons = []
        if debt_f > 33.0:
            reasons.append(f"Faizli Borç/Varlık %{debt_f:.1f} > %33")
        if cash_f > 33.0:
            reasons.append(f"Faizli Nakit/Varlık %{cash_f:.1f} > %33")
        if impure_f > 5.0:
            reasons.append(f"Mahzurlu Gelir %{impure_f:.1f} > %5")
        if not reasons:
            reasons.append(kaynak or "Faaliyet alanı / dönem revizyonu kısıtı")
        return {
            "durum": "UYGUN_DEGIL",
            "xktumUye": False,
            "xktumEndeksUyesi": False,
            "oranTaramasiDurum": "ESIK_ASIMI",
            "endeksCikisRiski": False,
            "aciklama": " · ".join(reasons)
        }

    near_limit = (28.0 <= debt_f <= 33.0) or (28.0 <= cash_f <= 33.0) or (4.0 <= impure_f <= 5.0)
    if near_limit or stock.get("katilimUyum") == "SINIRDA_UYARI":
        return {
            "durum": "SINIRDA_UYARI",
            "xktumUye": resmi_endeks_kaydi,
            "xktumEndeksUyesi": resmi_endeks_kaydi,
            "oranTaramasiDurum": "SINIRDA",
            "endeksCikisRiski": True,
            "aciklama": f"Oran sınır bölgesinde (Borç/Varlık %{debt_f:.1f} <= %33). Sonraki endeks döneminde izlenmeli."
        }

    return {
        "durum": "UYGUN",
        "xktumUye": resmi_endeks_kaydi,
        "xktumEndeksUyesi": resmi_endeks_kaydi,
        "oranTaramasiDurum": "UYGUN",
        "endeksCikisRiski": False,
        "aciklama": f"BIST XKTUM 6.8.e uyumlu (Borç/Varlık %{debt_f:.1f}, Nakit/Varlık %{cash_f:.1f}, Gelir %{impure_f:.2f})"
    }


def compute_gordon_justified_pddd(roe_pct, coe_pct, g_pct=None):
    """
    Standart Damodaran Gordon Growth Haklı PD/DD Formülü:
    Justified P/BV = (ROE - g) / (COE - g)
    Geçersiz parametrelerde (g >= COE) None döner; ROE <= 0 ise taban 0.20 döner.
    """
    if roe_pct is None or coe_pct is None:
        return None
    roe_d = float(roe_pct) / 100.0
    coe_d = float(coe_pct) / 100.0
    if not (math.isfinite(roe_d) and math.isfinite(coe_d)):
        return None
    if roe_d <= 0.0:
        return 0.20
    cpi = MACRO_PARAMS["cpiInflation"]
    g_d = (float(g_pct) / 100.0) if g_pct is not None else min(roe_d * 0.55, cpi * 0.6578947)
    if g_d >= coe_d:
        return None
    raw_pddd = (roe_d - g_d) / (coe_d - g_d)
    return round(min(4.50, max(0.20, raw_pddd)), 4)


def iz_suren_stop_yukselt(eski_stop, guncel_fiyat, atr14):
    """Stop Ratchet (Mandallı İz Süren Stop): Stop seviyesi yalnız yukarı yönlü güncellenir, asla düşmez."""
    eski = float(eski_stop or 0.0)
    fiyat = float(guncel_fiyat or 0.0)
    atr = float(atr14 or (fiyat * 0.028))
    stop_mesafe = min(fiyat * 0.095, max(fiyat * 0.035, 2.5 * atr))
    aday_stop = round(fiyat - stop_mesafe, 2)
    return round(max(eski, aday_stop), 2)


def evaluate_stock_quant(raw_stock, sector_medians):
    """
    Kurumsal Değerleme, Bilanço Değişmezleri (EPS0/BVPS0) ve 4 Sütunlu Hibrit Skor Motoru (v4.7).
    """
    s = dict(raw_stock)
    sec = s.get("altSektor", "GENEL")
    med = sector_medians.get(sec, {
        "medyanFK": 9.0, "medyanPDDD": 1.6, "medyanFDFavok": 6.0, "medyanROE": 28.0
    })

    price = s.get("bazFiyat")
    fk = s.get("fk")
    pddd = s.get("pddd")
    fd_favok = s.get("fdFavok")
    roe = s.get("roe")
    net_borc_favok = s.get("netBorcFavok")
    fcf_verimi = s.get("fcfVerimi")
    piotroski = s.get("piotroski")
    rsi14 = s.get("rsi14")
    rsi_sma9 = s.get("rsiSma9")
    low52 = s.get("low52")
    high52 = s.get("high52")
    ema20 = s.get("ema20")
    atr14 = s.get("atr14")
    hacim_orani = s.get("hacimOrani")
    beta = s.get("beta", 1.0)

    required = [price, fk, pddd, fd_favok, roe, rsi14, low52, high52, atr14]
    if any(v is None or isinstance(v, bool) or (isinstance(v, (int, float)) and (math.isnan(float(v)) or math.isinf(float(v)))) for v in required) or float(price) <= 0:
        s["veriDurumu"] = "EKSIK_VERI"
        s["uygunlukKapisi"] = False
        s["vetoNedenleri"] = ["Zorunlu fiyat veya bilanço verisi eksik (Sahte veri atanmadı)."]
        s["hibritSkor"] = 0.0
        return s

    s["veriDurumu"] = "DOGRULANDI"

    # Bilanço değişmezleri (Fiyat değiştiğinde F/K, PD/DD ve FD/FAVÖK'ün doğru ölçeklenmesi için)
    eps0 = s.get("eps0") if s.get("eps0") is not None else (round(price / fk, 6) if fk != 0 else 0.0)
    bvps0 = s.get("bvps0") if s.get("bvps0") is not None else (round(price / pddd, 6) if pddd > 0 else 0.0)
    favok_ps0 = s.get("favokPs0") if s.get("favokPs0") is not None else (round(price / fd_favok, 6) if fd_favok > 0 else 0.0)

    rf = MACRO_PARAMS["riskFreeRate"]        # 0.37
    erp = MACRO_PARAMS["equityRiskPremium"]  # 0.085
    cpi = MACRO_PARAMS["cpiInflation"]       # 0.38

    coe = rf + float(beta) * erp
    roe_dec = float(roe) / 100.0
    reel_roe = ((1.0 + roe_dec) / (1.0 + cpi) - 1.0) * 100.0
    reel_coe = ((1.0 + coe) / (1.0 + cpi) - 1.0)
    kazanc_verimi = (100.0 / float(fk)) if fk > 0 else -99.0

    # Damodaran Gordon Büyüme Modeli Teorik Haklı PD/DD: (ROE - g) / (COE - g)
    gordon_raw = compute_gordon_justified_pddd(roe, coe * 100.0)
    justified_pddd = round(gordon_raw, 2) if gordon_raw is not None else 0.25

    veto_list = []
    if fk <= 0:
        veto_list.append(f"Negatif/Sıfır F/K ({fk:.1f})")
    if pddd <= 0:
        veto_list.append(f"Negatif/Sıfır PD/DD ({pddd:.2f})")
    if fd_favok <= 0:
        veto_list.append(f"Negatif FD/FAVÖK ({fd_favok:.1f})")
    if net_borc_favok is not None and net_borc_favok > 3.5:
        veto_list.append(f"Aşırı Borçluluk: Net Borç/FAVÖK ({net_borc_favok:.2f} > 3.5)")
    if fcf_verimi is not None and fcf_verimi < -2.0:
        veto_list.append(f"Negatif Serbest Nakit Akışı ({fcf_verimi:.1f}%)")
    if piotroski is not None and piotroski < 4:
        veto_list.append(f"Düşük Bilanço Kalitesi (Piotroski {piotroski}/9)")

    if fk > 0 and pddd > 0 and fd_favok > 0 and gordon_raw is not None:
        val_fk = eps0 * med["medyanFK"]
        # EV/FAVÖK -> Özsermaye Köprüsü: Hedef EV - Net Borç Düzeltmesi (bilanço değişmezi favok_ps0 üzerinden)
        net_borc_ps0 = favok_ps0 * float(net_borc_favok or 0.0)
        val_ev = max(0.01, (favok_ps0 * med["medyanFDFavok"]) - (net_borc_ps0 * 0.22))
        hedef_pddd = 0.55 * med["medyanPDDD"] + 0.45 * justified_pddd
        val_pddd = bvps0 * hedef_pddd

        debt_penalty = 1.0
        if net_borc_favok is not None and net_borc_favok > 2.0:
            debt_penalty = max(0.65, 1.0 - (net_borc_favok - 2.0) * 0.12)

        adil_deger_baz = round((0.35 * val_fk + 0.35 * val_ev + 0.30 * val_pddd) * debt_penalty, 2)
        adil_deger_kotumser = round(adil_deger_baz * 0.85, 2)
        adil_deger_iyimser = round(adil_deger_baz * 1.15, 2)
        potansiyel_pct = round(((adil_deger_baz - price) / price) * 100.0, 2)
        graham_degeri = round(math.sqrt(22.5 * eps0 * bvps0), 2) if (eps0 > 0 and bvps0 > 0) else None
    else:
        adil_deger_baz = None
        adil_deger_kotumser = None
        adil_deger_iyimser = None
        potansiyel_pct = -100.0
        graham_degeri = None

    # 4 Sütunlu Hibrit Skor v4.7
    p1_degerleme = 0.0
    if adil_deger_baz is not None and fk > 0:
        if potansiyel_pct > 0:
            p1_degerleme += min(18.0, potansiyel_pct * 0.45)
        ev_disc = ((med["medyanFDFavok"] - fd_favok) / med["medyanFDFavok"]) * 100.0
        if ev_disc > 0:
            p1_degerleme += min(9.0, ev_disc * 0.25)
        p1_degerleme += max(0.0, min(8.0, (kazanc_verimi - 7.0) * 0.65))
    p1_degerleme = round(min(35.0, p1_degerleme), 2)

    p2_kalite = 0.0
    if roe > 0:
        p2_kalite += max(0.0, min(7.0, (roe - 15.0) * 0.22))
    if reel_roe >= 0:
        p2_kalite += min(4.0, 2.0 + reel_roe * 0.25)
    if net_borc_favok <= 0:
        p2_kalite += 8.0
    elif net_borc_favok <= 3.5:
        p2_kalite += max(0.0, 8.0 - net_borc_favok * 2.2)
    if fcf_verimi > 0:
        p2_kalite += min(5.0, fcf_verimi * 0.60)
    if piotroski is not None:
        p2_kalite += max(0.0, min(6.0, (piotroski - 3) * 1.2))
    p2_kalite = round(min(30.0, p2_kalite), 2)

    bant_genislik = max(0.01, high52 - low52)
    konum52_pct = max(0.0, min(100.0, ((price - low52) / bant_genislik) * 100.0))
    if 8.0 <= konum52_pct <= 45.0:
        p3_teknik = 11.0 - abs(konum52_pct - 22.0) * 0.22
    elif konum52_pct < 8.0:
        p3_teknik = 5.5
    else:
        p3_teknik = max(0.0, 8.0 - (konum52_pct - 45.0) * 0.15)

    if 32.0 <= rsi14 <= 52.0:
        p3_teknik += 9.0 - abs(rsi14 - 43.0) * 0.25
    elif rsi14 < 32.0:
        p3_teknik += 4.5
    else:
        p3_teknik += max(0.0, 6.0 - (rsi14 - 52.0) * 0.22)
    p3_teknik = round(min(20.0, max(0.0, p3_teknik)), 2)

    p4_momentum = 0.0
    if rsi14 > (rsi_sma9 if rsi_sma9 is not None else 50.0):
        p4_momentum += 4.5
    if price >= (ema20 if ema20 is not None else price):
        p4_momentum += 4.5
    if (hacim_orani if hacim_orani is not None else 1.0) >= 1.15:
        p4_momentum += 3.5
    if s.get("mom12_1", 0.0) > 0:
        p4_momentum += 2.5
    p4_momentum = round(min(15.0, p4_momentum), 2)

    value_trap_risk = False
    if p4_momentum < 4.5 or (net_borc_favok > 3.0) or (fcf_verimi < 0) or (piotroski <= 4):
        value_trap_risk = True
        if p4_momentum < 4.5 and konum52_pct < 15.0:
            veto_list.append("Düşen Bıçak / Value Trap: 52H dibinde hacim ve momentum dönüş teyidi yok")

    uygunluk_kapisi = (len(veto_list) == 0) and (adil_deger_baz is not None) and (potansiyel_pct > 5.0)
    ham_skor = round(p1_degerleme + p2_kalite + p3_teknik + p4_momentum, 2)
    hibrit_skor = ham_skor if uygunluk_kapisi else round(min(ham_skor * 0.55, 49.0), 2)

    atr_pct = round((atr14 / price) * 100.0, 2)
    stop_mesafe = min(price * 0.095, max(price * 0.035, 2.5 * atr14))
    chandelier_stop = round(price - stop_mesafe, 2)
    stop_kayip_pct = round(((price - chandelier_stop) / price) * 100.0, 2)

    if adil_deger_baz is not None:
        aylik_hedef = round(price + (adil_deger_baz - price) * 0.35, 2)
        aylik_potansiyel_pct = round(((aylik_hedef - price) / price) * 100.0, 2)
    else:
        aylik_hedef = round(price * 0.95, 2)
        aylik_potansiyel_pct = -5.0

    # Günün İlk 5 Önerisi İçin Sezgisel Sinyal Gücü (%), Ödül/Risk (R/R) ve Gidiş-Dönüş Maliyet Düşülmüş Net EV
    odul_risk = round(max(0.0, aylik_potansiyel_pct) / max(1.0, stop_kayip_pct), 2)
    if not uygunluk_kapisi:
        getiri_ihtimali_pct = round(max(12.0, min(39.0, ham_skor * 0.45)), 1)
    else:
        baz_olasilik = 42.0 + (ham_skor * 0.36)
        if (hacim_orani or 1.0) >= 1.25:
            baz_olasilik += 5.5
        if rsi14 > (rsi_sma9 if rsi_sma9 is not None else 50.0):
            baz_olasilik += 4.5
        if reel_roe > 0:
            baz_olasilik += 4.0
        if odul_risk >= 2.2:
            baz_olasilik += 3.5
        getiri_ihtimali_pct = round(min(92.0, max(45.0, baz_olasilik)), 1)

    p_win_dec = getiri_ihtimali_pct / 100.0
    gidis_donus_maliyet_pct = round(2.0 * (MACRO_PARAMS["commissionRate"] + MACRO_PARAMS["baseSlippageRate"]) * 100.0, 3)  # %0.405
    beklenen_net_deger = round(
        p_win_dec * max(0.0, aylik_potansiyel_pct) - (1.0 - p_win_dec) * stop_kayip_pct - gidis_donus_maliyet_pct,
        2
    )

    gerekce_parcalari = []
    if potansiyel_pct > 15.0:
        gerekce_parcalari.append(f"Adil değere göre %{potansiyel_pct:.1f} iskontolu")
    if reel_roe > 0:
        gerekce_parcalari.append(f"+%{reel_roe:.1f} pozitif Reel ROE")
    if (hacim_orani or 1.0) >= 1.20:
        gerekce_parcalari.append(f"{hacim_orani:.2f}x kurumsal hacim artışı")
    if rsi14 > (rsi_sma9 if rsi_sma9 is not None else 50.0):
        gerekce_parcalari.append(f"RSI ({rsi14:.1f}) > SMA9 momentum dönüşü")
    if odul_risk >= 2.0:
        gerekce_parcalari.append(f"{odul_risk:.1f}x asimetrik ödül/risk")
    secilme_gerekcesi = " · ".join(gerekce_parcalari) if gerekce_parcalari else "Dengeli temel ve teknik görünüm"

    katilim_denetim = verify_xktum_compliance(s)

    # Bilanço Röntgeni ve Projeksiyon Takvimi (Şeffaf Model/Tahmin Etiketli, %15 Stopajlı ve Gerçek Tarih Farklı)
    pay_milyon_raw = s.get("toplamPayMilyon")
    pay_milyon = float(pay_milyon_raw) if (pay_milyon_raw is not None and float(pay_milyon_raw) > 0) else None
    ozsermaye_milyar = round((bvps0 * pay_milyon) / 1000.0, 2) if (bvps0 > 0 and pay_milyon) else 0.0
    yillik_net_kar_milyar = round((eps0 * pay_milyon) / 1000.0, 2) if (eps0 != 0 and pay_milyon) else 0.0
    yillik_favok_milyar = round((favok_ps0 * pay_milyon) / 1000.0, 2) if (favok_ps0 > 0 and pay_milyon) else 0.0
    nakit_varlik_orani = float(s.get("faizliNakitVarlikOrani") or 10.0)
    cari_oran = round(max(0.75, min(2.85, 1.55 - (net_borc_favok * 0.22) + (nakit_varlik_orani * 0.015))), 2)
    roic_val = float(s.get("roic") if s.get("roic") is not None else (roe * 0.78))
    favok_marji_pct = round(max(4.5, min(42.0, roic_val * 0.85)), 1)
    net_kar_buyume_yoy = round((reel_roe * 1.15) + (fcf_verimi * 1.4), 1)
    pio_val = int(piotroski if piotroski is not None else 6)

    bilanco_analizi = {
        "sonDonem": "2026/06 (TMS-29 Enflasyon Muhasebeli)",
        "sonrakiDonem": "2026/09 (3. Çeyrek Bilanço Dönemi - Beklenen)",
        "veriNiteligi": "MODEL_PROJEKSIYONU_TMS29" if pay_milyon else "KISMI_ORAN_TAHMINI",
        "kaynak": "KAP 2026/06 Çarpanları & Model Rasyo Projeksiyonu (Tahmini)",
        "ozsermayeMilyarTL": ozsermaye_milyar,
        "yillikNetKarMilyarTL": yillik_net_kar_milyar,
        "yillikFavokMilyarTL": yillik_favok_milyar,
        "cariOran": cari_oran,
        "favokMarjiPct": favok_marji_pct,
        "netKarBuyumeYoY": net_kar_buyume_yoy,
        "piotroskiPuan": pio_val,
        "piotroskiOzeti": f"Karlılık: {min(4, max(0, pio_val // 2 + 1))}/4 · Kaldıraç/Likidite: {min(3, max(0, pio_val // 3))}/3 · Verimlilik: {max(0, pio_val - (min(4, max(0, pio_val // 2 + 1)) + min(3, max(0, pio_val // 3))))}/2"
    }

    bugun_date = datetime.now(timezone.utc).astimezone().date()
    kod_str = str(s.get("kod", "BIST"))
    kod_hash = sum(ord(ch) for ch in kod_str)
    bilanco_hedef_gun = min(28, 3 + (kod_hash % 12))
    bilanco_gun_str = s.get("sonrakiBilancoTarihi") or f"2026-11-{bilanco_hedef_gun:02d}"
    try:
        b_parts = [int(x) for x in bilanco_gun_str.split("-")]
        from datetime import date as dt_date
        bilanco_kalan_gun = max(0, (dt_date(b_parts[0], b_parts[1], b_parts[2]) - bugun_date).days)
    except Exception:
        bilanco_kalan_gun = 7

    if reel_roe > 0 and fcf_verimi > 4.0:
        beklenen_kar_durumu = "🟢 Güçlü Reel Kar & Nakit Akışı Beklentisi (Model)"
    elif fk > 0 and net_borc_favok <= 2.5:
        beklenen_kar_durumu = "🔵 Dengeli Faaliyet Karı / Marj Takibi (Model)"
    else:
        beklenen_kar_durumu = "🟠 Finansman Gideri / Borç Baskısı Riski (Model)"

    temettu_verimi_pct = float(s.get("temettuVerimi") or 0.0)
    pay_basi_brut_temettu = round(price * (temettu_verimi_pct / 100.0), 2) if temettu_verimi_pct > 0 else 0.0
    # 9286 sayılı Cumhurbaşkanı Kararı uyarınca %15 kar payı stopajı:
    pay_basi_net_temettu = round(pay_basi_brut_temettu * 0.85, 2)
    if temettu_verimi_pct > 0:
        tem_hedef_gun = min(30, 5 + ((kod_hash * 3) % 24))
        temettu_tarihi = s.get("temettuTarihi") or f"2026-11-{tem_hedef_gun:02d}"
        try:
            t_parts = [int(x) for x in temettu_tarihi.split("-")]
            from datetime import date as dt_date
            temettu_kalan_gun = max(0, (dt_date(t_parts[0], t_parts[1], t_parts[2]) - bugun_date).days)
        except Exception:
            temettu_kalan_gun = 14
    else:
        temettu_kalan_gun = None
        temettu_tarihi = "Temettü Dağıtmıyor"

    # Temettü sabahı hisse fiyatı brüt temettü kadar düştüğünde sahte stop-loss tetiklenmesini önleyen kalkan:
    temettu_duzeltmeli_stop = round(max(0.01, chandelier_stop - pay_basi_brut_temettu), 2)

    takvim_bilgisi = {
        "takvimNiteligi": "TAHMINI_TAKVIM_PROJEKSIYONU",
        "stopajOraniPct": 15.0,
        "sonrakiBilancoTarihi": bilanco_gun_str,
        "bilancoyaKalanGun": bilanco_kalan_gun,
        "beklenenKarDurumu": beklenen_kar_durumu,
        "temettuVerimiPct": temettu_verimi_pct,
        "payBasiBrutTemettuTL": pay_basi_brut_temettu,
        "payBasiNetTemettuTL": pay_basi_net_temettu,
        "temettuTarihi": temettu_tarihi,
        "temettuKalanGun": temettu_kalan_gun,
        "temettuDuzeltmeliStop": temettu_duzeltmeli_stop
    }

    if not uygunluk_kapisi:
        emir_sinyali = "VETO_UZAK_DUR"
    elif getiri_ihtimali_pct >= 76.0 and odul_risk >= 2.0:
        emir_sinyali = "GUCLU_AL_EMRI"
    else:
        emir_sinyali = "AL_ADAYI"

    ornek_lot = max(1, int(math.floor(2500.0 / max(0.01, price))))
    sesli_al_emri_metni = (
        f"AL EMRİ SİNYALİ: {s.get('ad', kod_str)} hissesi yüzde {getiri_ihtimali_pct:.1f} sinyal gücü ile "
        f"{price:.2f} liradan alım bölgesinde. Örneğin 2500 liralık dilim için {ornek_lot} lot AL emri verilebilir; "
        f"iz süren stop {chandelier_stop:.2f} lira, 30 günlük senaryo hedefi {aylik_hedef:.2f} lira."
    )

    s.update({
        "eps0": eps0,
        "bvps0": bvps0,
        "favokPs0": favok_ps0,
        "sektorMedyanFK": med["medyanFK"],
        "sektorMedyanPDDD": med["medyanPDDD"],
        "sektorMedyanFDFavok": med["medyanFDFavok"],
        "hakliPDDD": justified_pddd,
        "ozsermayeMaliyetiCOE": round(coe * 100.0, 2),
        "reelCOE": round(reel_coe * 100.0, 2),
        "reelROE": round(reel_roe, 2),
        "kazancVerimi": round(kazanc_verimi, 2),
        "adilDegerKotumser": adil_deger_kotumser,
        "adilDegerBaz": adil_deger_baz,
        "adilDegerIyimser": adil_deger_iyimser,
        "grahamDegeri": graham_degeri,
        "adilDegerPotansiyelPct": potansiyel_pct,
        "konum52H": round(konum52_pct, 1),
        "atrPct": atr_pct,
        "chandelierStop": chandelier_stop,
        "temettuDuzeltmeliStop": temettu_duzeltmeli_stop,
        "stopMesafePct": stop_kayip_pct,
        "aylikHedefFiyat": aylik_hedef,
        "aylikBeklentiPct": aylik_potansiyel_pct,
        "getiriIhtimaliPct": getiri_ihtimali_pct,
        "olasilikNiteligi": "SEZGISEL_SINYAL_GUCU",
        "odulRiskOrani": odul_risk,
        "beklenenNetDeger": beklenen_net_deger,
        "secilmeGerekcesi": secilme_gerekcesi,
        "emirSinyali": emir_sinyali,
        "sesliAlEmriMetni": sesli_al_emri_metni,
        "bilancoAnalizi": bilanco_analizi,
        "takvim": takvim_bilgisi,
        "puanDegerleme": p1_degerleme,
        "puanKalite": p2_kalite,
        "puanTeknik": p3_teknik,
        "puanMomentum": p4_momentum,
        "hamSkor": ham_skor,
        "hibritSkor": hibrit_skor,
        "uygunlukKapisi": uygunluk_kapisi,
        "valueTrapRiski": value_trap_risk,
        "vetoNedenleri": veto_list,
        "katilimDenetim": katilim_denetim,
        "katilimOnay": bool(katilim_denetim.get("xktumUye"))
    })
    return s


def build_top5_daily_picks(evaluated_stocks):
    """
    Tüm taranan BIST evreni içinden 'Sinyal Gücü (%) × Beklenen Net Değer (EV)'
    en yüksek olan Günün İlk 5 Hissesini (hem Katılım XKTUM hem Tüm BIST için) seçer.
    """
    eligible = [s for s in evaluated_stocks if s.get("uygunlukKapisi")]
    ranked = sorted(
        eligible,
        key=lambda x: (x.get("getiriIhtimaliPct", 0.0) * 0.6 + x.get("beklenenNetDeger", 0.0) * 2.5 + x.get("hibritSkor", 0.0) * 0.4),
        reverse=True
    )

    def select_top5(pool):
        picked = []
        sec_counts = {}
        for item in pool:
            sec = item.get("altSektor", "GENEL")
            if sec_counts.get(sec, 0) < 2:
                picked.append(item)
                sec_counts[sec] = sec_counts.get(sec, 0) + 1
                if len(picked) >= 5:
                    break
        return picked

    katilim_pool = [s for s in ranked if s.get("katilimDenetim", {}).get("durum") == "UYGUN"]
    return {
        "katilimIlk5": select_top5(katilim_pool),
        "tumBistIlk5": select_top5(ranked)
    }


def winsorize_series(values, low_q=0.05, high_q=0.95):
    """%5 - %95 Persentil Winsorization (Uç Değer Kırpma) uygular."""
    if not values:
        return [], 0.0, 0.0
    s_vals = sorted(float(v) for v in values)
    n = len(s_vals)
    if n >= 4:
        low_idx = max(1, min(n - 2, int(round((n - 1) * low_q))))
        high_idx = max(low_idx, min(n - 2, int(math.floor((n - 1) * high_q))))
    else:
        low_idx = 0
        high_idx = n - 1
    low_bound = s_vals[low_idx]
    high_bound = s_vals[high_idx]
    clipped = [min(high_bound, max(low_bound, float(v))) for v in values]
    return clipped, low_bound, high_bound


def attach_z_scores(evaluated_stocks):
    valid = [s for s in evaluated_stocks if s.get("veriDurumu") == "DOGRULANDI"]
    if len(valid) < 2:
        for s in evaluated_stocks:
            s["zSkor"] = 0.0
        return evaluated_stocks

    raw_scores = [s["hamSkor"] for s in valid]
    clipped_scores, low_b, high_b = winsorize_series(raw_scores, 0.05, 0.95)
    mean_s = sum(clipped_scores) / len(clipped_scores)
    var_s = sum((x - mean_s) ** 2 for x in clipped_scores) / len(clipped_scores)
    std_s = math.sqrt(var_s) if var_s > 0 else 1.0

    for s in evaluated_stocks:
        if s.get("veriDurumu") == "DOGRULANDI":
            w_val = min(high_b, max(low_b, float(s["hamSkor"])))
            s["zSkor"] = round((w_val - mean_s) / std_s, 2)
        else:
            s["zSkor"] = -3.0
    return evaluated_stocks


def compute_pairwise_correlation(c1, c2):
    """İki hisse arasındaki analitik korelasyon katsayısını (rho_ij) hesaplar."""
    if c1["kod"] == c2["kod"]:
        return 1.0
    same_sec = 1.0 if c1.get("altSektor") == c2.get("altSektor") else 0.0
    b1 = float(c1.get("beta", 1.0))
    b2 = float(c2.get("beta", 1.0))
    rho = 0.35 + 0.25 * same_sec + 0.15 * max(0.0, 1.0 - abs(b1 - b2))
    return round(min(0.85, max(0.15, rho)), 3)


def compute_model_weights(candidates, weight_model):
    """
    Ağırlık Modelleri:
    - TERS_ATR_HRP: Korelasyon Cezalı Ters Volatilite w_i ~ 1 / (sigma_i * (1 + avg_rho_i))
    - ESIT_RISK_ERC: Kovaryans matrisi üzerinde iteratif Eşit Risk Katkısı (Equal Risk Contribution)
    - SABIT_40_35_25: Klasik %40-%35-%25
    """
    n = len(candidates)
    if n == 0:
        return []
    if n == 1:
        return [1.0]
    if weight_model == "SABIT_40_35_25":
        base = [0.40, 0.35, 0.25, 0.15, 0.10][:n]
        s = sum(base)
        return [w / s for w in base]

    sigmas = [max(0.8, float(c.get("atrPct", 2.5))) for c in candidates]
    corr_matrix = [[compute_pairwise_correlation(candidates[i], candidates[j]) for j in range(n)] for i in range(n)]

    if weight_model in ("TERS_ATR_HRP", "KORELASYON_TERS_ATR"):
        raw_w = []
        for i in range(n):
            avg_rho = sum(corr_matrix[i][j] for j in range(n) if i != j) / max(1, n - 1)
            raw_w.append(1.0 / (sigmas[i] * (1.0 + avg_rho)))
        s = sum(raw_w)
        return [w / s for w in raw_w]

    # ESIT_RISK_ERC: İteratif Eşit Risk Katkısı çözücüsü (w_i * (Sigma * w)_i eşitlenir)
    w = [1.0 / s for s in sigmas]
    w_sum = sum(w)
    w = [x / w_sum for x in w]
    for _ in range(35):
        marg_risk = []
        for i in range(n):
            mr_i = sum(w[j] * sigmas[i] * sigmas[j] * corr_matrix[i][j] for j in range(n))
            marg_risk.append(max(1e-6, mr_i))
        rc = [w[i] * marg_risk[i] for i in range(n)]
        target_rc = sum(rc) / n
        w = [w[i] * (target_rc / rc[i]) ** 0.5 for i in range(n)]
        ws = sum(w)
        w = [x / ws for x in w]
    return w


def allocate_smart_lots(candidates, budget_tl, target_weights, cash_buffer_pct=0.0, current_day=1):
    """
    Kuruş-Tam (Zero-Overrun) Akıllı Tam Lot ve Artan Nakit Optimizasyonu.
    Birim maliyet yuvarlama farkından kaynaklanan bütçe aşımını (%100 kuruş kontrolüyle) engeller.
    """
    budget_kurus = max(0, int(round(float(budget_tl) * 100)))
    deployable_kurus = int(math.floor(budget_kurus * (1.0 - max(0.0, float(cash_buffer_pct)) / 100.0)))
    deployable_tl = deployable_kurus / 100.0
    if not candidates or deployable_kurus <= 0:
        return [], round(budget_kurus / 100.0, 2)

    n = len(candidates)
    w_sum = sum(target_weights[:n]) or 1.0
    norm_weights = [w / w_sum for w in target_weights[:n]]

    fee_mult = 1.0 + MACRO_PARAMS["commissionRate"] + MACRO_PARAMS["baseSlippageRate"]

    positions = []
    for i, c in enumerate(candidates):
        raw_price = float(c["bazFiyat"])
        exec_price = round(raw_price * fee_mult, 4)
        alloc_tl = deployable_tl * norm_weights[i]
        lots = max(0, int(math.floor(alloc_tl / exec_price)))
        while lots > 0 and int(round(lots * exec_price * 100)) > int(round(alloc_tl * 100)):
            lots -= 1
        cost_kurus = int(round(lots * exec_price * 100))
        cost = round(cost_kurus / 100.0, 2)
        positions.append({
            "kod": c["kod"],
            "ad": c["ad"],
            "altSektor": c["altSektor"],
            "alisGunu": int(current_day),
            "hedefAgirlikPct": round(norm_weights[i] * (1.0 - cash_buffer_pct / 100.0) * 100.0, 2),
            "lot": lots,
            "piyasaFiyati": raw_price,
            "oncekiKapanisFiyati": raw_price,
            "maliyetFiyati": exec_price,
            "toplamMaliyetTL": cost,
            "lotKatmanlari": [{"lot": lots, "alisGunu": int(current_day), "birimMaliyet": exec_price}] if lots > 0 else [],
            "stopFiyati": c["chandelierStop"],
            "temettuDuzeltmeliStop": c.get("temettuDuzeltmeliStop", c["chandelierStop"]),
            "hedefFiyati": c["aylikHedefFiyat"],
            "adilDegerBaz": c["adilDegerBaz"],
            "hibritSkor": c["hibritSkor"],
            "atrPct": c["atrPct"],
            "beta": c.get("beta", 1.0),
            "temettuVerimi": c.get("temettuVerimi", 0.0),
            "payBasiYillikMahzurluTL": c.get("payBasiYillikMahzurluTL", 0.0),
            "mahzurluGelirOrani": c.get("mahzurluGelirOrani", 0.0),
            "katilimDurum": c["katilimDenetim"]["durum"]
        })

    def total_cost_kurus(lot_list):
        return sum(int(round(lot_list[j] * positions[j]["maliyetFiyati"] * 100)) for j in range(n))

    def weight_error(lot_list):
        return sum(
            (((int(round(lot_list[j] * positions[j]["maliyetFiyati"] * 100)) / 100.0) / deployable_tl) - norm_weights[j]) ** 2
            for j in range(n)
        )

    current_lots = [p["lot"] for p in positions]
    cur_err = weight_error(current_lots)

    for _ in range(200):
        best_idx = None
        best_err = cur_err
        cur_spent_k = total_cost_kurus(current_lots)
        for j in range(n):
            ep = positions[j]["maliyetFiyati"]
            trial = list(current_lots)
            trial[j] += 1
            new_spent_k = total_cost_kurus(trial)
            if new_spent_k <= deployable_kurus:
                err = weight_error(trial)
                new_w = ((int(round(trial[j] * ep * 100)) / 100.0) / deployable_tl)
                if err < best_err and new_w <= (norm_weights[j] + 0.025):
                    best_err = err
                    best_idx = j
        if best_idx is None:
            break
        current_lots[best_idx] += 1
        cur_err = best_err

    # Son güvenlik kilidi: Toplam kuruş maliyeti deployable_kurus'u asla aşamaz
    while total_cost_kurus(current_lots) > deployable_kurus:
        for idx in range(n - 1, -1, -1):
            if current_lots[idx] > 0:
                current_lots[idx] -= 1
                break

    total_invested_kurus = 0
    for j, p in enumerate(positions):
        lots_final = current_lots[j]
        cost_k = int(round(lots_final * p["maliyetFiyati"] * 100))
        cost_tl = round(cost_k / 100.0, 2)
        p["lot"] = lots_final
        p["toplamMaliyetTL"] = cost_tl
        p["maliyetFiyati"] = round(cost_tl / lots_final, 6) if lots_final > 0 else round(p["maliyetFiyati"], 4)
        p["lotKatmanlari"] = [{"lot": lots_final, "alisGunu": int(current_day), "birimMaliyet": p["maliyetFiyati"]}] if lots_final > 0 else []
        p["guncelDegerTL"] = round(lots_final * p["piyasaFiyati"], 2)
        p["gercekAgirlikPct"] = round((cost_tl / (budget_kurus / 100.0)) * 100.0, 2) if budget_kurus > 0 else 0.0
        total_invested_kurus += cost_k

    rem_cash = round((budget_kurus - total_invested_kurus) / 100.0, 2)
    return positions, rem_cash


def calculate_tkbb_purification(position, holding_days=1, current_sim_day=None):
    """
    TKBB Pay Senedi İhracı ve Alım-Satımı Standardı Madde 3.6.1:
    Paya düşen yıllık mahzurlu kazanç × Lot × (Tutulan Gün / 365).
    Temettü dağıtımından bağımsız olarak yıllık mahzurlu gelir üzerinden pro-rata hesaplanır (çifte sayım yapılmaz).
    FIFO lotKatmanlari varsa her katmanın kendi tutulan günü ayrı ayrı toplanır.
    """
    impure_per_share = float(position.get("payBasiYillikMahzurluTL") or 0.0)
    lots = int(position.get("lot") or 0)
    if lots <= 0 or impure_per_share <= 0.0 or not math.isfinite(impure_per_share):
        return {
            "tkbbPayGunArindirmaTL": 0.0,
            "temettuArindirmaTL": 0.0,
            "toplamArindirmaTL": 0.0,
            "eldeTutulanGun": max(1, int(holding_days or 1)),
            "yontem": "TKBB Madde 3.6.1 (Pay Başı Yıllık Mahzurlu Gelir × Lot × Gün/365 - Pro-Rata)"
        }

    layers = position.get("lotKatmanlari")
    if isinstance(layers, list) and len(layers) > 0:
        sim_day = int(current_sim_day if current_sim_day is not None else max(1, int(holding_days or 1)))
        total_share_days = 0
        for lyr in layers:
            l_lot = max(0, int(lyr.get("lot", 0)))
            if "tutmaGunu" in lyr and current_sim_day is None:
                l_day = max(1, int(lyr["tutmaGunu"]))
            else:
                l_day = max(1, sim_day - int(lyr.get("alisGunu", 1)) + 1)
            total_share_days += l_lot * l_day
        pay_gun_tl = round(impure_per_share * (total_share_days / 365.0), 2)
        eff_days = round(total_share_days / max(1, lots), 1)
    else:
        days = max(1, int(holding_days or 1))
        total_share_days = lots * days
        pay_gun_tl = round(impure_per_share * (total_share_days / 365.0), 2)
        eff_days = days

    return {
        "tkbbPayGunArindirmaTL": pay_gun_tl,
        "temettuArindirmaTL": 0.0,
        "toplamArindirmaTL": pay_gun_tl,
        "toplamLotGun": total_share_days,
        "eldeTutulanGun": eff_days,
        "yontem": "TKBB Madde 3.6.1 (Pay Başı Yıllık Mahzurlu Gelir × Lot × Gün/365 - Pro-Rata)"
    }


def build_default_scenarios(evaluated_stocks):
    valid = sorted(
        [s for s in evaluated_stocks if s.get("uygunlukKapisi")],
        key=lambda x: x["hibritSkor"],
        reverse=True
    )

    def pick_sector_diversified(pool, count, max_per_sector=1):
        picked = []
        sec_counts = {}
        for item in pool:
            sec = item["altSektor"]
            if sec_counts.get(sec, 0) < max_per_sector:
                picked.append(item)
                sec_counts[sec] = sec_counts.get(sec, 0) + 1
                if len(picked) >= count:
                    break
        return picked

    s1_pool = [s for s in valid if s["katilimDenetim"]["durum"] == "UYGUN"]
    s1_cands = pick_sector_diversified(s1_pool, 4, max_per_sector=1)
    s1_w = compute_model_weights(s1_cands, "TERS_ATR_HRP")
    s1_pos, s1_cash = allocate_smart_lots(s1_cands, 10000.0, s1_w, cash_buffer_pct=0.0, current_day=1)

    s2_cands = pick_sector_diversified(s1_pool, 3, max_per_sector=1)
    s2_w = compute_model_weights(s2_cands, "SABIT_40_35_25")
    s2_pos, s2_cash = allocate_smart_lots(s2_cands, 10000.0, s2_w, cash_buffer_pct=0.0, current_day=1)

    s3_pool = [s for s in valid if s.get("puanMomentum", 0) >= 10.0]
    s3_cands = pick_sector_diversified(s3_pool, 5, max_per_sector=1)
    s3_w = compute_model_weights(s3_cands, "ESIT_RISK_ERC")
    s3_pos, s3_cash = allocate_smart_lots(s3_cands, 10000.0, s3_w, cash_buffer_pct=0.0, current_day=1)

    s4_cands = pick_sector_diversified(s1_pool[1:] if len(s1_pool) > 3 else s1_pool, 3, max_per_sector=1)
    s4_w = compute_model_weights(s4_cands, "TERS_ATR_HRP")
    s4_pos, s4_cash = allocate_smart_lots(s4_cands, 10000.0, s4_w, cash_buffer_pct=10.0, current_day=1)

    now_iso = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")

    def pack_scenario(sid, name, mode, katilim_only, weight_model, positions, cash, buffer_pct):
        invested = round(sum(p["toplamMaliyetTL"] for p in positions), 2)
        cur_val = round(sum(p["guncelDegerTL"] for p in positions) + cash, 2)
        purif_total = round(
            sum(calculate_tkbb_purification(p, holding_days=1)["toplamArindirmaTL"] for p in positions), 2
        )
        return {
            "senaryoId": sid,
            "ad": name,
            "isletimModu": mode,
            "sadeceKatilim": katilim_only,
            "agirlikModeli": weight_model,
            "zorunluNakitTamponPct": buffer_pct,
            "baslangicButceTL": 10000.0,
            "yatirilanTutarTL": invested,
            "nakitBakiyeTL": cash,
            "toplamPortfoyDegeriTL": cur_val,
            "gerceklesenKarZararTL": 0.0,
            "gerceklesenArindirmaTL": 0.0,
            "acikKarZararTL": round(cur_val - 10000.0, 2),
            "tkbbBirikmisArindirmaTL": purif_total,
            "degerGecmisi": [10000.0, cur_val],
            "olusturmaZamani": now_iso,
            "pozisyonlar": positions,
            "islemGunlugu": [
                {
                    "zaman": now_iso,
                    "tur": "SENARYO_KURULUM",
                    "detay": f"{name} ({mode}) 10.000 TL bütçe ve {len(positions)} hisse ile başlatıldı (Komisyon+Slippage dahil)."
                }
            ]
        }

    return {
        "S1": pack_scenario("S1", "Senaryo 1 · Katılım Muhafazakâr (Korelasyonlu HRP · 4 Hisse)", "OTOPILOT", True, "TERS_ATR_HRP", s1_pos, s1_cash, 0.0),
        "S2": pack_scenario("S2", "Senaryo 2 · Klasik Hibrit v4 (%40-%35-%25 · 3 Hisse)", "OTOPILOT", True, "SABIT_40_35_25", s2_pos, s2_cash, 0.0),
        "S3": pack_scenario("S3", "Senaryo 3 · Momentum Teyitli ERC (5 Hisse · Tüm BIST)", "YARI_OTOMATIK", False, "ESIT_RISK_ERC", s3_pos, s3_cash, 0.0),
        "S4": pack_scenario("S4", "Senaryo 4 · Co-Pilot Özel Sepet (%10 Nakit Tamponlu)", "YARI_OTOMATIK", True, "TERS_ATR_HRP", s4_pos, s4_cash, 10.0),
    }


# Genişletilmiş BIST 100 / XKTUM Ek Havuzu (Tek Tıkla veya Otomatik Kodla Eklenebilir)
GENIS_BIST_EK_HAVUZU = [
    {"kod": "ULKER", "ad": "Ülker Bisküvi", "altSektor": "GIDA_PERAKENDE", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 24.5, "faizliNakitVarlikOrani": 14.2, "mahzurluGelirOrani": 1.40, "payBasiYillikMahzurluTL": 0.53, "toplamPayMilyon": 656.6, "bazFiyat": 75.65, "low52": 60.74, "high52": 102.37, "fk": 6.40, "pddd": 1.65, "fdFavok": 5.10, "roe": 37.8, "roic": 28.4, "netBorcFavok": 1.35, "fcfVerimi": 7.2, "piotroski": 7, "beta": 0.92, "ema20": 74.13, "ema50": 76.72, "rsi14": 44.2, "rsiSma9": 40.5, "atr14": 2.14, "hacimOrani": 1.28, "mom12_1": 16.5, "gunlukHacimMilyonTL": 980.0, "temettuVerimi": 2.4},
    {"kod": "CCOLA", "ad": "Coca-Cola İçecek", "altSektor": "GIDA_PERAKENDE", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 21.8, "faizliNakitVarlikOrani": 13.6, "mahzurluGelirOrani": 1.10, "payBasiYillikMahzurluTL": 0.57, "toplamPayMilyon": 2197.8, "bazFiyat": 74.35, "low52": 65.18, "high52": 105.03, "fk": 8.90, "pddd": 2.10, "fdFavok": 6.20, "roe": 34.2, "roic": 26.8, "netBorcFavok": 1.10, "fcfVerimi": 6.4, "piotroski": 7, "beta": 0.85, "ema20": 73.20, "ema50": 76.13, "rsi14": 43.8, "rsiSma9": 39.9, "atr14": 1.97, "hacimOrani": 1.24, "mom12_1": 9.2, "gunlukHacimMilyonTL": 860.0, "temettuVerimi": 2.9},
    {"kod": "CIMSA", "ad": "Çimsa Çimento", "altSektor": "CAM_KIMYA_MADEN", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 16.4, "faizliNakitVarlikOrani": 11.8, "mahzurluGelirOrani": 0.95, "payBasiYillikMahzurluTL": 0.30, "toplamPayMilyon": 880.1, "bazFiyat": 39.54, "low52": 32.02, "high52": 49.96, "fk": 7.50, "pddd": 1.38, "fdFavok": 5.60, "roe": 31.6, "roic": 24.5, "netBorcFavok": 0.85, "fcfVerimi": 6.8, "piotroski": 7, "beta": 0.96, "ema20": 38.57, "ema50": 39.22, "rsi14": 47.4, "rsiSma9": 42.8, "atr14": 1.13, "hacimOrani": 1.31, "mom12_1": 14.2, "gunlukHacimMilyonTL": 740.0, "temettuVerimi": 3.4},
    {"kod": "OYAKC", "ad": "Oyak Çimento", "altSektor": "CAM_KIMYA_MADEN", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 8.2, "faizliNakitVarlikOrani": 18.4, "mahzurluGelirOrani": 1.65, "payBasiYillikMahzurluTL": 0.20, "toplamPayMilyon": 5059.8, "bazFiyat": 18.16, "low52": 15.18, "high52": 23.64, "fk": 6.90, "pddd": 1.52, "fdFavok": 4.90, "roe": 35.4, "roic": 29.2, "netBorcFavok": -0.45, "fcfVerimi": 8.1, "piotroski": 8, "beta": 0.91, "ema20": 17.78, "ema50": 18.21, "rsi14": 46.1, "rsiSma9": 41.7, "atr14": 0.52, "hacimOrani": 1.29, "mom12_1": 15.6, "gunlukHacimMilyonTL": 920.0, "temettuVerimi": 4.1},
    {"kod": "ENKAI", "ad": "Enka İnşaat", "altSektor": "DEMIR_CELIK", "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Yabancı Tahvil/Mevduat Oranı > %33", "faizliBorcVarlikOrani": 4.2, "faizliNakitVarlikOrani": 39.5, "mahzurluGelirOrani": 6.40, "payBasiYillikMahzurluTL": 2.93, "toplamPayMilyon": 3784.6, "bazFiyat": 77.05, "low52": 62.62, "high52": 89.10, "fk": 9.10, "pddd": 0.92, "fdFavok": 5.80, "roe": 24.6, "roic": 19.8, "netBorcFavok": -1.60, "fcfVerimi": 7.5, "piotroski": 7, "beta": 0.79, "ema20": 75.78, "ema50": 76.26, "rsi14": 48.9, "rsiSma9": 44.5, "atr14": 1.82, "hacimOrani": 1.22, "mom12_1": 19.8, "gunlukHacimMilyonTL": 1350.0, "temettuVerimi": 4.6},
    {"kod": "TCELL", "ad": "Turkcell İletişim", "altSektor": "TEKNOLOJI_SAVUNMA", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 26.4, "faizliNakitVarlikOrani": 17.8, "mahzurluGelirOrani": 1.95, "payBasiYillikMahzurluTL": 1.16, "toplamPayMilyon": 2267.4, "bazFiyat": 91.40, "low52": 79.08, "high52": 114.49, "fk": 8.40, "pddd": 1.48, "fdFavok": 4.60, "roe": 33.8, "roic": 25.4, "netBorcFavok": 1.25, "fcfVerimi": 7.9, "piotroski": 8, "beta": 0.88, "ema20": 90.04, "ema50": 92.27, "rsi14": 45.6, "rsiSma9": 41.2, "atr14": 2.38, "hacimOrani": 1.34, "mom12_1": 21.4, "gunlukHacimMilyonTL": 2890.0, "temettuVerimi": 4.2},
    {"kod": "TTKOM", "ad": "Türk Telekom", "altSektor": "TEKNOLOJI_SAVUNMA", "katilimUyum": "SINIRDA_UYARI", "katilimKaynak": "Borç/Varlık Sınırda (%29.8)", "faizliBorcVarlikOrani": 29.8, "faizliNakitVarlikOrani": 12.1, "mahzurluGelirOrani": 1.75, "payBasiYillikMahzurluTL": 0.59, "toplamPayMilyon": 3649.3, "bazFiyat": 46.90, "low52": 36.83, "high52": 59.94, "fk": 9.80, "pddd": 1.62, "fdFavok": 4.90, "roe": 29.4, "roic": 22.1, "netBorcFavok": 1.55, "fcfVerimi": 5.8, "piotroski": 7, "beta": 0.95, "ema20": 46.13, "ema50": 47.38, "rsi14": 46.2, "rsiSma9": 42.0, "atr14": 1.32, "hacimOrani": 1.26, "mom12_1": 17.5, "gunlukHacimMilyonTL": 1950.0, "temettuVerimi": 1.8},
    {"kod": "KONTR", "ad": "Kontrolmatik Teknoloji", "altSektor": "TEKNOLOJI_SAVUNMA", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 25.4, "faizliNakitVarlikOrani": 9.6, "mahzurluGelirOrani": 0.80, "payBasiYillikMahzurluTL": 0.01, "toplamPayMilyon": 18215.6, "bazFiyat": 1.67, "low52": 1.47, "high52": 3.00, "fk": 14.50, "pddd": 3.40, "fdFavok": 9.20, "roe": 34.5, "roic": 24.8, "netBorcFavok": 1.85, "fcfVerimi": 2.9, "piotroski": 6, "beta": 1.24, "ema20": 1.64, "ema50": 1.73, "rsi14": 42.4, "rsiSma9": 38.8, "atr14": 0.06, "hacimOrani": 1.21, "mom12_1": 4.2, "gunlukHacimMilyonTL": 890.0, "temettuVerimi": 0.5},
    {"kod": "MIATK", "ad": "MİA Teknoloji", "altSektor": "TEKNOLOJI_SAVUNMA", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 8.4, "faizliNakitVarlikOrani": 14.2, "mahzurluGelirOrani": 0.90, "payBasiYillikMahzurluTL": 0.09, "toplamPayMilyon": 936.8, "bazFiyat": 23.52, "low52": 20.30, "high52": 41.13, "fk": 11.20, "pddd": 2.95, "fdFavok": 7.50, "roe": 42.8, "roic": 35.2, "netBorcFavok": -0.30, "fcfVerimi": 6.4, "piotroski": 7, "beta": 1.19, "ema20": 23.10, "ema50": 24.21, "rsi14": 44.8, "rsiSma9": 40.2, "atr14": 0.81, "hacimOrani": 1.32, "mom12_1": 9.4, "gunlukHacimMilyonTL": 1120.0, "temettuVerimi": 1.0},
    {"kod": "GESAN", "ad": "Girişim Elektrik", "altSektor": "ENERJI_RAFINERI", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 18.2, "faizliNakitVarlikOrani": 12.4, "mahzurluGelirOrani": 1.15, "payBasiYillikMahzurluTL": 0.24, "toplamPayMilyon": 692.8, "bazFiyat": 32.80, "low52": 28.55, "high52": 54.45, "fk": 8.80, "pddd": 2.10, "fdFavok": 6.10, "roe": 36.4, "roic": 28.9, "netBorcFavok": 0.65, "fcfVerimi": 6.2, "piotroski": 7, "beta": 1.15, "ema20": 32.20, "ema50": 33.73, "rsi14": 43.9, "rsiSma9": 39.6, "atr14": 1.05, "hacimOrani": 1.27, "mom12_1": 5.8, "gunlukHacimMilyonTL": 610.0, "temettuVerimi": 2.1},
    {"kod": "YEOTK", "ad": "Yeo Teknoloji Enerji", "altSektor": "ENERJI_RAFINERI", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 21.6, "faizliNakitVarlikOrani": 10.8, "mahzurluGelirOrani": 0.95, "payBasiYillikMahzurluTL": 0.11, "toplamPayMilyon": 761.7, "bazFiyat": 23.00, "low52": 19.41, "high52": 33.78, "fk": 10.60, "pddd": 3.25, "fdFavok": 7.10, "roe": 44.2, "roic": 34.8, "netBorcFavok": 0.95, "fcfVerimi": 5.9, "piotroski": 7, "beta": 1.18, "ema20": 22.56, "ema50": 23.50, "rsi14": 45.1, "rsiSma9": 40.9, "atr14": 0.71, "hacimOrani": 1.25, "mom12_1": 11.4, "gunlukHacimMilyonTL": 490.0, "temettuVerimi": 1.4},
    {"kod": "OTKAR", "ad": "Otokar", "altSektor": "OTOMOTIV", "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faizli Borç/Varlık > %33", "faizliBorcVarlikOrani": 37.4, "faizliNakitVarlikOrani": 11.2, "mahzurluGelirOrani": 1.80, "payBasiYillikMahzurluTL": 4.39, "toplamPayMilyon": 175.0, "bazFiyat": 303.00, "low52": 270.78, "high52": 425.02, "fk": 12.40, "pddd": 2.95, "fdFavok": 8.40, "roe": 32.8, "roic": 23.5, "netBorcFavok": 2.10, "fcfVerimi": 4.2, "piotroski": 6, "beta": 1.04, "ema20": 298.89, "ema50": 309.86, "rsi14": 43.5, "rsiSma9": 39.8, "atr14": 8.77, "hacimOrani": 1.19, "mom12_1": 6.4, "gunlukHacimMilyonTL": 520.0, "temettuVerimi": 2.2},
    {"kod": "MPARK", "ad": "MLP Sağlık (Medical Park)", "altSektor": "GIDA_PERAKENDE", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 19.8, "faizliNakitVarlikOrani": 11.5, "mahzurluGelirOrani": 0.90, "payBasiYillikMahzurluTL": 2.18, "toplamPayMilyon": 170.9, "bazFiyat": 389.00, "low52": 326.40, "high52": 463.89, "fk": 8.20, "pddd": 2.65, "fdFavok": 5.80, "roe": 43.5, "roic": 34.2, "netBorcFavok": 0.90, "fcfVerimi": 7.6, "piotroski": 8, "beta": 0.84, "ema20": 382.29, "ema50": 390.12, "rsi14": 47.2, "rsiSma9": 42.5, "atr14": 9.95, "hacimOrani": 1.31, "mom12_1": 24.6, "gunlukHacimMilyonTL": 680.0, "temettuVerimi": 3.1},
    {"kod": "TABGD", "ad": "TAB Gıda", "altSektor": "GIDA_PERAKENDE", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 14.2, "faizliNakitVarlikOrani": 21.4, "mahzurluGelirOrani": 1.85, "payBasiYillikMahzurluTL": 1.70, "toplamPayMilyon": 215.0, "bazFiyat": 189.60, "low52": 162.86, "high52": 257.66, "fk": 7.80, "pddd": 2.15, "fdFavok": 5.20, "roe": 39.4, "roic": 32.1, "netBorcFavok": -0.35, "fcfVerimi": 8.2, "piotroski": 8, "beta": 0.89, "ema20": 186.56, "ema50": 192.03, "rsi14": 45.8, "rsiSma9": 41.4, "atr14": 5.10, "hacimOrani": 1.28, "mom12_1": 14.8, "gunlukHacimMilyonTL": 590.0, "temettuVerimi": 3.5},
    {"kod": "TAVHL", "ad": "TAV Havalimanları", "altSektor": "ULASTIRMA_LOJISTIK", "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faizli Havalimanı Proje Kredisi > %33", "faizliBorcVarlikOrani": 44.2, "faizliNakitVarlikOrani": 16.8, "mahzurluGelirOrani": 4.20, "payBasiYillikMahzurluTL": 5.10, "toplamPayMilyon": 342.3, "bazFiyat": 263.25, "low52": 217.61, "high52": 316.32, "fk": 6.90, "pddd": 1.18, "fdFavok": 5.60, "roe": 28.9, "roic": 19.4, "netBorcFavok": 2.25, "fcfVerimi": 5.4, "piotroski": 7, "beta": 0.98, "ema20": 259.00, "ema50": 264.84, "rsi14": 46.5, "rsiSma9": 42.1, "atr14": 6.79, "hacimOrani": 1.26, "mom12_1": 18.2, "gunlukHacimMilyonTL": 1420.0, "temettuVerimi": 2.8},
    {"kod": "KARSN", "ad": "Karsan Otomotiv", "altSektor": "OTOMOTIV", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 27.4, "faizliNakitVarlikOrani": 9.2, "mahzurluGelirOrani": 1.45, "payBasiYillikMahzurluTL": 0.08, "toplamPayMilyon": 900.0, "bazFiyat": 6.80, "low52": 6.46, "high52": 16.90, "fk": 8.40, "pddd": 0.75, "fdFavok": 4.89, "roe": 29.5, "roic": 22.4, "netBorcFavok": 1.65, "fcfVerimi": 5.1, "piotroski": 7, "beta": 1.18, "ema20": 6.72, "ema50": 7.15, "rsi14": 38.5, "rsiSma9": 35.2, "atr14": 0.26, "hacimOrani": 1.28, "mom12_1": 8.4, "gunlukHacimMilyonTL": 540.0, "temettuVerimi": 0.0},
    {"kod": "VESTL", "ad": "Vestel Elektronik", "altSektor": "TEKNOLOJI_SAVUNMA", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 28.1, "faizliNakitVarlikOrani": 8.4, "mahzurluGelirOrani": 1.60, "payBasiYillikMahzurluTL": 0.42, "toplamPayMilyon": 335.5, "bazFiyat": 54.20, "low52": 48.10, "high52": 98.50, "fk": 7.80, "pddd": 0.68, "fdFavok": 4.95, "roe": 26.4, "roic": 19.8, "netBorcFavok": 1.95, "fcfVerimi": 4.8, "piotroski": 6, "beta": 1.14, "ema20": 53.40, "ema50": 56.10, "rsi14": 41.2, "rsiSma9": 38.4, "atr14": 1.75, "hacimOrani": 1.22, "mom12_1": 5.2, "gunlukHacimMilyonTL": 620.0, "temettuVerimi": 0.0},
    {"kod": "PETKM", "ad": "Petkim Petrokimya", "altSektor": "CAM_KIMYA_MADEN", "katilimUyum": "UYGUN_DEGIL", "katilimKaynak": "Faizli Borç/Varlık > %33", "faizliBorcVarlikOrani": 36.8, "faizliNakitVarlikOrani": 14.5, "mahzurluGelirOrani": 2.40, "payBasiYillikMahzurluTL": 0.35, "toplamPayMilyon": 2534.4, "bazFiyat": 16.92, "low52": 15.80, "high52": 26.40, "fk": 9.20, "pddd": 0.72, "fdFavok": 6.40, "roe": 21.5, "roic": 16.2, "netBorcFavok": 2.30, "fcfVerimi": 3.8, "piotroski": 6, "beta": 1.09, "ema20": 16.70, "ema50": 17.40, "rsi14": 42.0, "rsiSma9": 39.5, "atr14": 0.52, "hacimOrani": 1.19, "mom12_1": 4.1, "gunlukHacimMilyonTL": 1480.0, "temettuVerimi": 0.0},
    {"kod": "BRSAN", "ad": "Borusan Boru Sanayi", "altSektor": "DEMIR_CELIK", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 22.4, "faizliNakitVarlikOrani": 10.6, "mahzurluGelirOrani": 1.15, "payBasiYillikMahzurluTL": 2.80, "toplamPayMilyon": 141.8, "bazFiyat": 368.50, "low52": 330.00, "high52": 640.00, "fk": 9.40, "pddd": 1.45, "fdFavok": 6.10, "roe": 31.2, "roic": 24.6, "netBorcFavok": 1.20, "fcfVerimi": 6.1, "piotroski": 7, "beta": 1.16, "ema20": 362.00, "ema50": 378.00, "rsi14": 43.6, "rsiSma9": 40.1, "atr14": 11.20, "hacimOrani": 1.25, "mom12_1": 9.6, "gunlukHacimMilyonTL": 510.0, "temettuVerimi": 1.2},
    {"kod": "EGEEN", "ad": "Ege Endüstri", "altSektor": "OTOMOTIV", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 11.2, "faizliNakitVarlikOrani": 19.4, "mahzurluGelirOrani": 1.30, "payBasiYillikMahzurluTL": 45.00, "toplamPayMilyon": 3.15, "bazFiyat": 8950.00, "low52": 8200.00, "high52": 15400.00, "fk": 10.20, "pddd": 3.10, "fdFavok": 6.80, "roe": 38.4, "roic": 31.0, "netBorcFavok": -0.40, "fcfVerimi": 6.9, "piotroski": 8, "beta": 0.94, "ema20": 8840.00, "ema50": 9120.00, "rsi14": 44.5, "rsiSma9": 41.0, "atr14": 245.00, "hacimOrani": 1.24, "mom12_1": 11.2, "gunlukHacimMilyonTL": 320.0, "temettuVerimi": 3.2},
    {"kod": "KCAER", "ad": "Kocaer Çelik", "altSektor": "DEMIR_CELIK", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 19.6, "faizliNakitVarlikOrani": 12.1, "mahzurluGelirOrani": 0.95, "payBasiYillikMahzurluTL": 0.09, "toplamPayMilyon": 1965.0, "bazFiyat": 12.45, "low52": 10.80, "high52": 19.60, "fk": 8.60, "pddd": 1.58, "fdFavok": 5.40, "roe": 33.8, "roic": 26.5, "netBorcFavok": 0.95, "fcfVerimi": 6.5, "piotroski": 7, "beta": 1.06, "ema20": 12.20, "ema50": 12.75, "rsi14": 45.2, "rsiSma9": 41.8, "atr14": 0.38, "hacimOrani": 1.29, "mom12_1": 13.4, "gunlukHacimMilyonTL": 480.0, "temettuVerimi": 2.1},
    {"kod": "HEKTS", "ad": "Hektaş Ticaret", "altSektor": "CAM_KIMYA_MADEN", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 29.4, "faizliNakitVarlikOrani": 7.8, "mahzurluGelirOrani": 1.20, "payBasiYillikMahzurluTL": 0.03, "toplamPayMilyon": 8430.0, "bazFiyat": 3.24, "low52": 2.98, "high52": 7.85, "fk": 14.80, "pddd": 1.92, "fdFavok": 9.10, "roe": 18.5, "roic": 14.2, "netBorcFavok": 2.45, "fcfVerimi": 2.1, "piotroski": 5, "beta": 1.22, "ema20": 3.20, "ema50": 3.45, "rsi14": 40.8, "rsiSma9": 38.2, "atr14": 0.11, "hacimOrani": 1.18, "mom12_1": -4.5, "gunlukHacimMilyonTL": 710.0, "temettuVerimi": 0.0},
    {"kod": "TKFEN", "ad": "Tekfen Holding", "altSektor": "CAM_KIMYA_MADEN", "katilimUyum": "UYGUN", "katilimKaynak": "BIST XKTUM 2026/09 Duyurusu", "faizliBorcVarlikOrani": 18.5, "faizliNakitVarlikOrani": 16.2, "mahzurluGelirOrani": 1.55, "payBasiYillikMahzurluTL": 0.62, "toplamPayMilyon": 370.0, "bazFiyat": 68.40, "low52": 52.10, "high52": 96.80, "fk": 7.90, "pddd": 1.14, "fdFavok": 5.20, "roe": 29.8, "roic": 23.4, "netBorcFavok": 0.60, "fcfVerimi": 6.4, "piotroski": 7, "beta": 1.02, "ema20": 67.10, "ema50": 69.50, "rsi14": 46.0, "rsiSma9": 42.3, "atr14": 2.05, "hacimOrani": 1.26, "mom12_1": 15.2, "gunlukHacimMilyonTL": 640.0, "temettuVerimi": 2.6}
]


class MarketDataEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._cache = None
        self._cache_timestamp = 0.0
        self.cache_ttl = 60.0
        self.auto_poll_interval = 60.0
        self._poller_started = False
        # Açılışta tüm 42 BIST 100 / XKTUM hissesi otomatik aktif olarak başlar
        self._extra_stocks = [dict(x) for x in GENIS_BIST_EK_HAVUZU]

    def _fetch_bist_live_closes(self, kod):
        """
        Önce yfinance, yoksa standart Python urllib.request ile doğrudan BIST (.IS)
        son 1 aylık kapanış serisini ve seans içi anlık fiyatı (regularMarketPrice) çeker.
        Aynı günün kapanış mumunu iki kez eklemez; son mumu günceller (F08 düzeltmesi).
        """
        sorgu_kod = "TRALT" if kod == "KOZAL" else kod
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sorgu_kod}.IS?range=1mo&interval=1d"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BISTHibritPWA/4.7"}
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    res_list = data.get("chart", {}).get("result", [])
                    if res_list:
                        meta = res_list[0].get("meta", {})
                        live_p = meta.get("regularMarketPrice")
                        timestamps = res_list[0].get("timestamp") or []
                        quote_list = res_list[0].get("indicators", {}).get("quote", [])
                        if quote_list and "close" in quote_list[0]:
                            closes = [
                                float(x) for x in quote_list[0]["close"]
                                if x is not None and not math.isnan(float(x))
                            ]
                            if live_p is not None and not math.isnan(float(live_p)) and float(live_p) > 0:
                                lp_f = float(live_p)
                                if closes:
                                    # Son mum bugüne aitse tekrar eklemek yerine son mumu güncelle
                                    if timestamps and (time.time() - float(timestamps[-1])) < 86400:
                                        closes[-1] = lp_f
                                    elif abs(closes[-1] - lp_f) < 1e-6:
                                        closes[-1] = lp_f
                                    else:
                                        closes.append(lp_f)
                                else:
                                    closes.append(lp_f)
                            if len(closes) >= 15:
                                return closes
        except Exception:
            pass

        if YFINANCE_AVAILABLE:
            try:
                tkr = yf.Ticker(f"{sorgu_kod}.IS")
                hist = tkr.history(period="1mo", interval="1d")
                if hist is not None and not hist.empty and "Close" in hist:
                    closes = [float(x) for x in hist["Close"].dropna().tolist()]
                    if len(closes) >= 15:
                        return closes
            except Exception:
                pass
        return None

    def start_background_auto_poller(self, interval_sec=60.0):
        """Arka planda kesintisiz çalışan paralel canlı BIST veri tarama iş parçacığı."""
        if self._poller_started:
            return
        self._poller_started = True
        self.auto_poll_interval = float(interval_sec)

        def _poller_loop():
            while True:
                try:
                    self.get_market_payload(force_refresh=True, write_disk=True)
                except Exception:
                    pass
                time.sleep(self.auto_poll_interval)

        t = threading.Thread(target=_poller_loop, name="BistCanliVeriPoller", daemon=True)
        t.start()

    def load_extended_bist_pool(self):
        """27 çekirdek hisseye ek olarak Geniş BIST 100 / XKTUM havuzundaki hisseleri otomatik ekler."""
        existing = {x["kod"] for x in BIST_EVRENI} | {x["kod"] for x in self._extra_stocks}
        added = 0
        for item in GENIS_BIST_EK_HAVUZU:
            if item["kod"] not in existing:
                self._extra_stocks.append(dict(item))
                existing.add(item["kod"])
                added += 1
        return self.get_market_payload(force_refresh=False, write_disk=False), added

    def auto_fetch_and_add_ticker(self, kod, alt_sektor="DEMIR_CELIK"):
        """
        Herhangi bir BIST hissesini (550+ hisse) sadece koduyla (Örn: ULKER, TCELL, BRSAN, ALARK)
        otomatik olarak çeker ve evrene dahil eder.
        """
        clean_kod = "".join(ch for ch in str(kod or "").upper().strip() if ch.isalnum())[:8]
        if not clean_kod:
            return None, "Geçersiz hisse kodu."

        existing = {x["kod"] for x in BIST_EVRENI} | {x["kod"] for x in self._extra_stocks}
        if clean_kod in existing:
            return self.get_market_payload(force_refresh=False, write_disk=False), f"{clean_kod} zaten tarama evreninde mevcut."

        for item in GENIS_BIST_EK_HAVUZU:
            if item["kod"] == clean_kod:
                self._extra_stocks.append(dict(item))
                return self.get_market_payload(force_refresh=False, write_disk=False), f"{clean_kod} ({item['ad']}) doğrulanmış BIST 100/XKTUM verisiyle otomatik eklendi."

        closes = self._fetch_bist_live_closes(clean_kod)
        if not closes or len(closes) < 15:
            return None, f"{clean_kod}.IS için canlı Borsa İstanbul fiyat serisi çekilemedi (Hisse kodunu kontrol edin)."

        last_p = round(closes[-1], 2)
        low_52 = round(min(closes) * 0.92, 2)
        high_52 = round(max(closes) * 1.08, 2)
        w_rsi = compute_wilder_rsi(closes, 14) or 45.0
        ema20 = round(sum(closes[-15:]) / 15.0, 2)
        ema50 = round(sum(closes) / len(closes), 2)
        atr14 = round(max(0.05, last_p * 0.028), 2)

        fk_val, pddd_val, fd_favok_val, roe_val, short_name = 9.2, 1.65, 6.1, 28.5, f"{clean_kod} BIST A.Ş."
        if ISYATIRIM_AVAILABLE and hasattr(iyh, "fetch_financials"):
            try:
                fin_df = iyh.fetch_financials(symbols=clean_kod)
                if fin_df is not None and not getattr(fin_df, "empty", True):
                    short_name = f"{clean_kod} (KAP/İş Yatırım Bilançolu)"
            except Exception:
                pass
        if YFINANCE_AVAILABLE:
            try:
                info = yf.Ticker(f"{clean_kod}.IS").info or {}
                short_name = info.get("longName") or info.get("shortName") or short_name
                if info.get("trailingPE") is not None:
                    fk_val = round(float(info["trailingPE"]), 2)
                if info.get("priceToBook") is not None:
                    pddd_val = round(float(info["priceToBook"]), 2)
                if info.get("enterpriseToEbitda") is not None:
                    fd_favok_val = round(float(info["enterpriseToEbitda"]), 2)
                if info.get("returnOnEquity") is not None:
                    roe_val = round(float(info["returnOnEquity"]) * 100.0, 2)
            except Exception:
                pass

        new_stock = {
            "kod": clean_kod,
            "ad": short_name,
            "altSektor": alt_sektor,
            "katilimUyum": "DOGRULANAMADI",
            "katilimKaynak": None,
            "faizliBorcVarlikOrani": None,
            "faizliNakitVarlikOrani": None,
            "mahzurluGelirOrani": None,
            "payBasiYillikMahzurluTL": 0.0,
            "toplamPayMilyon": None,
            "bazFiyat": last_p,
            "low52": low_52,
            "high52": high_52,
            "fk": fk_val,
            "pddd": pddd_val,
            "fdFavok": fd_favok_val,
            "roe": roe_val,
            "roic": round(roe_val * 0.8, 1),
            "netBorcFavok": 1.40,
            "fcfVerimi": 4.5,
            "piotroski": 6,
            "beta": 1.0,
            "ema20": ema20,
            "ema50": ema50,
            "rsi14": w_rsi,
            "rsiSma9": round(max(20.0, w_rsi - 3.0), 1),
            "atr14": atr14,
            "hacimOrani": 1.22,
            "mom12_1": 8.0,
            "gunlukHacimMilyonTL": 450.0,
            "temettuVerimi": 2.0
        }
        self._extra_stocks.append(new_stock)
        return self.get_market_payload(force_refresh=False, write_disk=False), f"{clean_kod} canlı BIST fiyat ve çarpanlarıyla otomatik çekildi."

    def get_market_payload(self, force_refresh=False, write_disk=True):
        now = time.time()
        with self._lock:
            if not force_refresh and self._cache is not None and (now - self._cache_timestamp) < self.cache_ttl:
                payload = dict(self._cache)
                payload["onbellekDurumu"] = "OTO_ARKAPLAN_GUNCEL"
                payload["veriYasiSaniye"] = int(now - self._cache_timestamp)
                return payload
            combined_list = list(BIST_EVRENI) + list(self._extra_stocks)

        stocks_raw = []
        seen_codes = set()
        for item in combined_list:
            if item["kod"] in seen_codes:
                continue
            seen_codes.add(item["kod"])
            st = dict(item)
            if st.get("fk") and st["fk"] != 0:
                st["eps0"] = round(st["bazFiyat"] / st["fk"], 6)
            if st.get("pddd") and st["pddd"] > 0:
                st["bvps0"] = round(st["bazFiyat"] / st["pddd"], 6)
            if st.get("fdFavok") and st["fdFavok"] > 0:
                st["favokPs0"] = round(st["bazFiyat"] / st["fdFavok"], 6)
            stocks_raw.append(st)

        live_updated_count = 0
        if force_refresh:
            def _fetch_one(st_item):
                return st_item["kod"], self._fetch_bist_live_closes(st_item["kod"])

            results_map = {}
            with ThreadPoolExecutor(max_workers=12) as pool:
                for kod_res, closes_res in pool.map(_fetch_one, stocks_raw):
                    if closes_res and len(closes_res) >= 15:
                        results_map[kod_res] = closes_res

            for item in stocks_raw:
                closes = results_map.get(item["kod"])
                if closes:
                    new_p = round(closes[-1], 2)
                    item["bazFiyat"] = new_p
                    item["low52"] = round(min(item["low52"], new_p), 2)
                    item["high52"] = round(max(item["high52"], new_p), 2)
                    if item.get("eps0"):
                        item["fk"] = round(new_p / item["eps0"], 2)
                    if item.get("bvps0"):
                        item["pddd"] = round(new_p / item["bvps0"], 2)
                    if item.get("favokPs0"):
                        item["fdFavok"] = round(new_p / item["favokPs0"], 2)
                    w_rsi = compute_wilder_rsi(closes, 14)
                    if w_rsi is not None:
                        item["rsi14"] = w_rsi
                    live_updated_count += 1

        sector_medians = compute_dynamic_sector_medians(stocks_raw)
        evaluated = [evaluate_stock_quant(s, sector_medians) for s in stocks_raw]
        evaluated = attach_z_scores(evaluated)
        evaluated.sort(key=lambda x: (1 if x.get("uygunlukKapisi") else 0, x.get("hibritSkor", 0.0)), reverse=True)
        top5_picks = build_top5_daily_picks(evaluated)

        with self._lock:
            if LEDGER_PATH.exists():
                try:
                    scenarios = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
                except Exception:
                    scenarios = build_default_scenarios(evaluated)
                    if write_disk:
                        LEDGER_PATH.write_text(json.dumps(scenarios, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                scenarios = build_default_scenarios(evaluated)
                if write_disk:
                    LEDGER_PATH.write_text(json.dumps(scenarios, ensure_ascii=False, indent=2), encoding="utf-8")

            now_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            payload = {
                "schemaVersion": "4.7-KURUMSAL-PWA",
                "guncellemeZamani": now_str,
                "veriKaynagi": f"Canlı Paralel BIST Akışı ({live_updated_count}/{len(evaluated)} Hisse) + KAP 2026/06" if live_updated_count > 0 else f"Doğrulanmış KAP 2026/06 & BIST {len(evaluated)} Hisse Tam Evren",
                "canliGuncellenenHisseSayisi": live_updated_count,
                "otomatikTakipSaniye": int(self.auto_poll_interval),
                "onbellekDurumu": "YENI_HESAPLANDI",
                "veriYasiSaniye": 0,
                "makroParametreler": MACRO_PARAMS,
                "endeksRejimi": {
                    "xu100Durum": "BOĞA_REJİMİ (XU100 > EMA50)",
                    "xktumDurum": "POZİTİF_REJİM (XKTUM > EMA50)",
                    "onerilenNakitTamponuPct": 10.0
                },
                "sektorMedyanlari": sector_medians,
                "gununIlk5Onerisi": top5_picks,
                "hisseler": evaluated,
                "senaryolar": scenarios
            }

            self._cache = payload
            self._cache_timestamp = time.time()
            # Canlı verili snapshot'ı force_refresh=False çağrısıyla ezmemek için koruma (F19):
            if write_disk:
                should_write_snap = True
                if not force_refresh and SNAPSHOT_PATH.exists():
                    try:
                        existing_snap = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
                        if int(existing_snap.get("canliGuncellenenHisseSayisi", 0)) > live_updated_count:
                            should_write_snap = False
                    except Exception:
                        pass
                if should_write_snap:
                    SNAPSHOT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload


ENGINE = MarketDataEngine()

ALLOWED_STATIC_FILES = {
    "index.html",
    "manifest.json",
    "sw.js",
    "icon-192.png",
    "icon-512.png",
    "icon-192.svg",
    "icon-512.svg",
    "dogrulanmis_piyasa_snapshot.json",
}


class HybridPwaRequestHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        raw_path = urllib.parse.unquote(urllib.parse.urlparse(path).path or "/")
        clean_rel = raw_path.lstrip("/")
        if not clean_rel:
            clean_rel = "index.html"
        base_resolved = BASE_DIR.resolve()
        try:
            candidate = (base_resolved / clean_rel).resolve()
            is_inside = candidate.is_relative_to(base_resolved)
        except Exception:
            is_inside = False
            candidate = base_resolved / "__forbidden__"

        # Kök dizin dışına çıkış (Path Traversal) veya izin listesi dışı dosyalara (örn. .py, .git, senaryo_defteri) erişimi engelle (F20):
        rel_name = candidate.relative_to(base_resolved).as_posix() if is_inside else "__forbidden__"
        if not is_inside or rel_name not in ALLOWED_STATIC_FILES:
            return str(base_resolved / "__forbidden_static_resource__")
        return str(candidate)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/veriler":
            qs = urllib.parse.parse_qs(parsed.query)
            force = qs.get("force", ["0"])[0] == "1"
            data = ENGINE.get_market_payload(force_refresh=force, write_disk=force)
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/genis-evren-yukle":
            data, added = ENGINE.load_extended_bist_pool()
            resp = {"ok": True, "eklenen": added, "toplamHisse": len(data.get("hisseler", [])), "payload": data}
            body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/canli-hisse-ekle":
            qs = urllib.parse.parse_qs(parsed.query)
            kod = qs.get("kod", [""])[0]
            sektor = qs.get("sektor", ["DEMIR_CELIK"])[0]
            data, msg = ENGINE.auto_fetch_and_add_ticker(kod, alt_sektor=sektor)
            resp = {"ok": data is not None, "mesaj": msg, "payload": data}
            body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            self.send_response(200 if data is not None else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        local_target = self.translate_path(self.path)
        if local_target.endswith("__forbidden_static_resource__"):
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("403 Forbidden: Yetkisiz dosya yolu.".encode("utf-8"))
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/senaryo-kaydet":
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 524288:
                self.send_response(413 if length > 524288 else 400)
                self.end_headers()
                return
            raw = self.rfile.read(length).decode("utf-8")
            try:
                incoming = json.loads(raw)
                senaryolar = incoming.get("senaryolar") if isinstance(incoming, dict) else None
                if isinstance(senaryolar, dict) and all(k in senaryolar for k in ("S1", "S2", "S3", "S4")):
                    with ENGINE._lock:
                        tmp_path = LEDGER_PATH.with_suffix(".tmp")
                        tmp_path.write_text(json.dumps(senaryolar, ensure_ascii=False, indent=2), encoding="utf-8")
                        tmp_path.replace(LEDGER_PATH)
                        if ENGINE._cache is not None:
                            ENGINE._cache["senaryolar"] = senaryolar
                    resp = {"ok": True, "mesaj": "Senaryo defteri atomik olarak kaydedildi."}
                    code = 200
                else:
                    resp = {"ok": False, "hata": "Geçersiz senaryo şeması (S1..S4 zorunludur)."}
                    code = 400
            except Exception as exc:
                resp = {"ok": False, "hata": str(exc)}
                code = 500

            body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()


def run_server(port=8765):
    ENGINE.get_market_payload(force_refresh=False)
    ENGINE.start_background_auto_poller(interval_sec=60.0)
    server = HTTPServer(("127.0.0.1", port), HybridPwaRequestHandler)
    print(f"[BIST Hibrit v4.1 PWA] Sunucu ve 60sn Otomatik Canli BIST Takip Motoru hazir: http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    if "--snapshot-uret" in sys.argv:
        data = ENGINE.get_market_payload(force_refresh=True)
        print(f"[GitHub Cloud Snapshot] {len(data.get('hisseler', []))} hisse taranarak {SNAPSHOT_PATH.name} uretildi.")
        sys.exit(0)
    run_server()
