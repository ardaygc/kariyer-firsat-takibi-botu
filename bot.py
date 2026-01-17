import asyncio
from playwright.async_api import async_playwright
import json
import os
import requests
from urllib.parse import urljoin
import re

# GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

SITELER = [
    {
        "isim": "Anbean", 
        "url": "https://anbeankampus.co/ilanlar/", 
        "card": ".joblistings-jobItem", 
        "title": "h6", 
        "link": "a",
        "deep_scrape": False # Tarih ana sayfada var
    },
    {
        "isim": "Coderspace", 
        "url": "https://coderspace.io/etkinlikler", 
        "card": ".event-card", 
        "title": "h5", 
        "link": "h5 a",
        "deep_scrape": False 
    },
    {
        "isim": "Youthall", 
        "url": "https://www.youthall.com/tr/jobs/", 
        "card": ".jobs", 
        "title": "h5", 
        "link": "a",
        "deep_scrape": False
    },
    {
        "isim": "Boomerang", 
        "url": "https://www.boomerang.careers/career-events", 
        "card": ".grid > div", 
        "title": "h3", 
        "link": "a[href*='/']",
        "deep_scrape": True # İçeri girip tarih araması yapacak
    }
]

DB_FILE = "ilanlar_veritabani.json"

async def get_deadline_from_page(page, url):
    """İlanın içine girip tarih arayan fonksiyon"""
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        content = await page.content()
        # Sayfa içinde tarih olabilecek kalıpları ara
        match = re.search(r'(\d{1,2}\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık))', content)
        return match.group(0) if match else "Detayda belirtilmiş"
    except:
        return "Belirtilmemiş"

async def telegram_send(mesaj):
    if not mesaj or not TELEGRAM_TOKEN: return
    clean_token = TELEGRAM_TOKEN.replace("bot", "")
    url = f"https://api.telegram.org/bot{clean_token}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown", "disable_web_page_preview": "true"})

async def main():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: arsiv = json.load(f)
    else: arsiv = {}

    yeni_ilanlar = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        for site in SITELER:
            page = await context.new_page()
            try:
                print(f"🔎 {site['isim']} taranıyor...")
                await page.goto(site['url'], wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(3000)
                
                cards = await page.query_selector_all(site['card'])
                
                for card in cards[:12]: # Hız için her siteden en güncel 12 ilanı alıyoruz
                    t_el = await card.query_selector(site['title'])
                    l_el = await card.query_selector(site['link'])
                    
                    title = (await t_el.inner_text()).strip() if t_el else ""
                    raw_link = await l_el.get_attribute("href") if l_el else ""
                    full_link = urljoin(site['url'], raw_link)
                    
                    if title and len(title) > 2:
                        key = f"{site['isim']}-{title}"
                        if key not in arsiv:
                            date = "İçeride aranıyor..."
                            if site['deep_scrape']:
                                # Derin tarama modu aktifse ilanın içine gir
                                date = await get_deadline_from_page(page, full_link)
                                await page.goto(site['url'], wait_until="networkidle") # Ana sayfaya geri dön
                            else:
                                # Normal modda ana sayfadaki tarih bilgisini çek
                                d_el = await card.query_selector("span[class*='date'], .date, .time")
                                date = (await d_el.inner_text()).strip() if d_el else "Belirtilmemiş"

                            detay = f"📌 *{site['isim']}*\n📝 *{title}*\n⏳ Son Başvuru: {date}\n🔗 [İlana Git]({full_link})"
                            yeni_ilanlar.append(detay)
                            arsiv[key] = date
            except Exception as e: print(f"⚠️ {site['isim']} Hatası: {e}")
            finally: await page.close()
        await browser.close()

    # --- TOPLU MESAJ MANTIĞI ---
    if yeni_ilanlar:
        mesaj_blogu = "🚀 **GÜNCEL FIRSATLAR LİSTESİ**\n\n"
        for ilan in yeni_ilanlar:
            # Eğer mevcut mesaj bloğu 4000 karaktere yaklaşırsa gönder ve yeni blok başlat
            if len(mesaj_blogu + ilan) > 3900:
                await telegram_send(mesaj_blogu)
                mesaj_blogu = "🚀 **LİSTE DEVAMI**\n\n"
            
            mesaj_blogu += ilan + "\n\n---\n\n"
        
        # Kalan son bloğu gönder
        await telegram_send(mesaj_blogu)
        
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(arsiv, f, indent=4, ensure_ascii=False)
    else:
        print("😴 Yeni ilan yok.")

if __name__ == "__main__":
    asyncio.run(main())
