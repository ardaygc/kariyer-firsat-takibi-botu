import asyncio
from playwright.async_api import async_playwright
import json
import os
import requests
from urllib.parse import urljoin
from google import genai

# API ve Gizli Bilgiler
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Gemini SDK Yapılandırması
client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

SITELER = [
    {"isim": "Anbean", "url": "https://anbeankampus.co/ilanlar/", "card": ".joblistings-jobItem", "title": "h6", "link": "a"},
    {"isim": "Coderspace", "url": "https://coderspace.io/etkinlikler", "card": ".event-card", "title": "h5", "link": "h5 a"},
    {"isim": "Youthall", "url": "https://www.youthall.com/tr/jobs/", "card": ".jobs", "title": "h5", "link": "a"},
    {"isim": "Boomerang", "url": "https://www.boomerang.careers/career-events", "card": "div.grid > div:has(h3)", "title": "h3", "link": "a"}
]

DB_FILE = "ilanlar_veritabani.json"

def ai_analiz(metin):
    """NLP kullanarak ilan metnini analiz eder"""
    if not client or not metin: return "Analiz yapılamadı."
    try:
        # En stabil model ismi kullanıldı
        prompt = f"""
        Aşağıdaki iş/etkinlik ilanı metnini analiz et. 
        Sadece şu 3 bilgiyi kısa ve net olarak Türkçe ver:
        1. Son Başvuru Tarihi: (Metinden bul, yoksa 'Belirtilmemiş' yaz)
        2. Kimler Başvurabilir: (Sınıf veya bölüm kriteri)
        3. Öne Çıkan Şartlar: (Maksimum 2 madde)
        
        Metin: {metin[:3000]}
        """
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        return response.text if response.text else "AI özet üretemedi."
    except Exception as e:
        return f"AI Hatası: {str(e)[:50]}"

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
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        for site in SITELER:
            page = await context.new_page()
            try:
                print(f"🔎 {site['isim']} taranıyor...")
                await page.goto(site['url'], wait_until="domcontentloaded", timeout=60000)
                
                # Sitenin yüklenmesini bekle (JS tabanlı siteler için kritik)
                try:
                    await page.wait_for_selector(site['card'], timeout=15000)
                except:
                    print(f"⚠️ {site['isim']} için ilan kartları bulunamadı (Zaman aşımı).")

                # Sayfayı kaydır
                await page.evaluate("window.scrollTo(0, 800)")
                await page.wait_for_timeout(2000)

                cards = await page.query_selector_all(site['card'])
                
                # Hafıza hatasını önlemek için önce linkleri toplayalım
                to_scan = []
                for card in cards[:5]: # Her siteden en güncel 5 ilan
                    t_el = await card.query_selector(site['title'])
                    l_el = await card.query_selector(site['link'])
                    if t_el and l_el:
                        title = (await t_el.inner_text()).strip()
                        link = urljoin(site['url'], await l_el.get_attribute("href"))
                        if f"{site['isim']}-{title}" not in arsiv:
                            to_scan.append({"title": title, "link": link})

                # Şimdi toplanan linklerin içine tek tek girip AI ile analiz edelim
                for item in to_scan:
                    print(f"🧠 {item['title']} analiz ediliyor...")
                    await page.goto(item['link'], wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(2000)
                    
                    full_text = await page.inner_text("body")
                    analiz_notu = ai_analiz(full_text)
                    
                    detay = f"📌 *{site['isim']}*\n📝 *{item['title']}*\n\n🤖 **AI ANALİZİ:**\n{analiz_notu}\n\n🔗 [İlana Gitmek İçin Tıkla]({item['link']})"
                    yeni_ilanlar.append(detay)
                    arsiv[f"{site['isim']}-{item['title']}"] = "analiz_edildi"

            except Exception as e:
                print(f"⚠️ {site['isim']} Genel Hatası: {e}")
            finally:
                await page.close()
        
        await browser.close()

    if yeni_ilanlar:
        mesaj_blogu = "🚀 **YAPAY ZEKA DESTEKLİ KARİYER LİSTESİ**\n\n"
        for ilan in yeni_ilanlar:
            if len(mesaj_blogu + ilan) > 3800:
                await telegram_send(mesaj_blogu)
                mesaj_blogu = "🚀 **LİSTE DEVAMI**\n\n"
            mesaj_blogu += ilan + "\n\n---\n\n"
        await telegram_send(mesaj_blogu)
        
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(arsiv, f, indent=4, ensure_ascii=False)
    else:
        print("😴 Yeni ilan yok.")

if __name__ == "__main__":
    asyncio.run(main())
