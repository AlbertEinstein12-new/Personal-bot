import ast
import base64
import io
import math
import operator
import os
import random
import re
import secrets
import subprocess
import shutil
import string
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import feedparser
import qrcode
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from fastapi import FastAPI
from gtts import gTTS
from PIL import Image, ImageFilter, ImageOps
from pydantic import BaseModel
from yt_dlp import YoutubeDL

PEXELS_API_KEY = "58153772-82cd1401be0f9bfb2c8d71f46"
GEMINI_API_KEY = "AQ.Ab8RN6I_J-XoWiWIX8hGA8gVi2BVsHCbQlcsfWNN0Ci_8nVdQw"
OPENWEATHER_API_KEY = "60718ed704cbc904c245fc9615de809b"
CRICAPI_KEY = ""
GEMINI_MODEL = "gemini-2.5-flash"
BOT_NUMBER = "14388162413"
ALLOWED_NUMBERS = ""
PREFIX = "/"

BASE_DIR = Path(__file__).resolve().parent
BOT_DIR = BASE_DIR / "bot"
AUTH_DIR = "/data/auth" if os.path.isdir("/data") else str(BOT_DIR / "auth")

os.environ["PEXELS_API_KEY"] = PEXELS_API_KEY
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
os.environ["OPENWEATHER_API_KEY"] = OPENWEATHER_API_KEY
os.environ["CRICAPI_KEY"] = CRICAPI_KEY
os.environ["GEMINI_MODEL"] = GEMINI_MODEL
os.environ["PAIR_NUMBER"] = BOT_NUMBER
os.environ["ALLOWED"] = ALLOWED_NUMBERS
os.environ["PREFIX"] = PREFIX
os.environ["AUTH_DIR"] = AUTH_DIR
os.environ["API_URL"] = "http://127.0.0.1:8000"

UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
GEO_UA = {"User-Agent": "PersonalWhatsAppBot/1.0"}
MAX_MB = 50

app = FastAPI()


class Cmd(BaseModel):
    cmd: str
    args: str = ""
    media_b64: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


def text(t):
    return {"type": "text", "text": t}


def media(kind, data, caption="", mime=None, filename=None):
    return {
        "type": kind,
        "b64": base64.b64encode(data).decode(),
        "caption": caption,
        "mime": mime,
        "filename": filename,
    }


HELP = """📋 *Bot Commands*

*Downloader*
/song naam
/video naam ya link
/insta /fb /tiktok link
/pic cheez
/sticker (photo bhejo ya reply karo)

*AI / Fun*
/ai sawal
/imagine description
/roast naam
/meme
/joke
/shayari topic
/truth
/dare
/8ball sawal

*Daily*
/weather shehar
/score
/movie naam
/translate urdu text (default English)
/remind 10m kaam
/qr text
/calc 2+2*5
/news topic

*Pro*
/bgremove (photo)
/upscale (photo)
/voice text
/location shehar (ya location bhejo)
/password 16"""

PERSONA = (
    "Tum ek dost jaisa WhatsApp bot ho. Jawab Roman Urdu (Latin script) me do, "
    "chhota, mazedaar aur saaf. Kisi ke mazhab, khandaan ya jism ka mazaak mat udao."
)

LANGS = {
    "en": "en", "english": "en", "ur": "ur", "urdu": "ur", "hindi": "hi",
    "ar": "ar", "arabic": "ar", "fr": "fr", "french": "fr", "de": "de",
    "german": "de", "es": "es", "spanish": "es", "tr": "tr", "turkish": "tr",
    "ru": "ru", "russian": "ru", "pa": "pa", "punjabi": "pa", "bn": "bn",
    "bengali": "bn", "ja": "ja", "japanese": "ja", "ko": "ko", "korean": "ko",
    "zh": "zh-CN", "chinese": "zh-CN",
}

AUDIO_MIME = {
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".webm": "audio/webm",
    ".opus": "audio/ogg; codecs=opus",
    ".ogg": "audio/ogg",
}

BALL = [
    "Haan bilkul 😎", "Pakka nahi, dobara pooch", "Bilkul nahi 🙅", "Lagta to hai",
    "Mere hisaab se haan", "Abhi kuch nahi keh sakta", "Dil se na bol raha hu 😅",
    "Sitare kehte hain haan ✨", "Umeed mat rakh", "Zaroor hoga", "Nahi yaar",
    "Pehle chai pi le, phir pooch ☕",
]

UNITS = {
    "s": 1, "sec": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
}


def split_lang(args, default):
    parts = args.split(None, 1)
    if len(parts) == 2 and parts[0].lower() in LANGS:
        return LANGS[parts[0].lower()], parts[1]
    return default, args


def gemini(prompt, system=PERSONA):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return "GEMINI_API_KEY main.py me nahi mili"
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key},
        json=body,
        timeout=60,
    )
    if r.status_code != 200:
        return f"Gemini error {r.status_code}: {r.text[:200]}"
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip() or "Gemini ne khali jawab diya"
    except Exception:
        return "Gemini ne jawab nahi diya (shayad safety block)"


def fetch_video(target, audio=False):
    tmp = tempfile.mkdtemp()
    try:
        if audio:
            fmt = "bestaudio[ext=m4a]/bestaudio"
        else:
            fmt = "best[ext=mp4][height<=480]/best[height<=480]/best"
        opts = {
            "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "max_filesize": MAX_MB * 1024 * 1024,
            "format": fmt,
        }
        if not target.startswith("http"):
            target = f"ytsearch1:{target}"
        with YoutubeDL(opts) as y:
            info = y.extract_info(target, download=True)
        if info and "entries" in info:
            info = info["entries"][0]
        files = sorted(Path(tmp).iterdir())
        if not files:
            raise RuntimeError("file download nahi hui (size zyada ya link private)")
        f = files[0]
        return f.read_bytes(), f.suffix.lower(), (info or {}).get("title", "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_help(c):
    return text(HELP)


def cmd_song(c):
    if not c.args:
        return text("Use: /song gaane ka naam")
    data, ext, title = fetch_video(c.args, audio=True)
    return [text(f"🎵 {title}"), media("audio", data, mime=AUDIO_MIME.get(ext, "audio/mp4"))]


def cmd_video(c):
    if not c.args:
        return text("Use: /video naam ya YouTube link")
    data, ext, title = fetch_video(c.args)
    return media("video", data, caption=f"🎬 {title}", mime="video/mp4")


def cmd_social(c):
    if not c.args.startswith("http"):
        return text("Use: /insta ya /fb ya /tiktok ke saath poora link")
    data, ext, title = fetch_video(c.args.split()[0])
    return media("video", data, caption=f"⬇️ {title[:200]}", mime="video/mp4")


def cmd_pic(c):
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return text("PEXELS_API_KEY main.py me nahi mili")
    if not c.args:
        return text("Use: /pic cheez ka naam")
    r = requests.get(
        "https://api.pexels.com/v1/search",
        params={"query": c.args, "per_page": 15},
        headers={"Authorization": key},
        timeout=20,
    )
    r.raise_for_status()
    photos = r.json().get("photos", [])
    if not photos:
        return text("Is naam ki koi pic nahi mili")
    p = random.choice(photos)
    img = requests.get(p["src"]["large"], timeout=30).content
    return media("image", img, caption=f"📸 {c.args} • {p.get('photographer', '')}")


def cmd_sticker(c):
    if not c.media_b64:
        return text("Photo bhejo caption /sticker ke saath, ya kisi photo ko reply karke /sticker likho")
    im = Image.open(io.BytesIO(base64.b64decode(c.media_b64))).convert("RGBA")
    im = ImageOps.contain(im, (512, 512))
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    canvas.paste(im, ((512 - im.width) // 2, (512 - im.height) // 2), im)
    buf = io.BytesIO()
    canvas.save(buf, "WEBP", quality=80)
    return media("sticker", buf.getvalue())


def cmd_ai(c):
    if not c.args:
        return text("Use: /ai apna sawal")
    return text("🤖 " + gemini(c.args))


def cmd_imagine(c):
    if not c.args:
        return text("Use: /imagine kya banana hai")
    url = f"https://image.pollinations.ai/prompt/{quote(c.args)}?width=768&height=768&nologo=true"
    r = requests.get(url, timeout=120)
    if r.status_code != 200 or "image" not in r.headers.get("content-type", ""):
        return text("Image nahi ban saki, thodi der baad try karo")
    return media("image", r.content, caption=f"🎨 {c.args}")


def cmd_roast(c):
    who = c.args or "mera dost"
    return text("🔥 " + gemini(f"{who} ko 3-4 line me halki phulki dosti wali roast karo."))


def cmd_meme(c):
    for _ in range(3):
        r = requests.get("https://meme-api.com/gimme", timeout=20).json()
        if not r.get("nsfw") and not r.get("spoiler"):
            img = requests.get(r["url"], timeout=30).content
            return media("image", img, caption=f"😂 {r.get('title', '')}")
    return text("Meme nahi mila, dobara try karo")


def cmd_joke(c):
    return text("😄 " + gemini("Ek chhota saaf suthra mazedaar joke sunao."))


def cmd_shayari(c):
    topic = c.args or "dosti"
    return text("✍️ " + gemini(f"{topic} par 4 line ki Roman Urdu shayari likho."))


def cmd_truth(c):
    return text("🎯 Truth: " + gemini("Dosto ki game ke liye ek mazedaar Truth sawal do. Sirf sawal likho."))


def cmd_dare(c):
    return text("🔥 Dare: " + gemini("Dosto ki game ke liye ek mazedaar aur safe Dare do. Sirf dare likho."))


def cmd_8ball(c):
    if not c.args:
        return text("Use: /8ball apna sawal")
    return text("🎱 " + random.choice(BALL))


def cmd_weather(c):
    key = os.getenv("OPENWEATHER_API_KEY")
    if not key:
        return text("OPENWEATHER_API_KEY main.py me nahi mili")
    if not c.args:
        return text("Use: /weather shehar ka naam")
    r = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"q": c.args, "appid": key, "units": "metric"},
        timeout=20,
    )
    if r.status_code == 401:
        return text("Weather key abhi active nahi hui (nayi key 1-2 ghante leti hai) ya galat hai")
    if r.status_code == 404:
        return text("Ye shehar nahi mila")
    r.raise_for_status()
    d = r.json()
    w = d["weather"][0]["description"].title()
    m = d["main"]
    return text(
        f"🌤️ *{d['name']}, {d['sys'].get('country', '')}*\n"
        f"{w}\n"
        f"🌡️ {m['temp']:.0f}°C (mehsoos {m['feels_like']:.0f}°C)\n"
        f"💧 Nami {m['humidity']}%\n"
        f"💨 Hawa {d['wind']['speed']} m/s"
    )


def cmd_score(c):
    key = os.getenv("CRICAPI_KEY")
    if key:
        r = requests.get(
            "https://api.cricapi.com/v1/currentMatches",
            params={"apikey": key, "offset": 0},
            timeout=20,
        ).json()
        rows = []
        for m in r.get("data", [])[:8]:
            rows.append(f"🏏 {m.get('name', '')}\n{m.get('status', '')}")
        if rows:
            return text("\n\n".join(rows))
    r = requests.get("https://www.cricbuzz.com/cricket-match/live-scores", headers=UA, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    seen = []
    for a in soup.select('a[href*="/live-cricket-scores/"]'):
        t = a.get_text(" ", strip=True) or a.get("title", "")
        if t and t not in seen:
            seen.append(t)
    if not seen:
        return text("Abhi koi live match nahi mila")
    return text("🏏 *Live Cricket*\n\n" + "\n\n".join(seen[:8]))


def cmd_movie(c):
    if not c.args:
        return text("Use: /movie film ka naam")
    s = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={"action": "query", "list": "search", "srsearch": f"{c.args} film", "format": "json", "srlimit": 1},
        headers=GEO_UA,
        timeout=20,
    ).json()
    hits = s.get("query", {}).get("search", [])
    if not hits:
        return text("Ye film nahi mili")
    title = hits[0]["title"]
    d = requests.get(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}",
        headers=GEO_UA,
        timeout=20,
    ).json()
    link = d.get("content_urls", {}).get("desktop", {}).get("page", "")
    return text(f"🎬 *{d.get('title', title)}*\n\n{d.get('extract', 'Story nahi mili')}\n\n🔗 {link}")


def cmd_translate(c):
    if not c.args:
        return text("Use: /translate urdu hello  (ya sirf /translate text = English me)")
    lang, body = split_lang(c.args, "en")
    out = GoogleTranslator(source="auto", target=lang).translate(body)
    return text(f"🌐 {out}")


def cmd_remind(c):
    m = re.match(r"^(\d+)\s*([a-zA-Z]*)\s+(.+)$", c.args, re.S)
    if not m:
        return text("Use: /remind 10m chai peena  (s, m, h)")
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit in UNITS:
        secs = n * UNITS[unit]
        msg = m.group(3)
    else:
        secs = n * 60
        msg = f"{m.group(2)} {m.group(3)}".strip()
    secs = max(1, min(secs, 86400))
    return {
        "type": "reminder",
        "seconds": secs,
        "text": msg,
        "confirm": f"⏰ Theek hai, {secs // 60 if secs >= 60 else secs} {'min' if secs >= 60 else 'sec'} baad yaad dilaunga: {msg}",
    }


def cmd_qr(c):
    if not c.args:
        return text("Use: /qr koi bhi text ya link")
    buf = io.BytesIO()
    qrcode.make(c.args).save(buf, "PNG")
    return media("image", buf.getvalue(), caption="🔳 QR tayyar")


OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "abs": abs, "round": round,
    "factorial": math.factorial,
}
CONSTS = {"pi": math.pi, "e": math.e}


def ev(n):
    if isinstance(n, ast.Expression):
        return ev(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.Name) and n.id in CONSTS:
        return CONSTS[n.id]
    if isinstance(n, ast.BinOp) and type(n.op) in OPS:
        left, right = ev(n.left), ev(n.right)
        if isinstance(n.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("power bohot bada hai")
        return OPS[type(n.op)](left, right)
    if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
        return OPS[type(n.op)](ev(n.operand))
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords:
        return FUNCS[n.func.id](*[ev(a) for a in n.args])
    raise ValueError("ye expression samajh nahi aaya")


def cmd_calc(c):
    if not c.args:
        return text("Use: /calc 2+2*5  ya  /calc sqrt(144)")
    expr = c.args.replace("^", "**").replace("×", "*").replace("÷", "/")
    val = ev(ast.parse(expr, mode="eval"))
    if isinstance(val, float):
        val = int(val) if val.is_integer() else round(val, 10)
    return text(f"🧮 {c.args} = *{val}*")


def cmd_news(c):
    if c.args:
        url = f"https://news.google.com/rss/search?q={quote(c.args)}&hl=en-PK&gl=PK&ceid=PK:en"
    else:
        url = "https://news.google.com/rss?hl=en-PK&gl=PK&ceid=PK:en"
    feed = feedparser.parse(url, agent=UA["User-Agent"])
    items = feed.entries[:7]
    if not items:
        return text("Abhi koi khabar nahi mili")
    lines = [f"{i}. {e.title}\n{e.link}" for i, e in enumerate(items, 1)]
    return text("📰 *Taza Khabrein*\n\n" + "\n\n".join(lines))


def cmd_bgremove(c):
    if not c.media_b64:
        return text("Photo bhejo caption /bgremove ke saath, ya photo ko reply karo")
    try:
        from rembg import remove
    except ImportError:
        return text("rembg install nahi hai: pip install -r requirements-extra.txt")
    out = remove(base64.b64decode(c.media_b64))
    im = Image.open(io.BytesIO(out)).convert("RGBA")
    white = Image.new("RGBA", im.size, (255, 255, 255, 255))
    white.alpha_composite(im)
    prev = io.BytesIO()
    white.convert("RGB").save(prev, "JPEG", quality=90)
    return [
        media("image", prev.getvalue(), caption="✂️ Background hat gaya"),
        media("document", out, mime="image/png", filename="no-background.png"),
    ]


def cmd_upscale(c):
    if not c.media_b64:
        return text("Photo bhejo caption /upscale ke saath, ya photo ko reply karo")
    im = Image.open(io.BytesIO(base64.b64decode(c.media_b64))).convert("RGB")
    scale = min(2.0, 3000 / max(im.size))
    if scale > 1:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return media("image", buf.getvalue(), caption=f"🔍 {im.width}x{im.height}")


def cmd_voice(c):
    if not c.args:
        return text("Use: /voice hello dost  ya  /voice urdu اردو متن")
    lang, body = split_lang(c.args, "en")
    buf = io.BytesIO()
    gTTS(body[:500], lang=lang).write_to_fp(buf)
    return media("audio", buf.getvalue(), mime="audio/mpeg")


def cmd_location(c):
    if c.lat is not None and c.lon is not None:
        lat, lon = c.lat, c.lon
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "jsonv2", "accept-language": "en"},
            headers=GEO_UA,
            timeout=20,
        ).json()
        place = r.get("display_name", "Pata nahi chala")
    elif c.args:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": c.args, "format": "jsonv2", "limit": 1, "accept-language": "en"},
            headers=GEO_UA,
            timeout=20,
        ).json()
        if not r:
            return text("Ye jagah nahi mili")
        lat, lon, place = r[0]["lat"], r[0]["lon"], r[0]["display_name"]
    else:
        return text("Location bhejo ya likho: /location shehar ka naam")
    return text(f"📍 {place}\n🧭 {lat}, {lon}\n🗺️ https://www.google.com/maps?q={lat},{lon}")


def cmd_password(c):
    n = int(c.args) if c.args.strip().isdigit() else 14
    n = max(8, min(n, 64))
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%^&*-_?"]
    chars = [secrets.choice(p) for p in pools]
    allc = "".join(pools)
    chars += [secrets.choice(allc) for _ in range(n - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return text("🔐 " + "".join(chars))


HANDLERS = {
    "help": cmd_help, "menu": cmd_help, "start": cmd_help,
    "song": cmd_song, "video": cmd_video,
    "insta": cmd_social, "instagram": cmd_social, "fb": cmd_social,
    "facebook": cmd_social, "tiktok": cmd_social,
    "pic": cmd_pic, "sticker": cmd_sticker,
    "ai": cmd_ai, "imagine": cmd_imagine, "roast": cmd_roast, "meme": cmd_meme,
    "joke": cmd_joke, "shayari": cmd_shayari, "truth": cmd_truth, "dare": cmd_dare,
    "8ball": cmd_8ball,
    "weather": cmd_weather, "score": cmd_score, "movie": cmd_movie,
    "translate": cmd_translate, "remind": cmd_remind, "qr": cmd_qr,
    "calc": cmd_calc, "news": cmd_news,
    "bgremove": cmd_bgremove, "upscale": cmd_upscale, "voice": cmd_voice,
    "location": cmd_location, "password": cmd_password,
}


@app.post("/cmd")
def run(c: Cmd):
    fn = HANDLERS.get(c.cmd.lower())
    if not fn:
        return {"replies": [text("Ye command nahi mili. /help likho")]}
    try:
        out = fn(c)
    except Exception as e:
        out = text(f"⚠️ /{c.cmd} fail hua: {str(e)[:200]}")
    return {"replies": out if isinstance(out, list) else [out]}


@app.get("/ping")
def ping():
    return {"ok": True}


BOT_JS = r"""import path from 'node:path'
import pino from 'pino'
import qrcode from 'qrcode-terminal'
import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  downloadMediaMessage,
  Browsers
} from '@whiskeysockets/baileys'

const here = process.cwd()

const PREFIX = process.env.PREFIX || '/'
const API_URL = process.env.API_URL || 'http://127.0.0.1:8000'
const PAIR = (process.env.PAIR_NUMBER || '').replace(/\D/g, '')
const ALLOWED = (process.env.ALLOWED || '').split(',').map(s => s.trim()).filter(Boolean)
const MEDIA_CMDS = new Set(['sticker', 'bgremove', 'upscale'])
const logger = pino({ level: 'silent' })

let sock

const unwrap = m => m?.ephemeralMessage?.message ?? m?.viewOnceMessage?.message ?? m

const getText = m =>
  m.conversation ||
  m.extendedTextMessage?.text ||
  m.imageMessage?.caption ||
  m.videoMessage?.caption ||
  ''

async function grabImage(msg, m) {
  const jid = msg.key.remoteJid
  let target = null
  if (m.imageMessage) {
    target = msg
  } else {
    const ctx = m.extendedTextMessage?.contextInfo
    const q = ctx?.quotedMessage && unwrap(ctx.quotedMessage)
    if (q?.imageMessage) {
      target = {
        key: { remoteJid: jid, id: ctx.stanzaId, participant: ctx.participant, fromMe: false },
        message: q
      }
    }
  }
  if (!target) return null
  const buf = await downloadMediaMessage(target, 'buffer', {}, {
    logger,
    reuploadRequest: sock.updateMediaMessage
  })
  return buf.toString('base64')
}

async function callApi(payload) {
  const res = await fetch(`${API_URL}/cmd`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(280000)
  })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()).replies
}

async function deliver(jid, msg, r) {
  const opt = { quoted: msg }
  const buf = r.b64 ? Buffer.from(r.b64, 'base64') : null
  switch (r.type) {
    case 'text':
      return sock.sendMessage(jid, { text: r.text }, opt)
    case 'image':
      return sock.sendMessage(jid, { image: buf, caption: r.caption || '' }, opt)
    case 'video':
      return sock.sendMessage(jid, { video: buf, caption: r.caption || '', mimetype: r.mime || 'video/mp4' }, opt)
    case 'audio':
      return sock.sendMessage(jid, { audio: buf, mimetype: r.mime || 'audio/mpeg' }, opt)
    case 'sticker':
      return sock.sendMessage(jid, { sticker: buf }, opt)
    case 'document':
      return sock.sendMessage(jid, { document: buf, mimetype: r.mime, fileName: r.filename || 'file' }, opt)
    case 'reminder':
      await sock.sendMessage(jid, { text: r.confirm }, opt)
      setTimeout(() => {
        sock.sendMessage(jid, { text: `⏰ *Yaad dihani:* ${r.text}` }).catch(console.error)
      }, r.seconds * 1000)
      return
  }
}

async function handle(msg) {
  if (!msg.message) return
  const jid = msg.key.remoteJid
  if (!jid || jid === 'status@broadcast') return

  const m = unwrap(msg.message)
  const who = (msg.key.participant || jid).split('@')[0].split(':')[0]
  if (!msg.key.fromMe && ALLOWED.length && !ALLOWED.includes(who)) return

  let cmd, args, extra = {}
  if (m.locationMessage) {
    cmd = 'location'
    args = ''
    extra = { lat: m.locationMessage.degreesLatitude, lon: m.locationMessage.degreesLongitude }
  } else {
    const body = getText(m).trim()
    if (!body.startsWith(PREFIX)) return
    const match = body.slice(PREFIX.length).match(/^(\S+)\s*([\s\S]*)$/)
    if (!match) return
    cmd = match[1].toLowerCase()
    args = match[2].trim()
  }

  await sock.sendPresenceUpdate('composing', jid)

  let media_b64 = null
  if (MEDIA_CMDS.has(cmd)) media_b64 = await grabImage(msg, m)

  try {
    const replies = await callApi({ cmd, args, media_b64, ...extra })
    for (const r of replies) await deliver(jid, msg, r)
  } catch (e) {
    console.error(e)
    await sock.sendMessage(jid, { text: '⚠️ Python API se jawab nahi aaya. Kya api chal rahi hai?' }, { quoted: msg })
  }
}

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState(process.env.AUTH_DIR || path.join(here, 'auth'))
  const { version } = await fetchLatestBaileysVersion()

  sock = makeWASocket({
    version,
    auth: state,
    logger,
    browser: Browsers.ubuntu('Chrome'),
    markOnlineOnConnect: false
  })

  sock.ev.on('creds.update', saveCreds)

  if (PAIR && !sock.authState.creds.registered) {
    setTimeout(async () => {
      try {
        const code = await sock.requestPairingCode(PAIR)
        console.log(`\nPairing code: ${code}\nWhatsApp > Linked devices > Link with phone number\n`)
      } catch (e) {
        console.error('Pairing code nahi bana:', e.message)
      }
    }, 3000)
  }

  sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
    if (qr && !PAIR) qrcode.generate(qr, { small: true })
    if (connection === 'open') console.log('Bot connected ✅')
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode
      if (code === DisconnectReason.loggedOut) {
        console.log('Logout ho gaya. bot/auth folder delete karke dobara chalao.')
      } else {
        setTimeout(start, 3000)
      }
    }
  })

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return
    for (const msg of messages) {
      try {
        await handle(msg)
      } catch (e) {
        console.error(e)
      }
    }
  })
}

start()
"""

PACKAGE_JSON = r"""{
  "name": "wa-chill-bot",
  "version": "1.0.0",
  "type": "module",
  "private": true,
  "dependencies": {
    "@whiskeysockets/baileys": "latest",
    "pino": "^9.0.0",
    "qrcode-terminal": "^0.12.0"
  }
}
"""


def write_bot_files():
    BOT_DIR.mkdir(parents=True, exist_ok=True)
    (BOT_DIR / "index.js").write_text(BOT_JS)
    (BOT_DIR / "package.json").write_text(PACKAGE_JSON)


def install_node_deps():
    if not (BOT_DIR / "node_modules").exists():
        subprocess.run(["npm", "install", "--omit=dev"], cwd=BOT_DIR, check=True)


if __name__ == "__main__":
    write_bot_files()
    if "--setup" in sys.argv:
        install_node_deps()
        sys.exit(0)
    install_node_deps()
    Path(AUTH_DIR).mkdir(parents=True, exist_ok=True)
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=BASE_DIR,
    )
    time.sleep(3)
    try:
        code = subprocess.call(["node", "index.js"], cwd=BOT_DIR)
    finally:
        api.terminate()
    sys.exit(code)
