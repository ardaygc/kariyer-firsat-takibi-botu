import asyncio
from playwright.async_api import async_playwright
import json
import os
import requests

# GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

# SİTELER VE ANALİZ EDİLMİŞ GÜNCEL SEÇİCİLER
SITELER = [
    {
        "isim": "Anbean", 
        "url": "https://anbeankampus.co/ilanlar/", 
        "card": ".joblistings-jobItem", 
        "title": "h6", 
        "date": ".mini-eventCard-dateItem"
    },
    {
        "isim": "Coderspace", 
        "url": "https://coderspace.io/etkinlikler", 
        "card": ".event-card", 
        "title": "h5", 
        "date": ".event-card-info"
    },
    {
        "isim": "Youthall", 
        "url": "https://www.youthall.com/tr/jobs/", 
        "card": ".jobs", 
        "title": "h5", 
        "date": ".jobs-content-bottom"
    },
    {
        "isim": "Boomerang", 
        "url": "https://www.boomerang.careers/career-events", 
        "card": ".grid > div", 
        "title": "h3", 
        "date": "p"
    }
]

DB_FILE = "ilanlar_veritabani.json"

async def telegram_send(mesaj):
    if not mesaj or not TELEGRAM_TOKEN:
        return
    clean_token = TELEGRAM_TOKEN.replace("bot", "")
    url = f"https://api.telegram.org/bot{clean_token}/sendMessage"
    try:
        response = requests.post(url, data={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}, timeout=10)
        print(f"📡 Telegram Durumu: {response.status_code}")
    except Exception as e:
        print(f"📡 Telegram hatası: {e}")

async def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ HATA: Token veya ID eksik!")
        return

    # Veritabanını oku
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            arsiv = json.load(f)
    else:
        arsiv = {}

    ilk_calisma = len(arsiv) == 0
    yeni_ilanlar = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Gerçek kullanıcı gibi davranmak için User-Agent ekliyoruz
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        for site in SITELER:
            page = await context.new_page()
            try:
                print(f"🔎 {site['isim']} taranıyor...")
                await page.goto(site['url'], wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(4000) # JS yüklenmesi için bekle
                
                # Sayfayı aşağı kaydır (Youthall gibi siteler için)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                await page.wait_for_timeout(2000)

                cards = await page.query_selector_all(site['card'])
                print(f"📊 {site['isim']}: {len(cards)} ilan bulundu.")
                
                for card in cards:
                    t_el = await card.query_selector(site['title'])
                    d_el = await card.query_selector(site['date'])
                    
                    title = (await t_el.inner_text()).strip() if t_el else ""
                    date = (await d_el.inner_text()).strip().replace("\n", " ") if d_el else "Bilgi yok"
                    
                    if title and len(title) > 2:
                        key = f"{site['isim']}-{title}"
                        if key not in arsiv:
                            yeni_ilanlar.append(f"📌 *{site['isim']}*\n📝 {title}\n⏳ {date}")
                            arsiv[key] = date
            except Exception as e:
                print(f"⚠️ {site['isim']} Hatası: {e}")
            finally:
                await page.close()
        await browser.close()

    # --- MESAJ GÖNDERME MANTIĞI ---
    if yeni_ilanlar:
        baslik = "✅ **AKTİF TÜM İLANLAR**" if ilk_calisma else "🔔 **YENİ İLANLAR BULUNDU!**"
        
        # Telegram mesaj sınırı nedeniyle 10'arlı gruplar halinde gönder
        for i in range(0, len(yeni_ilanlar), 10):
            grup = "\n\n".join(yeni_ilanlar[i:i+10])
            await telegram_send(f"{baslik}\n\n{grup}")
        
        # Veritabanını güncelle
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(arsiv, f, indent=4, ensure_ascii=False)
    else:
        print("😴 Yeni ilan bulunamadı.")

if __name__ == "__main__":
    asyncio.run(main())
