import os
import json
import time
import math
import asyncio
import datetime
import subprocess
import requests
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import edge_tts

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

STYLE_LOCK = (
    "2D classic whiteboard stickman animation on clean white paper background, "
    "hand-drawn black marker lines with expressive stickman characters, clear storytelling props, "
    "smooth 2D motion, warm red-orange accent highlight on key object, no text or watermarks"
)

SYSTEM_PROMPT = (
    "You are a professional 'Why?' Stickman animation director for an English YouTube channel. "
    "Pick one fascinating 'Why...?' psychology or science question and write a 35-scene script (~4 minutes). "
    "For each scene provide: "
    "1. narration_en: 12-18 words of engaging, conversational English addressing 'you'. "
    "2. flow_prompt: vivid 1-sentence visual scene description for AI video/image generation showing stickman character acting out the story with props. "
    "3. camera_move: one of ['zoom_in', 'zoom_out', 'pan_right', 'pan_left']. "
    'Return ONLY valid JSON: {"title_en": "Why...?", "description_en": "...", "scenes": [{"scene_number": 1, "narration_en": "...", "flow_prompt": "...", "camera_move": "zoom_in"}]}'
)


def generate_script():
    models = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-pro"]
    last_err = None
    for m in models:
        try:
            print("1. Generating 35-scene script with:", m, flush=True)
            resp = client.models.generate_content(
                model=m,
                contents="Create a deep, fascinating 35-scene 'Why...?' stickman video script in English.",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.8,
                ),
            )
            data = json.loads(resp.text)
            if len(data.get("scenes", [])) >= 15:
                print("Script ready! Scenes:", len(data["scenes"]), flush=True)
                return data
        except Exception as e:
            print(m, "failed:", e, flush=True)
            last_err = e
            time.sleep(3)
    raise RuntimeError("Script generation failed: " + str(last_err))


def configure_flow_models(page):
    """Google Flow'da rasm uchun Nano Banana 2.1 va video uchun 6 kreditli modelni tanlash."""
    try:
        # 1. Model / Settings menyularini tekshirish
        for trigger_text in ["Veo", "Imagen", "Nano", "Model", "Quality", "Fast", "Settings", "tune"]:
            btns = page.locator(f"button:has-text('{trigger_text}')")
            for i in range(btns.count()):
                b = btns.nth(i)
                if b.is_visible():
                    b.click()
                    time.sleep(1.2)
                    # Rasm modeli: Nano Banana 2.1
                    nb = page.locator("text=/Nano Banana 2\\.1/i").first
                    if nb.count() > 0 and nb.is_visible():
                        nb.click()
                        print("Selected image model: Nano Banana 2.1", flush=True)
                        time.sleep(1)
                    # Video modeli: 6 kredit sarflaydigan (Fast / 6 credits) variant
                    v6 = page.locator("text=/6\\s*credit|Fast.*6|Veo.*Fast/i").first
                    if v6.count() > 0 and v6.is_visible():
                        v6.click()
                        print("Selected video model: 6-credit Fast mode", flush=True)
                        time.sleep(1)
                    page.keyboard.press("Escape")
                    time.sleep(0.5)
    except Exception as e:
        print("Model selector check note:", e, flush=True)


def generate_flow_assets(scenes):
    os.makedirs("build/flow", exist_ok=True)
    cookies_file = "flow_cookies.json"
    if not os.path.exists(cookies_file) and os.environ.get("FLOW_COOKIES_JSON"):
        with open(cookies_file, "w", encoding="utf-8") as f:
            f.write(os.environ["FLOW_COOKIES_JSON"])

    results = {}
    if not os.path.exists(cookies_file):
        print("flow_cookies.json topilmadi.", flush=True)
        return results

    with open(cookies_file, "r", encoding="utf-8") as f:
        raw_cookies = json.load(f)

    clean_cookies = []
    for c in raw_cookies:
        item = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ".google.com"),
            "path": c.get("path", "/"),
        }
        if c.get("sameSite") in ("Strict", "Lax", "None"):
            item["sameSite"] = c["sameSite"]
        clean_cookies.append(item)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_cookies(clean_cookies)
        page = context.new_page()

        try:
            print("Opening Google Flow (https://flow.google.com)...", flush=True)
            page.goto("https://flow.google.com", timeout=60000, wait_until="domcontentloaded")
            time.sleep(6)

            if "accounts.google.com" in page.url:
                print("WARNING: flow_cookies.json eskirgan (login kerak).", flush=True)
                browser.close()
                return results

            for btn_text in ["New project", "Create", "Start"]:
                btn = page.locator(f"button:has-text('{btn_text}')").first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    time.sleep(4)
                    break

            configure_flow_models(page)

            seen_urls = set()
            for idx, sc in enumerate(scenes, start=1):
                prompt_text = f"{sc['flow_prompt']}. {STYLE_LOCK}"
                print(f"[Flow {idx}/{len(scenes)}] Generating: {sc['flow_prompt'][:55]}...", flush=True)
                try:
                    # Har sahna oldidan 6-kreditli rejim va Nano Banana 2.1 faolligini tekshirish
                    if idx == 1:
                        configure_flow_models(page)

                    box = page.locator("textarea, [contenteditable='true']").first
                    box.wait_for(state="visible", timeout=15000)
                    box.click()
                    box.fill("")
                    time.sleep(0.4)
                    box.fill(prompt_text)
                    time.sleep(0.6)
                    page.keyboard.press("Enter")

                    media_url = None
                    is_video = False
                    for _ in range(18):
                        time.sleep(5)
                        vids = page.locator("video[src^='http'], video source[src^='http']")
                        if vids.count() > 0:
                            src = vids.last.get_attribute("src")
                            if src and src not in seen_urls:
                                media_url = src
                                is_video = True
                                break
                        imgs = page.locator("img[src^='https://lh3.'], img[src^='https://storage.']")
                        if imgs.count() > 0:
                            src = imgs.last.get_attribute("src")
                            if src and src not in seen_urls:
                                media_url = src
                                is_video = False
                                break

                    if media_url:
                        seen_urls.add(media_url)
                        ext = "mp4" if is_video else "png"
                        out_f = f"build/flow/scene_{idx}.{ext}"
                        r = requests.get(media_url, timeout=30)
                        if r.status_code == 200 and len(r.content) > 5000:
                            with open(out_f, "wb") as fp:
                                fp.write(r.content)
                            results[idx] = out_f
                            print(f"   Saved Flow asset ({ext}): {out_f}", flush=True)
                except Exception as scene_err:
                    print(f"   Flow scene {idx} skipped: {scene_err}", flush=True)
        except Exception as e:
            print("Flow session error:", e, flush=True)
        finally:
            browser.close()

    return results


def draw_fallback_frame(s_idx, f_idx, out_path):
    img = Image.new("RGB", (1280, 720), (252, 252, 250))
    d = ImageDraw.Draw(img)
    blk, acc = (22, 22, 24), (232, 68, 42)
    bob = int(math.sin(f_idx * 0.45) * 6)
    wave = int(math.cos(f_idx * 0.45) * 16)
    d.line([(160, 590), (1120, 590)], fill=blk, width=6)
    hx, hy, r = 640, 220 + bob, 55
    d.ellipse([hx - r, hy - r, hx + r, hy + r], outline=blk, width=7)
    d.ellipse([hx - 20, hy - 10, hx - 9, hy + 1], fill=blk)
    d.ellipse([hx + 9, hy - 10, hx + 20, hy + 1], fill=blk)
    talk = abs(int(math.sin(f_idx * 1.1) * 13))
    d.ellipse([hx - 13, hy + 12, hx + 13, hy + 16 + talk], outline=blk, width=5)
    d.line([(hx, hy + r), (hx, 435 + bob // 2)], fill=blk, width=8)
    d.line([(hx, hy + r + 30), (hx - 85, 360 - wave)], fill=blk, width=7)
    d.line([(hx, hy + r + 30), (hx + 85, 360 + wave)], fill=blk, width=7)
    d.line([(hx, 435), (hx - 50, 590)], fill=blk, width=8)
    d.line([(hx, 435), (hx + 50, 590)], fill=blk, width=8)
    d.ellipse([hx + 110, hy - 80 + bob, hx + 170, hy - 20 + bob], outline=acc, width=9)
    img.save(out_path, "PNG")


async def generate_voice(text_en, out_path):
    clean = (text_en or "").strip() or "Let us explore how your brain works."
    voices = ["en-US-AndrewNeural", "en-US-GuyNeural", "en-US-ChristopherNeural"]
    last_err = None
    for attempt in range(4):
        v = voices[attempt % len(voices)]
        try:
            comm = edge_tts.Communicate(clean, v, rate="+4%")
            await comm.save(out_path)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                await asyncio.sleep(1.2)
                return
        except Exception as e:
            print("Voice retry", attempt + 1, e, flush=True)
            last_err = e
            await asyncio.sleep(4)
    raise RuntimeError("TTS failed: " + str(last_err))


def get_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())


def format_ass_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def create_styled_cc(text_en, duration, ass_path):
    """Chiroyli pop-in va glow effektli dinamik CC (subtitr) faylini yaratish."""
    words = (text_en or "").strip().split()
    if not words:
        words = ["Why", "does", "this", "happen?"]

    # Har bir kadrda 3-4 tadan so'z chiqishi (zamonaviy YouTube retention CC)
    chunks = [" ".join(words[i:i + 4]) for i in range(0, len(words), 4)]
    step = duration / len(chunks)

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: PopCC,DejaVu Sans,46,&H00FFFFFF,&H000066FF,&H00141414,&H80000000,-1,0,0,0,100,100,1,0,1,4,2,2,60,60,48,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for idx, chunk in enumerate(chunks):
        t0 = idx * step
        t1 = (idx + 1) * step
        # Pop-in zoom effekti (\fscx85\fscy85 -> \fscx103\fscy103 -> \fscx100\fscy100)
        styled_text = (
            r"{\fscx82\fscy82\t(0,110,\fscx104\fscy104)\t(110,220,\fscx100\fscy100)}"
            + chunk.upper()
        )
        lines.append(f"Dialogue: 0,{format_ass_time(t0)},{format_ass_time(t1)},PopCC,,0,0,0,,{styled_text}\n")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def build_scene_clip(s_idx, asset_path, text_en, aud_path, move, clip_path):
    dur = get_duration(aud_path) + 0.3
    f_str = str(int(dur * 30))
    ass_path = f"build/cc_{s_idx}.ass"
    create_styled_cc(text_en, dur, ass_path)
    ass_esc = ass_path.replace("\\", "/").replace(":", "\\:")

    if move == "zoom_in":
        z = "zoom='min(zoom+0.0012,1.16)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif move == "zoom_out":
        z = "zoom='if(lte(zoom,1.0),1.16,max(1.001,zoom-0.0012))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif move == "pan_right":
        z = "zoom='1.08':x='(iw-iw/zoom)*(on/" + f_str + ")':y='ih/2-(ih/zoom/2)'"
    else:
        z = "zoom='1.08':x='(iw-iw/zoom)*(1-on/" + f_str + ")':y='ih/2-(ih/zoom/2)'"

    # Chiroyli montaj effekti: silliq kirish (fade) + yumshoq vignette + pop-in CC subtitrlar
    post_fx = f"fade=t=in:st=0:d=0.22,vignette=PI/6,ass='{ass_esc}',format=yuv420p"

    if asset_path and asset_path.endswith(".mp4"):
        vf = f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30,{post_fx}"
        subprocess.run(
            ["ffmpeg", "-y", "-stream_loop", "-1", "-i", asset_path, "-i", aud_path, "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-t", str(dur), clip_path],
            check=True,
        )
    elif asset_path and asset_path.endswith(".png"):
        vf = f"scale=2560:1440,zoompan={z}:d={f_str}:s=1280x720:fps=30,{post_fx}"
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", asset_path, "-i", aud_path, "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-t", str(dur), clip_path],
            check=True,
        )
    else:
        fps = 12
        n_frames = max(int(dur * fps), 12)
        fdir = f"build/frames_{s_idx}"
        os.makedirs(fdir, exist_ok=True)
        for i in range(n_frames):
            draw_fallback_frame(s_idx, i, f"{fdir}/f_{i:04d}.png")
        vf = f"fps=30,zoompan={z}:d=1:s=1280x720:fps=30,{post_fx}"
        subprocess.run(
            ["ffmpeg", "-y", "-framerate", str(fps), "-i", f"{fdir}/f_%04d.png", "-i", aud_path, "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-c:a", "aac", "-b:a", "192k", "-t", str(dur), clip_path],
            check=True,
        )


def upload_youtube(video_path, title, desc):
    print("Uploading to YouTube...", flush=True)
    tf = "token.json"
    if not os.path.exists(tf) and os.environ.get("YOUTUBE_TOKEN_JSON"):
        with open(tf, "w", encoding="utf-8") as f:
            f.write(os.environ["YOUTUBE_TOKEN_JSON"])
    creds = Credentials.from_authorized_user_file(tf, ["https://www.googleapis.com/auth/youtube.upload"])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds)

    now = datetime.datetime.now(datetime.timezone.utc)
    pub = now.replace(hour=11, minute=0, second=0, microsecond=0)
    if pub <= now + datetime.timedelta(minutes=15):
        pub += datetime.timedelta(days=1)

    body = {
        "snippet": {
            "title": title[:95],
            "description": desc + "\n\n#why #stickman #psychology #sciencefacts",
            "tags": ["why", "stickman animation", "psychology", "science explained"],
            "categoryId": "27",
        },
        "status": {
            "privacyStatus
