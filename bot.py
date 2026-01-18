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

client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

SITELER = [
    {"isim": "Anbean", "url": "https://anbeankampus.co/ilanlar/", "card": ".joblistings-jobItem", "title": "h6", "link": "a"},
    {"isim": "Coderspace", "url": "https://coderspace.io/etkinlikler", "card": ".event-card", "title": "h5", "link": "h5 a"},
    {"isim": "Youthall", "url": "https://www.youthall.com/tr/jobs/", "card": ".jobs", "title": "h5", "link": "a"},
    {"isim": "Boomerang", "url": "https://www.boomerang.careers/career-events", "card": ".grid > div", "title": "h3", "link": "a"}
]

DB_FILE = "ilanlar_veritabani.json"

def ai_analiz(metin):
    if not client or not metin: return "Analiz yapılamadı."
    try:
        prompt = f"Aşağıdaki kariyer ilanını analiz et. Son başvuru tarihi, uygun sınıflar ve kısa bir özeti Türkçe yaz: {metin[:2500]}"
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        return response.text if response.text else "AI özet üretemedi."
    except Exception as e:
        return f"AI Hatası: {str(e)[:50]}"

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
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        
        # --- KRİTİK GİZLİLİK ENJEKSİYONU ---
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', {get: () => ['tr-TR', 'tr', 'en-US', 'en']});
        """)

        for site in SITELER:
            page = await context.new_page()
            try:
                print(f"🔎 {site['isim']} taranıyor...")
                await page.goto(site['url'], wait_until="networkidle", timeout=60000)
                
                # Sayfayı yavaşça aşağı kaydır (Lazy load tetikleme)
                for _ in range(5):
                    await page.mouse.wheel(0, 400)
                    await asyncio.sleep(1)

                # Eleman beklerken timeout süresini uzattık
                try:
                    await page.wait_for_selector(site['card'], timeout=20000)
                except:
                    print(f"⚠️ {site['isim']} kartları bulunamadı. Alternatif bekleniyor...")
                    await page.wait_for_timeout(5000)

                cards = await page.query_selector_all(site['card'])
                print(f"📊 {site['isim']}: {len(cards)} ilan görüldü.")
                
                to_scan = []
                for card in cards[:5]: 
                    t_el = await card.query_selector(site['title'])
                    l_el = await card.query_selector(site['link'])
                    if t_el and l_el:
                        title = (await t_el.inner_text()).strip()
                        href = await l_el.get_attribute("href")
                        link = urljoin(site['url'], href)
                        if f"{site['isim']}-{title}" not in arsiv:
                            to_scan.append({"title": title, "link": link})

                for item in to_scan:
                    print(f"🧠 {item['title']} inceleniyor...")
                    await page.goto(item['link'], wait_until="domcontentloaded", timeout=40000)
                    await page.wait_for_timeout(3000)
                    full_text = await page.inner_text("body")
                    analiz_notu = ai_analiz(full_text)
                    
                    detay = f"📌 *{site['isim']}*\n📝 *{item['title']}*\n\n🤖 *AI ÖZETİ:*\n{analiz_notu}\n\n🔗 [İlana Git]({item['link']})"
                    yeni_ilanlar.append(detay)
                    arsiv[f"{site['isim']}-{item['title']}"] = "analiz_edildi"

            except Exception as e:
                print(f"⚠️ {site['isim']} Hatası: {str(e)[:50]}")
            finally:
                await page.close()
        
        await browser.close()

    if yeni_ilanlar:
        msg = "🚀 **GÜNCEL FIRSATLAR LİSTESİ**\n\n"
        for i in yeni_ilanlar:
            if len(msg + i) > 3900:
                await telegram_send(msg)
                msg = ""
            msg += i + "\n\n---\n\n"
        if msg: await telegram_send(msg)
        
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(arsiv, f, indent=4, ensure_ascii=False)
    else:
        print("😴 Yeni ilan yok.")

if __name__ == "__main__":
    asyncio.run(main())
