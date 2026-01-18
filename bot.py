import asyncio
from playwright.async_api import async_playwright
import json
import os
import requests
from urllib.parse import urljoin
from google import genai

# API Bilgileri
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Gemini SDK Yapılandırması
client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

SITELER = [
    {"isim": "Anbean", "url": "https://anbeankampus.co/ilanlar/", "card": ".joblistings-jobItem", "title": "h6", "link": "a"},
    {"isim": "Coderspace", "url": "https://coderspace.io/etkinlikler", "card": ".event-card", "title": "h5", "link": "h5 a"},
    {"isim": "Youthall", "url": "https://www.youthall.com/tr/jobs/", "card": ".jobs", "title": "h5", "link": "a"},
    {"isim": "Boomerang", "url": "https://www.boomerang.careers/career-events", "card": "div.grid > div", "title": "h3", "link": "a"}
]

DB_FILE = "ilanlar_veritabani.json"

async def ai_analiz(metin):
    """NLP Analizi - 404 Hatasını Önleyen Yapı"""
    if not client: return "⚠️ AI API Anahtarı eksik!"
    try:
        # Model ismini 'models/' ön ekiyle deneyelim (404 çözüm yolu)
        prompt = f"Aşağıdaki iş ilanını analiz et. Son başvuru tarihini ve uygun sınıfları kısa yaz: {metin[:2000]}"
        response = client.models.generate_content(
            model="gemini-1.5-flash", # Eğer yine 404 verirse "models/gemini-1.5-flash" yap
            contents=prompt
        )
        return response.text if response.text else "Özet çıkarılamadı."
    except Exception as e:
        print(f"❌ AI Analiz Hatası: {e}")
        return "İlan detayları linkte mevcut."

async def telegram_send(mesaj):
    if not mesaj: return
    clean_token = TELEGRAM_TOKEN.replace("bot", "")
    url = f"https://api.telegram.org/bot{clean_token}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown", "disable_web_page_preview": "true"})

async def main():
    # JSON Okuma Hatasını Önle (Daha önce konuştuğumuz düzeltme)
    arsiv = {}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content: arsiv = json.loads(content)
        except: arsiv = {}

    yeni_ilanlar = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        # --- TEST FOTOĞRAFI ---
        test_page = await context.new_page()
        await test_page.goto("https://www.google.com")
        await test_page.screenshot(path="system_test.png") # Artifact'ın çalıştığını kanıtlayacak
        await test_page.close()

        for site in SITELER:
            page = await context.new_page()
            try:
                print(f"🔎 {site['isim']} taranıyor...")
                await page.goto(site['url'], wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)

                # Kartları bekle
                try:
                    await page.wait_for_selector(site['card'], timeout=15000)
                except:
                    print(f"📸 {site['isim']} bulunamadı, fotoğraf çekiliyor...")
                    await page.screenshot(path=f"error_{site['isim']}.png")
                    continue

                cards = await page.query_selector_all(site['card'])
                for card in cards[:3]:
                    t_el = await card.query_selector(site['title'])
                    l_el = await card.query_selector(site['link'])
                    if t_el and l_el:
                        title = (await t_el.inner_text()).strip()
                        link = urljoin(site['url'], await l_el.get_attribute("href"))
                        if f"{site['isim']}-{title}" not in arsiv:
                            await page.goto(link, wait_until="domcontentloaded")
                            full_text = await page.inner_text("body")
                            analiz = await ai_analiz(full_text)
                            
                            detay = f"📌 *{site['isim']}*\n📝 *{title}*\n\n🤖 *AI ANALİZİ:*\n{analiz}\n\n🔗 [İlana Git]({link})"
                            yeni_ilanlar.append(detay)
                            arsiv[f"{site['isim']}-{title}"] = "ok"
                            await page.goto(site['url'], wait_until="domcontentloaded")

            except Exception as e: print(f"⚠️ {site['isim']} Hatası: {e}")
            finally: await page.close()
        
        await browser.close()

    if yeni_ilanlar:
        msg = "🚀 **GÜNCEL FIRSATLAR**\n\n"
        for i in yeni_ilanlar:
            if len(msg + i) > 3900:
                await telegram_send(msg); msg = ""
            msg += i + "\n\n---\n\n"
        if msg: await telegram_send(msg)
        
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(arsiv, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    asyncio.run(main())
