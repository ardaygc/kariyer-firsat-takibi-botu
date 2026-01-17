import asyncio
from playwright.async_api import async_playwright
import json
import os
import requests

# GitHub Secrets üzerinden gelecek değerler
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

SITELER = [
    {"isim": "Anbean", "url": "https://anbeankampus.co/ilanlar/", "card": ".job-item", "title": "h3", "date": ".date"},
    {"isim": "Coderspace", "url": "https://coderspace.io/etkinlikler", "card": ".event-card", "title": "h4", "date": ".event-date"},
    {"isim": "Youthall", "url": "https://www.youthall.com/tr/jobs/", "card": ".job-item", "title": ".job-item-title", "date": ".deadline"}
]

DB_FILE = "ilanlar_veritabani.json"

async def telegram_send(mesaj):
    if not mesaj or not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"})

async def main():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: arsiv = json.load(f)
    else: arsiv = {}

    yeni_ilanlar = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for site in SITELER:
            page = await browser.new_page()
            try:
                await page.goto(site['url'], timeout=60000)
                await page.wait_for_timeout(3000)
                cards = await page.query_selector_all(site['card'])
                for card in cards:
                    t_el = await card.query_selector(site['title'])
                    d_el = await card.query_selector(site['date'])
                    title = (await t_el.inner_text()).strip() if t_el else "Başlık Yok"
                    date = (await d_el.inner_text()).strip() if d_el else "Belirsiz"
                    
                    key = f"{site['isim']}-{title}"
                    if key not in arsiv:
                        yeni_ilanlar.append(f"📌 *{site['isim']}*\n📝 {title}\n⏳ {date}")
                        arsiv[key] = date
            except Exception as e: print(f"{site['isim']} hatası: {e}")
            finally: await page.close()
        await browser.close()

    if yeni_ilanlar:
        await telegram_send("🚀 **YENİ FIRSATLAR!**\n\n" + "\n\n".join(yeni_ilanlar))
        with open(DB_FILE, "w") as f: json.dump(arsiv, f, indent=4)
        return True # Yeni veri var
    return False

if __name__ == "__main__":
    asyncio.run(main())
