# 📈 BIST Hibrit Analiz, İlk 5 Günlük Öneri & Sesli Portföy Terminali (v4.2 PWA)

Bu paket hem **masaüstünde (`BASLAT_PWA.bat`)** hem de **GitHub Pages üzerinde (bilgisayarınız kapalıyken bile 7/24 telefonunuzda)** çalışacak şekilde tasarlanmıştır.

---

## 🚀 Özellikler

1. **🎯 Günün Getiri İhtimali En Yüksek 5 Hissesi (Tüm Evren Analizi):**
   - 42+ BIST 100 ve BIST Katılım (`XKTUM`) hissesinin tamamı paralel olarak analiz edilir.
   - Her hisse için **Kazanma Olasılığı ($P_{\text{win}}$ %)**, **30G Hedef Getiri (%)**, **Chandelier ATR Stop (%)**, **Ödül/Risk Oranı ($R/R$)** ve **Otomatik Seçilme Gerekçesi** hesaplanarak en üst vitrinde listelenir.
2. **🔊 Telefonda Kişisel Portföy Bazlı Türkçe Sesli Uyarı (`Web Speech API tr-TR` + `Web Audio`):**
   - Üst bardaki **`📱 Kendi Portföyümü Gir`** butonuyla elinizdeki gerçek hisseleri (Kod, Lot, Maliyet) girebilirsiniz.
   - Portföyünüzdeki herhangi bir hisse **Kâr-Al Hedefine** ulaştığında, **Chandelier ATR Stop** seviyesini kırdığında veya stopa **%1,5 yaklaştığında** telefonunuz Türkçe sesli olarak konuşur (*"Dikkat! Portföyünüzdeki Tüpraş hissesi kâr al hedef fiyatına ulaştı..."*).
   - **`🎙️ Portföyümü Sesli Oku`** ve **`🔊 İlk 5 Öneriyi Sesli Dinle`** butonlarıyla istediğiniz an tek dokunuşla sesli brifing alabilirsiniz.
3. **☁️ GitHub Pages & GitHub Actions Bulut Tarama:**
   - [`.github/workflows/bist_canli_tarama.yml`](.github/workflows/bist_canli_tarama.yml) dosyası sayesinde proje GitHub'a yüklendiğinde, GitHub sunucuları hafta içi seans saatlerinde her 15 dakikada bir BIST verilerini otomatik günceller.

---

## 📲 GitHub'a Yükleme ve Telefonda Kurulum (3 Adım)

1. GitHub'da yeni bir depo (repository) açın (Örn: `bist-hibrit-pwa`).
2. Klasördeki **`GITHUB_YUKLE.bat`** dosyasına çift tıklayın ve GitHub depo adresinizi yapıştırın.
3. GitHub deponuzda **Settings $\rightarrow$ Pages $\rightarrow$ Source: Deploy from a branch $\rightarrow$ Branch: `main` / `/ (root)` $\rightarrow$ Save** seçin.
4. Telefonunuzdan `https://<kullanici-adiniz>.github.io/<depo-adi>/` adresini açıp **"📲 PWA Kur / Ana Ekrana Ekle"** ve **"📱 Kendi Portföyümü Gir"** butonuna dokunun!
