# 🤖 Universal Media & AI Chat Telegram Bot

Ushbu bot ko'p funksiyali bo'lib, quyidagi barcha imkoniyatlarni o'zida jamlagan:

---

## 🚀 Asosiy Imkoniyatlar:

1. **💬 Sun'iy Intellekt (AI Chat):**
   - Istalgan savolga (ilm-fan, texnologiya, dasturlash, maslahat, chet tillari va h.k.) o'zbek tilida batafsil va tezkor javob beradi.
   - Suhbat tarixini eslab qoladi va muloqotni davom ettiradi.
   - `🧹 Suhbatni tozalash` va `❌ AI Chatdan chiqish` tugmalari mavjud.
2. **📥 Instagram Video Downloader:**
   - Reels, post videolar va IGTV havolalarini qabul qiladi va yuqori sifatda yuklab beradi.
3. **📥 YouTube Video & Shorts Downloader:**
   - YouTube Shorts va oddiy videolarni 50MB gacha avtomatik sifatli yuklab beradi.
4. **🔄 To'rtburchak video ➡️ Dumaloq video (Krujok):**
   - Istalgan oddiy videoni Telegramning 1:1 kvadrat dumaloq video xabari formatiga aylantirib beradi.
5. **🔄 Dumaloq video (Krujok) ➡️ To'rtburchak video:**
   - Krujok videoni galereyaga saqlanadigan, to'xtatib ko'rish mumkin bo'lgan oddiy video formatiga o'tkazib beradi.

---

## 🛠 O'rnatish va Ishga Tushirish

### 1. Kutubxonalarni o'rnatish

```bash
pip install -r requirements.txt
```

### 2. Telegram Bot Tokenini sozlash

Loyiha papkasidagi `.env` fayliga @BotFather dan olingan tokenni kiriting:

```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Botni mahalliy ishga tushirish (sinov uchun)

```bash
python bot.py
```

---

## ☁️ Render.com da 24/7 (Kompyuter o'chiq holatda ham) Ishlatish

Botni faqat **Render.com** serverida kompyuteringiz o'chiq bo'lsa ham uzluksiz ishlashini ta'minlash:

### 1. GitHub-ga yuklash:
O'zgarishlarni GitHub-ga yuboring (`git push origin main`).

### 2. Render.com da sozlash:
1. [Render.com](https://render.com) ga kiring va **New +** ➡️ **Web Service** ni tanlang.
2. O'zingizning GitHub dagi `instagram-bot` repozitoriyangizni ulang.
3. Sozlamalarni tekshiring:
   - **Name**: `instagram-bot`
   - **Region**: Frankfurt (yoki yaqin hudud)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Instance Type**: `Free`
4. **Environment Variables** bo'limiga `.env` dagi qiymatlarni qo'shing:
   - `BOT_TOKEN`: Sizning @BotFather dan olingan haqiqiy tokeningiz
   - `GEMINI_API_KEY`: Sizning Google Gemini API kalitingiz
5. **Create Web Service** tugmasini bosing.

### 3. 24/7 Uxlab qolmasligini ta'minlash (Keep-Alive):
Render bepul tarifi 15 daqiqa so'rov bo'lmasa xizmatni to'xtatib qo'yadi. Bot kodida buni oldini oluvchi avtomatik keep-alive tizimi mavjud (`RENDER_EXTERNAL_URL`).

Kafolatlangan 100% uzluksiz ishlashi uchun:
- Render bergan havolani oling (masalan: `https://instagram-bot-xxxx.onrender.com/health`)
- [Cron-job.org](https://cron-job.org) yoki [UptimeRobot.com](https://uptimerobot.com) bepul saytiga kirib, shu havolaga har 5-10 daqiqada bitta GET so'rov yuborishni sozlab qo'ying.

> **Muhim eslatma:** Render'da bot ishga tushgandan so'ng, o'z kompyuteringizdagi `python bot.py` ni to'xtating (yopib qo'ying). Bitta token bir vaqtning o'zida ikkita joyda ishlasa ziddiyat (Conflict) yuzaga keladi.
