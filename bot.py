import asyncio
from playwright.async_api import async_playwright
import json
import os
import requests
from urllib.parse import urljoin
import google.generativeai as genai

# API Bilgileri
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Gemini AI Yapılandırması (Daha stabil olan gemini-pro modeline geçildi)
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    ai_model = genai.GenerativeModel('gemini-pro')

SITELER = [
    {"isim": "Anbean", "url": "https://anbeankampus.co/ilanlar/", "card": ".joblistings-jobItem", "title": "h6", "link": "a"},
    {"isim": "Coderspace", "url": "https://coderspace.io/etkinlikler", "card": ".event-card", "title": "h5", "link": "h5 a"},
    {"isim": "Youthall", "url": "https://www.youthall.com/tr/jobs/", "card": ".jobs", "title": "h5", "link": "a"},
    {"isim": "Boomerang", "url": "https://www.boomerang.careers/career-events", "card": ".grid > div", "title": "h3", "link": "a"}
]

DB_FILE = "ilanlar_veritabani.json"

async def ai_analiz(text):
    if not GEMINI_KEY or not text: return "Analiz yapılamadı."
    try:
        # Prompt sadeleştirildi
        prompt = f"İş ilanı metnini analiz et. Son başvuru tarihi, uygun sınıflar ve kısa özeti Türkçe yaz: {text[:2000]}"
        response = ai_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Hatası: Model henüz hazır değil veya kısıtlı."

async def telegram_send(mesaj):
    if not mesaj: return
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
        # Gerçek bir tarayıcı gibi davranmak kritik
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        
        for site in SITELER:
            page = await context.new_page()
            try:
                print(f"🔎 {site['isim']} taranıyor...")
                await page.goto(site['url'], wait_until="load", timeout=90000)
                
                # SİTEYE ÖZEL BEKLEME: Kartlar görünene kadar bekle
                try:
                    await page.wait_for_selector(site['card'], timeout=20000)
                except:
                    print(f"⚠️ {site['isim']} kartları zamanında yüklenemedi.")
                
                await page.wait_for_timeout(3000) # Ekstra nefes alma payı

                cards = await page.query_selector_all(site['card'])
                print(f"📊 {site['isim']}: {len(cards)} ilan bulundu.")
                
                task_list = []
                for card in cards[:5]: # Her siteden en güncel 5 ilan
                    t_el = await card.query_selector(site['title'])
                    l_el = await card.query_selector(site['link'])
                    if t_el and l_el:
                        title = (await t_el.inner_text()).strip()
                        link = urljoin(site['url'], await l_el.get_attribute("href"))
                        if f"{site['isim']}-{title}" not in arsiv:
                            task_list.append({"title": title, "link": link})

                for task in task_list:
                    print(f"🧠 {task['title']} analiz ediliyor...")
                    try:
                        await page.goto(task['link'], wait_until="domcontentloaded", timeout=40000)
                        await page.wait_for_timeout(2000)
                        full_text = await page.inner_text("body")
                        analiz_notu = await ai_analiz(full_text)
                        
                        detay = f"📌 *{site['isim']}*\n📝 *{task['title']}*\n\n🤖 *AI ÖZETİ:*\n{analiz_notu}\n\n🔗 [İlana Git]({task['link']})"
                        yeni_ilanlar.append(detay)
                        arsiv[f"{site['isim']}-{task['title']}"] = "kaydedildi"
                    except: continue

            except Exception as e:
                print(f"⚠️ {site['isim']} Hatası: {e}")
            finally:
                await page.close()
        
        await browser.close()

    if yeni_ilanlar:
        msg = "🚀 **YAPAY ZEKA ANALİZLİ İLANLAR**\n\n"
        for i in yeni_ilanlar:
            if len(msg + i) > 3900:
                await telegram_send(msg)
                msg = "🚀 **DEVAMI...**\n\n"
            msg += i + "\n\n---\n\n"
        await telegram_send(msg)
        
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(arsiv, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    asyncio.run(main())
