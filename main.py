import os
import json
import asyncio
import datetime
import subprocess
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
client = genai.Client(api_key=GEMINI_KEY)

# 1. SSENARIY VA VIDIQ (95-100 BALL) SEO GENERATSIYASI
def generate_plan_and_seo() -> dict:
    prompt = """
    Sen Stickman YouTube kanali prodyuseri va vidIQ SEO ekspertisan.
    Bugungi kun uchun qiziqarli, dinamik stickman qisqa hikoya/sarguzasht g'oyasi va vidIQ shkalasida 95-100 ball oladigan SEO yarat.
    Qoidalar:
    - story_narration: 60-90 soniyalik qiziqarli hikoya matni (o'zbek tilida, jonli va intrigali).
    - scene_prompts: Hikoyaga mos 4 ta inglizcha stickman rasm/video prompti.
    - title: 50-60 belgi, asosiy kalit so'z boshida, CTR yuqori.
    - description: Birinchi 2 qatorda asosiy kalit so'zlar takrorlansin, kamida 200 so'z, teglar tabiiy singdirilgan.
    - tags: 15-20 ta kalit so'z ro'yxati (umumiy 450-500 belgi).
    - thumbnail_text: Thumbnail uchun 2-3 ta portlovchi so'z (KATTA HARFLARDA).
    - thumbnail_prompt: Stickman uslubida yorqin, emotsional fon rasmi uchun inglizcha prompt (matnsiz).

    Faqat quyidagi JSON formatda javob ber:
    {"story_narration": "...", "scene_prompts": ["...", "...", "...", "..."], "title": "...", "description": "...", "tags": ["..."], "thumbnail_text": "...", "thumbnail_prompt": "..."}
    """
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )
    return json.loads(resp.text)

# 2. OVOZLASHTIRISH (100% BEPUL EDGE-TTS)
async def create_voiceover(text: str, out_audio="voice.mp3"):
    communicate = edge_tts.Communicate(text, voice="uz-UZ-SardorNeural", rate="+5%")
    await communicate.save(out_audio)

# 3. GOOGLE FLOW ORQALI VIDEO OLISH (ZAXIRA STICKMAN GENERATOR BILAN)
def generate_visuals(scene_prompts: list) -> list:
    video_clips = []
    if os.path.exists("flow_cookies.json"):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context()
                with open("flow_cookies.json", "r", encoding="utf-8") as f:
                    context.add_cookies(json.load(f))
                page = context.new_page()
                page.goto("https://flow.google.com", timeout=60000)
                page.wait_for_timeout(5000)
                textarea = page.locator("textarea").first
                if textarea.is_visible(timeout=8000):
                    textarea.fill(scene_prompts[0] + ", 2d stickman animation, clean white background")
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(45000)
                    video_el = page.locator("video").first
                    if video_el.is_visible(timeout=15000):
                        src = video_el.get_attribute("src")
                        if src and src.startswith("http"):
                            with open("flow_clip.mp4", "wb") as vf:
                                vf.write(requests.get(src).content)
                            video_clips.append("flow_clip.mp4")
                browser.close()
        except Exception as e:
            print(f"Flow AI o'tkazib yuborildi (zaxira stickman generator ishlaydi): {e}")

    # Agar Flow AI dan video olinmasa, 4 ta stickman kadr yaratib dinamik videoga aylantiramiz
    if not video_clips:
        for idx, sp in enumerate(scene_prompts):
            img_url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(sp + ', 2d stickman comic animation style, bold black lines, vibrant background, 16:9')}?width=1280&height=720&nologo=true"
            img_path = f"scene_{idx}.jpg"
            with open(img_path, "wb") as f:
                f.write(requests.get(img_url, timeout=60).content)
            clip_path = f"clip_{idx}.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-i", img_path,
                "-vf", "scale=1920:1080,zoompan=z='min(zoom+0.001,1.15)':d=200:s=1280x720",
                "-t", "8", "-c:v", "libx264", "-pix_fmt", "yuv420p", clip_path
            ], check=True)
            video_clips.append(clip_path)

    return video_clips

# 4. AVTOMATIK MONTAJ (FFMPEG)
def assemble_video(clips: list, audio_path="voice.mp3", output_video="final_video.mp4"):
    with open("clips.txt", "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{c}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "clips.txt",
        "-c", "copy", "merged_raw.mp4"
    ], check=True)

    subprocess.run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", "merged_raw.mp4",
        "-i", audio_path, "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", output_video
    ], check=True)
    return output_video

# 5. THUMBNAIL YARATISH
def create_thumbnail(image_prompt: str, overlay_text: str, output_path="thumbnail.jpg"):
    url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(image_prompt + ', stickman 2d animation style, dramatic lighting, high contrast, youtube thumbnail, no text')}?width=1280&height=720&nologo=true"
    with open("raw_bg.jpg", "wb") as f:
        f.write(requests.get(url, timeout=60).content)

    img = Image.open("raw_bg.jpg").convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 95)
    except:
        font = ImageFont.load_default()

    draw.text((60, 520), overlay_text, font=font, fill="#FFE600", stroke_width=8, stroke_fill="#000000")
    img.save(output_path, quality=95)
    return output_path

# 6. YOUTUBE'GA YUKLASH VA SOAT 16:00 (UTC+5) GA REJALASHTIRISH
def upload_to_youtube(video_path: str, thumb_path: str, seo_data: dict):
    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl"
    ]
    creds = Credentials.from_authorized_user_file("token.json", scopes)
    youtube = build("youtube", "v3", credentials=creds)

    # Toshkent vaqti 16:00 (UTC+5) = UTC 11:00
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    publish_time = now_utc.replace(hour=11, minute=0, second=0, microsecond=0)
    if now_utc >= publish_time:
        publish_time += datetime.timedelta(days=1)

    body = {
        "snippet": {
            "title": seo_data["title"][:100],
            "description": seo_data["description"],
            "tags": seo_data["tags"],
            "categoryId": "24"
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_time.isoformat(),
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    video_id = response["id"]

    youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumb_path)).execute()
    print(f"MUVAFFAQIYATLI YUKLANDI! Video ID: {video_id} | Rejalashtirilgan vaqt (UTC): {publish_time.isoformat()}")

if __name__ == "__main__":
    plan = generate_plan_and_seo()
    asyncio.run(create_voiceover(plan["story_narration"]))
    clips = generate_visuals(plan["scene_prompts"])
    final_vid = assemble_video(clips)
    thumb = create_thumbnail(plan["thumbnail_prompt"], plan["thumbnail_text"])
    upload_to_youtube(final_vid, thumb, plan)
