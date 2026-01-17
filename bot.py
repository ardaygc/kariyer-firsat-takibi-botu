import asyncio
from playwright.async_api import async_playwright
import json
import os
import requests

# GitHub Secrets üzerinden gelen değerler
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

SITELER = [
    {"isim": "Anbean", "url": "https://anbeankampus.co/ilanlar/", "card": ".job-item", "title": "h3", "date": ".date-info"},
    {"isim": "Coderspace", "url": "https://coderspace.io/etkinlikler", "card": ".event-card", "title": "h4", "date": ".event-date"},
    {"isim": "Youthall", "url": "https://www.youthall.com/tr/jobs/", "card": ".job-item", "title": ".job-item-title", "date": ".deadline"}
]

DB_FILE = "ilanlar_veritabani.json"

async def telegram_send(mesaj):
    if not mesaj: return
    print(f"📡 Telegram'a mesaj gönderiliyor: {mesaj[:50]}...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    response = requests.post(url, data={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"})
    print(f"📬 Telegram Yanıtı: {response.status_code} - {response.text}")

async def main():
    # --- 1. BAĞLANTI KONTROLÜ ---
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ HATA: TELEGRAM_TOKEN veya CHAT_ID bulunamadı! GitHub Secrets ayarlarını kontrol et.")
        return
    
    await telegram_send("🤖 Bot taramaya başladı, bağlantı başarılı!")

    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: arsiv = json.load(f)
    else: arsiv = {}

    yeni_ilanlar = []
    async with async_playwright() as p:
        print("🌐 Tarayıcı başlatılıyor...")
        browser = await p.chromium.launch(headless=True)
        
        for site in SITELER:
            page = await browser.new_page()
            try:
                print(f"🔎 {site['isim']} taranıyor: {site['url']}")
                await page.goto(site['url'], timeout=60000)
                await page.wait_for_timeout(5000) # Sayfanın yüklenmesi için 5 sn bekle
                
                cards = await page.query_selector_all(site['card'])
                print(f"📊 {site['isim']} sitesinde {len(cards)} adet ilan kartı bulundu.")
                
                for card in cards:
                    t_el = await card.query_selector(site['title'])
                    d_el = await card.query_selector(site['date'])
                    
                    title = (await t_el.inner_text()).strip() if t_el else "Başlık Yok"
                    date = (await d_el.inner_text()).strip() if d_el else "Belirsiz"
                    
                    key = f"{site['isim']}-{title}"
                    if key not in arsiv:
                        print(f"🆕 Yeni İlan: {title}")
                        yeni_ilanlar.append(f"📌 *{site['isim']}*\n📝 {title}\n⏳ {date}")
                        arsiv[key] = date
            except Exception as e:
                print(f"⚠️ {site['isim']} hatası: {e}")
            finally:
                await page.close()
        await browser.close()

    # --- 2. SONUÇLARI GÖNDERME ---
    if yeni_ilanlar:
        print(f"🚀 Toplam {len(yeni_ilanlar)} yeni ilan gönderiliyor.")
        await telegram_send("🚀 **YENİ FIRSATLAR!**\n\n" + "\n\n".join(yeni_ilanlar))
        with open(DB_FILE, "w") as f:
            json.dump(arsiv, f, indent=4)
    else:
        print("😴 Yeni bir ilan bulunamadı.")

if __name__ == "__main__":
    asyncio.run(main())
