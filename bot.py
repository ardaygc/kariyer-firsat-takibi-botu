import asyncio
from playwright.async_api import async_playwright
import json
import os
import requests
from urllib.parse import urljoin
import google.generativeai as genai

# API ve Gizli Bilgiler
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Gemini Ayarı
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')

SITELER = [
    {
        "isim": "Anbean", 
        "url": "https://anbeankampus.co/ilanlar/", 
        "card": ".joblistings-jobItem", 
        "title": "h6", 
        "link": "a"
    },
    {
        "isim": "Coderspace", 
        "url": "https://coderspace.io/etkinlikler", 
        "card": ".event-card", 
        "title": "h5", 
        "link": "h5 a"
    },
    {
        "isim": "Youthall", 
        "url": "https://www.youthall.com/tr/jobs/", 
        "card": ".jobs", 
        "title": "h5", 
        "link": "a"
    },
    {
        "isim": "Boomerang", 
        "url": "https://www.boomerang.careers/career-events", 
        "card": "div.grid > div", 
        "title": "h3", 
        "link": "a"
    }
]

DB_FILE = "ilanlar_veritabani.json"

async def ai_ile_analiz_et(metin):
    """NLP kullanarak ilan metnini analiz eder"""
    if not GEMINI_KEY: return "NLP Analizi Devre Dışı (API Key Yok)"
    try:
        prompt = f"""
        Aşağıdaki iş/etkinlik ilanı metnini analiz et. 
        Sadece şu 3 bilgiyi kısa ve net olarak Türkçe ver:
        1. Son Başvuru Tarihi: (Bulamazsan 'Belirtilmemiş' yaz)
        2. Kimler Başvurabilir: (Sınıf ve bölüm kriteri)
        3. Özet: (Tek cümlelik görev tanımı)
        
        İlan Metni: {metin[:3000]}
        """
        response = ai_model.generate_content(prompt)
        return response.text
    except:
        return "NLP analizi sırasında hata oluştu."

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
        # Daha zengin bir User-Agent (Engellenmemek için)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        for site in SITELER:
            page = await context.new_page()
            try:
                print(f"🔎 {site['isim']} taranıyor...")
                await page.goto(site['url'], wait_until="networkidle", timeout=60000)
                
                # Dinamik içeriklerin yüklenmesi için scroll ve bekleme
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                await page.wait_for_timeout(5000) 

                cards = await page.query_selector_all(site['card'])
                print(f"📊 {site['isim']}: {len(cards)} ilan bulundu.")

                # Zaman aşımı riskine karşı her siteden en güncel 5 ilanı alıyoruz
                for card in cards[:5]:
                    t_el = await card.query_selector(site['title'])
                    l_el = await card.query_selector(site['link'])
                    
                    title = (await t_el.inner_text()).strip() if t_el else ""
                    raw_link = await l_el.get_attribute("href") if l_el else ""
                    full_link = urljoin(site['url'], raw_link)
                    
                    if title and len(title) > 2:
                        key = f"{site['isim']}-{title}"
                        if key not in arsiv:
                            print(f"🧠 {title} NLP ile analiz ediliyor...")
                            # İlanın içine girip tüm metni çek
                            await page.goto(full_link, wait_until="domcontentloaded")
                            full_text = await page.inner_text("body")
                            
                            # Gemini ile NLP analizi
                            ai_analiz = await ai_ile_analiz_et(full_text)
                            
                            detay = f"📌 *{site['isim']}*\n📝 *{title}*\n\n🤖 **AI ANALİZİ:**\n{ai_analiz}\n\n🔗 [Detay ve Başvuru İçin Tıkla]({full_link})"
                            yeni_ilanlar.append(detay)
                            arsiv[key] = "kaydedildi"
                            
                            # Geri dön
                            await page.goto(site['url'], wait_until="domcontentloaded")

            except Exception as e: print(f"⚠️ {site['isim']} Hatası: {e}")
            finally: await page.close()
        await browser.close()

    # Toplu mesaj gönderme (4000 karakter sınırı kontrolüyle)
    if yeni_ilanlar:
        mesaj_blogu = "🚀 **YAPAY ZEKA DESTEKLİ KARİYER RAPORU**\n\n"
        for ilan in yeni_ilanlar:
            if len(mesaj_blogu + ilan) > 3800:
                await telegram_send(mesaj_blogu)
                mesaj_blogu = "🚀 **LİSTE DEVAMI**\n\n"
            mesaj_blogu += ilan + "\n\n---\n\n"
        await telegram_send(mesaj_blogu)
        
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(arsiv, f, indent=4, ensure_ascii=False)
    else: print("😴 Yeni bir şey yok.")

if __name__ == "__main__":
    asyncio.run(main())
