import os
import re
import sys
import uuid
import logging
import asyncio
import subprocess
from pathlib import Path

# Konsol va loglarda chiqishlarni zudlik bilan ko'rsatish (buffer to'lib qolmasligi uchun)
try:
    sys.stdout.reconfigure(line_buffering=True, encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(line_buffering=True, encoding='utf-8', errors='replace')
except Exception:
    pass


from dotenv import load_dotenv
import yt_dlp

import urllib.parse
import aiohttp
from aiohttp import web

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

# .env faylini yuklash
load_dotenv()

# Konfiguratsiya
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Logging sozlamalari
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Havolalarni aniqlash uchun Regex
INSTAGRAM_URL_REGEX = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|reels|tv|share)/[A-Za-z0-9_\-]+/?(?:\?[^\s]*)?",
    re.IGNORECASE
)

YOUTUBE_URL_REGEX = re.compile(
    r"https?://(?:(?:www\.|m\.)?youtube\.com/(?:watch\?v=[A-Za-z0-9_\-]+|shorts/[A-Za-z0-9_\-]+|live/[A-Za-z0-9_\-]+|embed/[A-Za-z0-9_\-]+)|youtu\.be/[A-Za-z0-9_\-]+)[^\s]*",
    re.IGNORECASE
)

# Telegram bot limiti (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024


def detect_platform(text: str) -> tuple[str | None, str | None]:
    """
    Xabardan Instagram yoki YouTube havolasini ajratib oladi.
    """
    if match := INSTAGRAM_URL_REGEX.search(text):
        return "Instagram", match.group(0)
    if match := YOUTUBE_URL_REGEX.search(text):
        return "YouTube", match.group(0)
    return None, None


def download_video_sync(url: str, platform: str = "Video") -> dict:
    """
    yt-dlp yordamida Instagram yoki YouTube videosini yuklab oluvchi sinxron funksiya.
    """
    unique_id = str(uuid.uuid4())[:8]
    output_template = str(DOWNLOAD_DIR / f"{unique_id}_%(id)s.%(ext)s")

    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg_exe = None

    cookie_file = Path("cookies.txt")
    # Agar Render yoki serverda YOUTUBE_COOKIES muhit o'zgaruvchisi berilgan bo'lsa
    youtube_cookies_env = os.getenv("YOUTUBE_COOKIES")
    if youtube_cookies_env and not cookie_file.exists():
        try:
            cookie_file.write_text(youtube_cookies_env.strip(), encoding="utf-8")
            logger.info("YOUTUBE_COOKIES o'zgaruvchisidan cookies.txt fayli yaratildi.")
        except Exception as e:
            logger.warning(f"cookies.txt yaratishda xatolik: {e}")
    elif not cookie_file.exists():
        # Serverda qo'shimcha sozlarsiz avtomatik ishlashi uchun tayyor cookies
        try:
            default_cookies = (
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1808543082\tVISITOR_INFO1_LIVE\t_LZuymERYH8\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1808543082\tVISITOR_PRIVACY_METADATA\tCgJVWhIEGgAgVw%3D%3D\n"
                ".youtube.com\tTRUE\t/\tTRUE\t0\tYSC\tN9S3ehat9l4\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1808542855\t__Secure-ROLLOUT_TOKEN\tCNniw7D6kuqJQhDfvOupqKSSAxjPlKe489aXAw%3D%3D\n"
                ".youtube.com\tTRUE\t/\tFALSE\t0\tPREF\thl=en&tz=UTC\n"
                ".youtube.com\tTRUE\t/\tTRUE\t0\tSOCS\tCAI\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1792992655\tGPS\t1\n"
            )
            cookie_file.write_text(default_cookies, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Zaxira cookies yaratishda xatolik: {e}")

    # YouTube uchun 50MB limitga mos keladigan formatni tanlash
    if platform == "YouTube":
        video_format = (
            'bestvideo[filesize<?45M][ext=mp4]+bestaudio[ext=m4a]/'
            'bestvideo[filesize<?45M]+bestaudio/'
            'bestvideo[height<=720]+bestaudio/'
            'best[filesize<?48M]/'
            'best[height<=720]/'
            '18/'
            'best'
        )
        ydl_opts = {
            'format': video_format,
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'merge_output_format': 'mp4',
            'max_filesize': MAX_FILE_SIZE,
            'source_address': '0.0.0.0',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'tv_downgraded', 'mweb'],
                    'player_skip': ['web', 'configs'],
                }
            }
        }
    else:
        video_format = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
        ydl_opts = {
            'format': video_format,
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'merge_output_format': 'mp4',
            'max_filesize': MAX_FILE_SIZE,
            'source_address': '0.0.0.0',
            'http_headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/124.0.0.0 Safari/537.36'
                ),
            }
        }

    if ffmpeg_exe:
        ydl_opts['ffmpeg_location'] = ffmpeg_exe

    if cookie_file.exists():
        ydl_opts['cookiefile'] = str(cookie_file)

    def _extract_and_download(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            res = ydl.extract_info(url, download=True)
            if not res:
                raise ValueError("Ma'lumot olinmadi.")
            if 'entries' in res and res['entries']:
                res = res['entries'][0]
            filename = ydl.prepare_filename(res)
            return res, filename

    try:
        info, filename = _extract_and_download(ydl_opts)
    except Exception as first_err:
        # Agar maxsus YouTube sozlamalari xatolik bersa, zaxira (fallback) bilan qayta urinish
        if platform == "YouTube":
            logger.warning(f"Birlamchi YouTube mijozlari xatolik berdi ({first_err}), zaxira bilan urinilmoqda...")
            fallback_opts = dict(ydl_opts)
            fallback_opts['format'] = '18/best'
            try:
                info, filename = _extract_and_download(fallback_opts)
            except Exception:
                fallback_opts2 = dict(ydl_opts)
                fallback_opts2.pop('extractor_args', None)
                info, filename = _extract_and_download(fallback_opts2)
        else:
            raise first_err

    # Fayl nomini aniqlash
    base, _ = os.path.splitext(filename)
    mp4_path = f"{base}.mp4"

    if os.path.exists(mp4_path):
        final_path = mp4_path
    elif os.path.exists(filename):
        final_path = filename
    else:
        matches = list(DOWNLOAD_DIR.glob(f"{unique_id}_*"))
        if matches:
            final_path = str(matches[0])
        else:
            raise FileNotFoundError("Yuklangan video fayli topilmadi.")

    title = info.get('title') or f"{platform} Video"
    if len(title) > 80:
        title = title[:77] + "..."

    return {
        'filepath': final_path,
        'title': title,
        'duration': info.get('duration') or 0,
        'width': info.get('width'),
        'height': info.get('height')
    }


async def download_video(url: str, platform: str = "Video") -> dict:
    """
    Event loopni bloklamaslik uchun yuklab olishni alohida thread'da bajarish.
    """
    return await asyncio.to_thread(download_video_sync, url, platform)


def convert_to_video_note_sync(input_path: str, output_path: str) -> None:
    """
    To'rtburchak videoni Telegram dumaloq video (krujok / video note) formatiga
    (1:1 kvadrat, 480x480, maksimal 60 soniya) aylantiradi.
    """
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg_exe = "ffmpeg"

    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", input_path,
        "-t", "60",  # Telegram dumaloq video limiti 60 soniya
        "-vf", "crop=min(iw\\,ih):min(iw\\,ih),scale=480:480",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-preset", "fast",
        "-movflags", "+faststart",
        output_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error(f"FFmpeg xatoligi: {res.stderr}")
        raise RuntimeError(f"FFmpeg xatosi: {res.stderr}")


class AIChatState(StatesGroup):
    chatting = State()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Asosiy menyu klaviaturasi.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💬 AI Chat"), KeyboardButton(text="📥 Video yuklash")],
            [KeyboardButton(text="🔄 Dumaloq video"), KeyboardButton(text="ℹ️ Yordam")]
        ],
        resize_keyboard=True
    )


def get_ai_chat_keyboard() -> ReplyKeyboardMarkup:
    """
    AI Chat rejimi uchun klaviatura.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧹 Suhbatni tozalash")],
            [KeyboardButton(text="❌ AI Chatdan chiqish")]
        ],
        resize_keyboard=True
    )


def split_text(text: str, max_length: int = 4000) -> list[str]:
    """
    Uzun javoblarni Telegram limiti (4096 belgi) bo'yicha bo'laklarga ajratish.
    """
    chunks = []
    while len(text) > max_length:
        split_idx = text.rfind('\n', 0, max_length)
        if split_idx == -1:
            split_idx = max_length
        chunks.append(text[:split_idx].strip())
        text = text[split_idx:].strip()
    if text:
        chunks.append(text)
    return chunks


async def query_gemini(prompt: str, api_key: str) -> str:
    """
    Google Gemini API orqali javob olish.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": f"{prompt}\nIltimos, o'zbek tilida aniq va tushunarli javob ber."}]}]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            raise RuntimeError(f"Gemini API xatolik kodi: {resp.status}")


async def ask_ai_async(prompt: str, context: str = "") -> str:
    """
    Sun'iy intellektga (AI) so'rov yuborish:
    1. Avval Gemini API orqali tekshiradi (agar kalit kiritilgan bo'lsa).
    2. Agar tarmoq yoki boshqa sabab bilan xatolik bo'lsa, zaxira AI orqali javob beradi.
    """
    clean_prompt = prompt.replace("\n", " ").strip()
    full_prompt = f"{context.strip()}. Hozirgi savol: {clean_prompt}" if context else clean_prompt

    # 1. Google Gemini orqali urinish
    if GEMINI_API_KEY:
        try:
            gemini_ans = await query_gemini(full_prompt, GEMINI_API_KEY)
            if gemini_ans:
                return gemini_ans
        except Exception as err:
            logger.info(f"Gemini javob bermadi ({err}), zaxira AI tizimiga o'tilmoqda...")

    # 2. Zaxira AI orqali urinish
    encoded = urllib.parse.quote(f"Savol: {full_prompt}. Iltimos, o'zbek tilida aniq va batafsil javob ber.")
    url = f"https://text.pollinations.ai/{encoded}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    return text.strip() or "Kechirasiz, javob olishda xatolik yuz berdi."
                else:
                    return "Kechirasiz, sun'iy intellekt xizmati vaqtincha band. Birozdan so'ng qayta urinib ko'ring."
    except asyncio.TimeoutError:
        return "⚠️ Sun'iy intellekt javob berish vaqti tugadi (Timeout). Iltimos, savolingizni qisqaroq qilib qayta yuboring."
    except Exception as e:
        logger.error(f"AI so'rovida xatolik: {e}")
        return "❌ Kechirasiz, AI bilan bog'lanishda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring."


# Bot va Dispatcher yaratish
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    """
    /start komandasi uchun handler.
    """
    await state.clear()
    text = (
        f"Assalomu alaykum, <b>{message.from_user.full_name}</b>! 🎬🤖\n\n"
        "Men universal media va <b>Sun'iy Intellekt (AI)</b> botman! Imkoniyatlarim:\n\n"
        "1️⃣ <b>💬 AI Chat</b> — istalgan savolingizga javob beruvchi aqlli suhbatdosh.\n"
        "2️⃣ <b>📥 Video yuklash</b> — Instagram va YouTube havolasini yuborsangiz, videoni yuklab beraman.\n"
        "3️⃣ <b>🔄 Dumaloq video</b> — oddiy to'rtburchak videoni dumaloq (krujok) formatga va aksincha aylantiraman!\n\n"
        "Quyidagi menyu tugmalaridan birini tanlang yoki to'g'ridan-to'g'ri video/havola yuboring! 🚀"
    )
    await message.answer(text, reply_markup=get_main_keyboard())


@dp.message(Command("help"))
@dp.message(F.text == "ℹ️ Yordam")
async def cmd_help(message: types.Message):
    """
    /help komandasi uchun handler.
    """
    text = (
        "📖 <b>Botdan foydalanish yo'riqnomasi:</b>\n\n"
        "• <b>💬 AI Chat:</b> Tugmani bosing va istalgan savolingizni bering (dasturlash, fan, tarjima, maslahat va h.k.).\n"
        "• <b>📥 Instagram & YouTube yuklash:</b> Video, Reels yoki Shorts havolasini yuboring.\n"
        "• <b>🔄 To'rtburchak videoni dumaloq qilish:</b> Oddiy video yuboring, bot uni krujok qilib beradi.\n"
        "• <b>🔄 Dumaloq videoni oddiy video qilish:</b> Krujok video yuboring, bot uni galereyaga saqlanadigan oddiy video qilib beradi.\n\n"
        "⚠️ <i>Telegram orqali maksimal 50MB gacha bo'lgan fayllarni qayta ishlash mumkin.</i>"
    )
    await message.answer(text, reply_markup=get_main_keyboard())


@dp.message(Command("ai"))
@dp.message(F.text == "💬 AI Chat")
async def enter_ai_chat(message: types.Message, state: FSMContext):
    """
    AI Chat rejimiga o'tish.
    """
    await state.set_state(AIChatState.chatting)
    await state.update_data(history="")
    text = (
        "🤖 <b>AI Suhbatdosh rejimiga xush kelibsiz!</b>\n\n"
        "Endi menga istalgan savolingizni yuborishingiz mumkin. "
        "Men sizga barcha sohalarda (ilm-fan, texnologiya, dasturlash, maslahat, chet tillari) yordam beraman.\n\n"
        "<i>Chiqish uchun pastdagi «❌ AI Chatdan chiqish» tugmasini bosing yoki /exit deb yozing.</i>"
    )
    await message.answer(text, reply_markup=get_ai_chat_keyboard())


@dp.message(F.text == "❌ AI Chatdan chiqish")
@dp.message(Command("exit"))
@dp.message(Command("stop"))
async def exit_ai_chat(message: types.Message, state: FSMContext):
    """
    AI Chat rejimidan chiqish.
    """
    await state.clear()
    await message.answer(
        "✅ <b>AI suhbat rejimidan chiqdingiz.</b> Asosiy menyudasiz.",
        reply_markup=get_main_keyboard()
    )


@dp.message(F.text == "🧹 Suhbatni tozalash")
async def clear_ai_history(message: types.Message, state: FSMContext):
    """
    AI suhbat tarixini tozalash.
    """
    await state.update_data(history="")
    await message.answer(
        "🧹 <b>Suhbat tarixi tozalandi!</b> Yangi mavzuda savol berishingiz mumkin.",
        reply_markup=get_ai_chat_keyboard()
    )


@dp.message(F.text == "📥 Video yuklash")
async def info_video_download(message: types.Message):
    await message.answer(
        "📥 <b>Video yuklash bo'limi:</b>\n\n"
        "Instagram (Reels/post) yoki YouTube (Shorts/video) havolasini nusxalang va botga yuboring.\n"
        "Bot uni darhol video formatida yuklab beradi! 🚀",
        reply_markup=get_main_keyboard()
    )


@dp.message(F.text == "🔄 Dumaloq video")
async def info_round_video(message: types.Message):
    await message.answer(
        "🔄 <b>Video formatini o'zgartirish:</b>\n\n"
        "• Oddiy to'rtburchak video yuborsangiz ➡️ <b>Dumaloq (krujok)</b> qilib beraman.\n"
        "• Dumaloq video (krujok) yuborsangiz ➡️ <b>Oddiy to'rtburchak video</b> qilib beraman.\n\n"
        "Sinab ko'rish uchun hoziroq video yuboring! 🎥",
        reply_markup=get_main_keyboard()
    )


@dp.message(AIChatState.chatting, F.text)
async def handle_ai_chat_message(message: types.Message, state: FSMContext, bot: Bot):
    """
    AI Chat rejimidagi savollarga javob berish.
    """
    # Agar foydalanuvchi Instagram yoki YouTube havolasi yuborgan bo'lsa, videoni yuklab berish
    platform, url = detect_platform(message.text)
    if platform:
        await handle_message(message, bot)
        return

    # Typing holatini ko'rsatish
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    # Foydalanuvchi ma'lumotlari va tarixi
    data = await state.get_data()
    history = data.get("history", "")

    # AI ga so'rov yuborish
    ai_response = await ask_ai_async(prompt=message.text, context=history)

    # Suhbat tarixini qisqacha yangilab borish
    new_history = f"Savol: {message.text[:80]}. Javob: {ai_response[:80]}"
    await state.update_data(history=new_history)

    # Javobni xabarlarga bo'lib yuborish
    chunks = split_text(ai_response)
    for chunk in chunks:
        try:
            await message.reply(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            try:
                await message.reply(chunk, parse_mode=ParseMode.HTML)
            except Exception:
                await message.reply(chunk, parse_mode=None)


@dp.message(F.text)
async def handle_message(message: types.Message, bot: Bot):
    """
    Matnli xabarlarni qayta ishlash va Instagram/YouTube havolasini tekshirish.
    """
    platform, url = detect_platform(message.text)
    if not platform:
        await message.reply(
            "⚠️ <b>Noma'lum buyruq yoki havola!</b>\n\n"
            "Menga quyidagilarni yuborishingiz mumkin:\n"
            "• <b>💬 AI Chat</b> tugmasini bosib, sun'iy intellekt bilan suhbatlashish\n"
            "• <b>Instagram yoki YouTube havolasi</b> (videoni yuklash uchun)\n"
            "• <b>Oddiy video fayl</b> (dumaloq krujok qilish uchun)\n"
            "• <b>Dumaloq video (krujok)</b> (oddiy video qilish uchun)",
            reply_markup=get_main_keyboard()
        )
        return

    status_msg = await message.reply(f"⏳ {platform} videosi yuklanmoqda, iltimos kuting...")

    # Telegramda "video yuklamoqda" holatini ko'rsatish
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)

    filepath = None
    try:
        # Alohida oqimda videoni yuklash
        video_info = await download_video(url, platform=platform)
        filepath = video_info.get('filepath')

        if not filepath or not os.path.exists(filepath):
            await status_msg.edit_text("❌ Videoni yuklab olishda xatolik yuz berdi.")
            return

        # Fayl hajmini tekshirish
        file_size = os.path.getsize(filepath)
        if file_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                "⚠️ Video hajmi 50MB dan katta bo'lgani sababli Telegram orqali yuborib bo'lmadi."
            )
            return

        # Foydalanuvchiga yuborish holatini ko'rsatish
        try:
            await status_msg.edit_text(f"📤 {platform} videosi Telegramga yuborilmoqda...")
        except Exception:
            pass

        # Videoni yuborish
        video_file = FSInputFile(filepath)
        caption = (
            f"✅ <b>{platform} videosi muvaffaqiyatli yuklab olindi!</b>\n\n"
            f"📌 <b>{video_info.get('title')}</b>\n\n"
            f"🔗 <a href='{url}'>{platform} havolasi</a>"
        )

        await message.reply_video(
            video=video_file,
            caption=caption,
            duration=int(video_info.get('duration') or 0),
            width=video_info.get('width'),
            height=video_info.get('height'),
            supports_streaming=True,
            request_timeout=300
        )

        # Holat xabarini o'chirish
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Xatolik yuz berdi ({platform}): {e}", exc_info=True)
        err_msg_str = str(e).lower()
        if "larger than" in err_msg_str or "max-filesize" in err_msg_str:
            err_text = (
                "⚠️ Ushbu video hajmi 50MB dan katta bo'lgani sababli "
                "Telegram orqali yuborib bo'lmaydi (Telegram botlar limiti 50MB).\n\n"
                "💡 Maslahat: Qisqaroq video yoki YouTube Shorts havolasini yuborib ko'ring."
            )
        elif any(k in err_msg_str for k in ("confirm you're not a bot", "sign in to confirm", "bot", "403", "forbidden")):
            err_text = (
                f"⚠️ <b>{platform} tomonidan cheklov (Bot/IP himoyasi)!</b>\n\n"
                "YouTube/Instagram bulutli server (Render/Cloud) IP-manzilidan yuklashni vaqtincha chekladi.\n\n"
                "🔧 <b>Yechim:</b>\n"
                "1. Botni o'z kompyuteringizda (mahalliy internetda) ishga tushiring: <code>python bot.py</code>\n"
                "2. Yoki brauzerdan <b>cookies.txt</b> olib, Render.com da <b>YOUTUBE_COOKIES</b> o'zgaruvchisiga kiriting."
            )
        elif "timeout" in err_msg_str:
            err_text = (
                "⚠️ Internet tezligi pastligi sababli videoni Telegramga yuklash vaqti tugadi (Timeout). "
                "Iltimos, qaytadan urinib ko'ring yoki qisqaroq video tanlang."
            )
        else:
            err_text = (
                f"❌ Kechirasiz, {platform} videosini yuklab bo'lmadi.\n\n"
                "<b>Mumkin bo'lgan sabablar:</b>\n"
                "• Video o'chirilgan yoki yopiq (private/yopiq profil)\n"
                "• Video hajmi juda katta (Telegram limiti 50MB)\n"
                "• Platforma tomonidan vaqtinchalik cheklov o'rnatilgan"
            )
        await status_msg.edit_text(err_text)
    finally:
        # Faylni server xotirasidan tozalash (Windows blokirovkasini hisobga olgan holda)
        if filepath and os.path.exists(filepath):
            for _ in range(5):
                try:
                    os.remove(filepath)
                    break
                except (PermissionError, OSError):
                    await asyncio.sleep(0.5)


@dp.message(F.video | (F.document & F.document.mime_type.startswith("video/")))
async def handle_video_to_circle(message: types.Message, bot: Bot):
    """
    Oddiy (to'rtburchak) videoni Telegram dumaloq (krujok / video note) formatiga aylantirish.
    """
    video_item = message.video or message.document
    if not video_item:
        return

    # 50MB limit tekshiruvi
    if video_item.file_size and video_item.file_size > MAX_FILE_SIZE:
        await message.reply("⚠️ Video hajmi 50MB dan katta bo'lgani sababli uni qayta ishlab bo'lmaydi.")
        return

    unique_id = str(uuid.uuid4())[:8]
    input_path = str(DOWNLOAD_DIR / f"in_{unique_id}.mp4")
    output_path = str(DOWNLOAD_DIR / f"circle_{unique_id}.mp4")

    status_msg = await message.reply("⏳ Video serverga yuklab olinmoqda...")
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.RECORD_VIDEO_NOTE)

    try:
        # Faylni yuklab olish (300 soniya timeout bilan)
        await bot.download(video_item, destination=input_path, timeout=300)

        # Holat xabarini yangilash
        try:
            await status_msg.edit_text("⚙️ Video 1:1 dumaloq (krujok) formatiga aylantirilmoqda...")
        except Exception:
            pass

        # FFmpeg orqali 1:1 kvadrat dumaloq video formatiga o'tkazish
        await asyncio.to_thread(convert_to_video_note_sync, input_path, output_path)

        if not os.path.exists(output_path):
            await status_msg.edit_text("❌ Dumaloq video yaratishda xatolik yuz berdi.")
            return

        try:
            await status_msg.edit_text("📤 Dumaloq video yuborilmoqda...")
        except Exception:
            pass

        duration = getattr(video_item, 'duration', 0) or 0
        video_note_file = FSInputFile(output_path)

        await message.reply_video_note(
            video_note=video_note_file,
            duration=min(60, int(duration)),
            length=480,
            request_timeout=300
        )
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Dumaloq videoga aylantirishda xatolik: {e}", exc_info=True)
        err_msg_str = str(e).lower()
        if "timeout" in err_msg_str:
            err_text = "⚠️ Video hajmi kattaligi yoki internet sekinligi sababli yuklab olish vaqti tugadi (Timeout). Iltimos, qaytadan urinib ko'ring yoki qisqaroq video yuboring."
        else:
            err_text = "❌ Videoni dumaloq formatga o'tkazishda xatolik yuz berdi."
        await status_msg.edit_text(err_text)
    finally:
        for p in (input_path, output_path):
            if os.path.exists(p):
                for _ in range(5):
                    try:
                        os.remove(p)
                        break
                    except (PermissionError, OSError):
                        await asyncio.sleep(0.5)


@dp.message(F.video_note)
async def handle_circle_to_video(message: types.Message, bot: Bot):
    """
    Dumaloq (krujok / video note) videoni oddiy to'rtburchak video formatiga aylantirish.
    """
    video_note = message.video_note
    if not video_note:
        return

    unique_id = str(uuid.uuid4())[:8]
    input_path = str(DOWNLOAD_DIR / f"note_{unique_id}.mp4")

    status_msg = await message.reply("⏳ Dumaloq video serverga yuklab olinmoqda...")
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)

    try:
        # Dumaloq videoni yuklab olish (300 soniya timeout bilan)
        await bot.download(video_note, destination=input_path, timeout=300)

        if not os.path.exists(input_path):
            await status_msg.edit_text("❌ Videoni yuklab olishda xatolik yuz berdi.")
            return

        try:
            await status_msg.edit_text("📤 Oddiy to'rtburchak video formatida yuborilmoqda...")
        except Exception:
            pass

        video_file = FSInputFile(input_path)
        caption = "🎬 <b>Dumaloq video oddiy to'rtburchak video formatiga o'tkazildi!</b>"

        await message.reply_video(
            video=video_file,
            caption=caption,
            duration=video_note.duration,
            width=video_note.length,
            height=video_note.length,
            supports_streaming=True,
            request_timeout=300
        )
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Oddiy videoga aylantirishda xatolik: {e}", exc_info=True)
        err_msg_str = str(e).lower()
        if "timeout" in err_msg_str:
            err_text = "⚠️ Video hajmi kattaligi yoki internet sekinligi sababli yuklab olish vaqti tugadi (Timeout)."
        else:
            err_text = "❌ Dumaloq videoni oddiy video formatiga o'tkazishda xatolik yuz berdi."
        await status_msg.edit_text(err_text)
    finally:
        if os.path.exists(input_path):
            for _ in range(5):
                try:
                    os.remove(input_path)
                    break
                except (PermissionError, OSError):
                    await asyncio.sleep(0.5)


async def start_health_check_server():
    """
    Render.com Web Service'da 'Port binding timed out' bo'lmasligi va
    servis holati darhol 'Live' bo'lishi uchun yengil HTTP server.
    """
    port = int(os.getenv("PORT", 10000))

    async def handle_ping(request):
        return web.Response(text="Bot is running! OK 200")

    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 HTTP health check server 0.0.0.0:{port} da muvaffaqiyatli ishga tushdi.", flush=True)
    logger.info(f"Render port={port} da HTTP health check server ishga tushdi.")


async def render_keep_alive_task():
    """
    Render.com Free Web Service 15 daqiqa davomida so'rov kelmasa uxlab qolmasligi (spin down bo'lmasligi)
    uchun har 9 daqiqada o'zining public manziliga HTTP GET so'rovi yuborib turadi.
    Bu bot 24/7 kompyuter o'chiq bo'lganda ham uzluksiz ishlashini ta'minlaydi.
    """
    target_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("KEEP_ALIVE_URL")
    if not target_url:
        logger.info("ℹ️ RENDER_EXTERNAL_URL topilmadi (mahalliy rejimda keep-alive ping talab etilmaydi).")
        return

    target_url = target_url.rstrip("/")
    health_url = f"{target_url}/health"
    logger.info(f"🔄 Render 24/7 Keep-alive ping tizimi ishga tushirildi: {health_url}")

    # Server to'liq ko'tarilishi uchun 60 soniya kutish
    await asyncio.sleep(60)

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(health_url, timeout=15) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Render Keep-alive muvaffaqiyatli: {resp.status} OK")
                    else:
                        logger.warning(f"⚠️ Render Keep-alive kutilmagan javob qaytardi: {resp.status}")
        except Exception as e:
            logger.warning(f"⚠️ Render Keep-alive ping xatosi: {e}")

        # Render 15 daqiqada uxlatadi, shuning uchun har 9 daqiqada (540 soniya) ping jo'natiladi
        await asyncio.sleep(540)


async def main():
    if not BOT_TOKEN or BOT_TOKEN == "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ":
        print("\n" + "=" * 60, flush=True)
        print("XATOLIK: BOT_TOKEN topilmadi yoki o'rnatilmadi!", flush=True)
        print("Iltimos, .env faylini oching va @BotFather dan olingan", flush=True)
        print("haqiqiy tokenni BOT_TOKEN o'zgaruvchisiga kiriting.", flush=True)
        print("=" * 60 + "\n", flush=True)
        return

    # Render.com Web Service uchun HTTP portni ochish (har doim ishga tushiramiz)
    try:
        await start_health_check_server()
    except Exception as e:
        logger.warning(f"Health check server ishga tushirishda ogohlantirish: {e}")

    # Render 15 daqiqada uxlab qolmasligi uchun 24/7 Keep-alive vazifasini ishga tushirish
    asyncio.create_task(render_keep_alive_task())

    # Katta video fayllarni yuklashda timeout xatosini oldini olish (300 soniya / 5 daqiqa)
    session = AiohttpSession(timeout=300)
    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    print("🤖 Instagram, YouTube, Video Converter & AI Chat bot ishga tushdi...", flush=True)

    # Eskirgan buyruqlarni tashlab yuborish
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Bot to'xtatildi.")
