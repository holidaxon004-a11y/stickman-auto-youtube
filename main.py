import os
import json
import time
import math
import random
import asyncio
import datetime
import subprocess
from PIL import Image, ImageDraw
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import edge_tts

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = (
    "Siz professional 'Nima uchun?' (ilm-fan, psixologiya, inson miyasi va hayotiy qiziqarli faktlar) mavzusidagi Stickman video rejissyori va ssenariynavisisiz. "
    "Sizning vazifangiz — bitta qiziqarli 'Nima uchun...?' mavzusini tanlash va uni 8 sahnadan iborat (~60 soniyalik) dinamik stickman video paketi ko'rinishida tayyorlash. "
    "QOIDALAR: "
    "1. Mavzu: Odamlar o'ziga beradigan, lekin javobini bilmaydigan qiziqarli savol. "
    "2. O'zbekcha matn (narration_uz): Har bir sahna uchun 14-22 so'zdan iborat, do'stona, jonli, og'zaki o'zbek tilida ('siz' shaklida) yozilsin. Uydirma statistika ishlatmang. "
    "3. Har bir sahna uchun mos poza (pose) tanlang: 'think', 'shock', 'run', 'idea', 'brain', 'point', 'tired', 'happy'. "
    "4. Kamera harakati (camera_move): 'zoom_in', 'zoom_out', 'pan_right', 'pan_left', 'impact_shake' dan birini tanlang. "
    "FAQAT quyidagi JSON formatda javob qaytaring: "
    '{"title_uz": "YouTube sarlavha", "description_uz": "Tavsif", "scenes": [{"scene_number": 1, "narration_uz": "Matn", "pose": "think", "camera_move": "zoom_in"}]}'
)


def generate_script():
    models_to_try = [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-2.5-pro",
    ]
    last_err = None
    for model_name in models_to_try:
        try:
            print("1. Model sinab ko'rilmoqda:", model_name, flush=True)
            response = client.models.generate_content(
                model=model_name,
                contents="Yangi, juda qiziqarli va hayotiy 'Nima uchun...?' mavzusida 8 sahnalik stickman video ssenariysini yarat.",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.8,
                ),
            )
            print("Muvaffaqiyatli! Ishlatilgan model:", model_name, flush=True)
            return json.loads(response.text)
        except Exception as e:
            print(model_name, "xato berdi:", e, flush=True)
            last_err = e
            time.sleep(3)
    raise RuntimeError("Hech bir model ishlamadi: " + str(last_err))


def wobble_line(draw, pts, fill=(20, 20, 20), width=10):
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        steps = max(int(math.hypot(x2 - x1, y2 - y1) / 18), 2)
        seg = []
        for s in range(steps + 1):
            t = s / steps
            jitter = 0 if (s == 0 or s == steps) else random.uniform(-1.8, 1.8)
            seg.append((x1 + (x2 - x1) * t + jitter, y1 + (y2 - y1) * t + jitter))
        draw.line(seg, fill=fill, width=width, joint="curve")


def draw_stickman_scene(pose, scene_idx, output_path):
    random.seed(scene_idx * 97)
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), (252, 252, 250))
    draw = ImageDraw.Draw(img)

    black = (22, 22, 24)
    accent = (232, 68, 42)

    wobble_line(draw, [(260, 880), (1660, 880)], fill=black, width=8)

    cx = 860 if pose in ("point", "brain", "idea") else 960
    head_y = 330
    r = 85

    lean = -35 if pose == "shock" else (45 if pose == "run" else (25 if pose == "tired" else 0))
    hx = cx + lean
    hy = head_y + (35 if pose == "tired" else 0)

    for off in range(-2, 3):
        draw.ellipse(
            [hx - r + off, hy - r - off, hx + r - off, hy + r + off],
            outline=black,
            width=10,
        )

    eye_shift = 18 if pose in ("point", "idea", "brain") else 0
    draw.ellipse([hx - 32 + eye_shift, hy - 18, hx - 16 + eye_shift, hy - 2], fill=black)
    draw.ellipse([hx + 16 + eye_shift, hy - 18, hx + 32 + eye_shift, hy - 2], fill=black)

    if pose == "shock":
        draw.ellipse([hx - 16, hy + 18, hx + 16, hy + 52], outline=black, width=8)
    elif pose == "tired":
        wobble_line(draw, [(hx - 28, hy + 38), (hx, hy + 24), (hx + 28, hy + 38)], fill=black, width=8)
    else:
        draw.arc([hx - 30, hy + 8, hx + 30, hy + 46], start=15, end=165, fill=black, width=8)

    neck = (hx, hy + r)
    hip = (cx, 650)
    wobble_line(draw, [neck, ((neck[0] + hip[0]) // 2 + lean // 3, 530), hip], fill=black, width=11)

    shoulder = (hx + lean // 4, hy + r + 45)

    if pose == "think":
        wobble_line(draw, [shoulder, (hx - 95, 520), (hx - 35, hy + r - 10)], fill=black, width=10)
        wobble_line(draw, [shoulder, (cx + 95, 540), (cx + 45, 640)], fill=black, width=10)
        wobble_line(draw, [hip, (cx - 65, 770), (cx - 75, 880)], fill=black, width=11)
        wobble_line(draw, [hip, (cx + 65, 770), (cx + 75, 880)], fill=black, width=11)
        draw.arc([hx + 135, hy - 140, hx + 225, hy - 40], start=180, end=45, fill=accent, width=14)
        wobble_line(draw, [(hx + 215, hy - 55), (hx + 180, hy - 10)], fill=accent, width=14)
        draw.ellipse([hx + 170, hy + 8, hx + 190, hy + 28], fill=accent)

    elif pose == "shock":
        wobble_line(draw, [shoulder, (hx - 130, 360), (hx - 150, 260)], fill=black, width=10)
        wobble_line(draw, [shoulder, (hx + 130, 360), (hx + 150, 260)], fill=black, width=10)
        wobble_line(draw, [hip, (cx - 95, 765), (cx - 110, 880)], fill=black, width=11)
        wobble_line(draw, [hip, (cx + 85, 765), (cx + 95, 880)], fill=black, width=11)
        for bx, by in [(hx - 175, hy - 90), (hx + 175, hy - 90), (hx, hy - 155)]:
            wobble_line(draw, [(bx - 25, by - 25), (bx + 25, by + 25)], fill=accent, width=11)
            wobble_line(draw, [(bx + 25, by - 25), (bx - 25, by + 25)], fill=accent, width=11)

    elif pose == "run":
        wobble_line(draw, [shoulder, (hx + 120, 440), (hx + 190, 390)], fill=black, width=10)
        wobble_line(draw, [shoulder, (hx - 110, 500), (hx - 160, 560)], fill=black, width=10)
        wobble_line(draw, [hip, (cx + 120, 740), (cx + 185, 865)], fill=black, width=11)
        wobble_line(draw, [hip, (cx - 110, 750), (cx - 185, 845)], fill=black, width=11)
        for sy in [330, 430, 540, 640]:
            wobble_line(draw, [(420, sy), (640, sy)], fill=accent, width=10)

    elif pose in ("idea", "brain"):
        wobble_line(draw, [shoulder, (hx + 125, 420), (hx + 185, 310)], fill=black, width=10)
        wobble_line(draw, [shoulder, (cx - 85, 540), (cx - 55, 640)], fill=black, width=10)
        wobble_line(draw, [hip, (cx - 65, 770), (cx - 75, 880)], fill=black, width=11)
        wobble_line(draw, [hip, (cx + 65, 770), (cx + 75, 880)], fill=black, width=11)
        bx, by = hx + 250, 270
        draw.ellipse([bx - 55, by - 55, bx + 55, by + 55], outline=accent, width=13)
        wobble_line(draw, [(bx - 25, by + 55), (bx + 25, by + 55)], fill=black, width=10)
        for ang in range(0, 360, 45):
            rad = math.radians(ang)
            wobble_line(
                draw,
                [(bx + math.cos(rad) * 75, by + math.sin(rad) * 75),
                 (bx + math.cos(rad) * 110, by + math.sin(rad) * 110)],
                fill=accent,
                width=10,
            )

    elif pose == "point":
        wobble_line(draw, [shoulder, (hx + 150, 450), (hx + 270, 430)], fill=black, width=10)
        wobble_line(draw, [shoulder, (cx - 85, 540), (cx - 55, 640)], fill=black, width=10)
        wobble_line(draw, [hip, (cx - 65, 770), (cx - 75, 880)], fill=black, width=11)
        wobble_line(draw, [hip, (cx + 65, 770), (cx + 75, 880)], fill=black, width=11)
        tx, ty = 1320, 430
        draw.ellipse([tx - 95, ty - 95, tx + 95, ty + 95], outline=black, width=10)
        draw.ellipse([tx - 45, ty - 45, tx + 45, ty + 45], outline=accent, width=12)
        draw.ellipse([tx - 14, ty - 14, tx + 14, ty + 14], fill=accent)

    else:
        wobble_line(draw, [shoulder, (cx - 95, 560), (cx - 85, 660)], fill=black, width=10)
        wobble_line(draw, [shoulder, (cx + 95, 560), (cx + 85, 660)], fill=black, width=10)
        wobble_line(draw, [hip, (cx - 65, 770), (cx - 75, 880)], fill=black, width=11)
        wobble_line(draw, [hip, (cx + 65, 770), (cx + 75, 880)], fill=black, width=11)
        draw.ellipse([hx + 140, hy - 110, hx + 210, hy - 40], outline=accent, width=12)

    img.save(output_path, "PNG")
    print("   Stickman sahna chizildi (" + pose + ")", flush=True)


async def generate_voice(text_uz, output_path):
    communicate = edge_tts.Communicate(text_uz, "uz-UZ-SardorNeural", rate="+5%")
    await communicate.save(output_path)


def get_audio_duration(audio_path):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    return float(subprocess.check_output(cmd).decode().strip())


def create_scene_clip(img_path, audio_path, move, clip_path):
    duration = get_audio_duration(audio_path) + 0.4
    frames = int(duration * 30)
    f_str = str(frames)

    if move == "zoom_in":
        zoom_expr = "zoom='min(zoom+0.0015,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif move == "zoom_out":
        zoom_expr = "zoom='if(lte(zoom,1.0),1.25,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif move == "pan_right":
        zoom_expr = "zoom='1.15':x='(iw-iw/zoom)*(on/" + f_str + ")':y='ih/2-(ih/zoom/2)'"
    elif move == "pan_left":
        zoom_expr = "zoom='1.15':x='(iw-iw/zoom)*(1-on/" + f_str + ")':y='ih/2-(ih/zoom/2)'"
    else:
        zoom_expr = "zoom='1.12':x='iw/2-(iw/zoom/2)+sin(on*0.8)*8':y='ih/2-(ih/zoom/2)+cos(on*0.8)*6'"

    vf = (
        "scale=2560:1440,zoompan="
        + zoom_expr
        + ":d="
        + f_str
        + ":s=1280x720:fps=30,format=yuv420p"
    )

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            img_path,
            "-i",
            audio_path,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            str(duration),
            clip_path,
        ],
        check=True,
    )


def upload_to_youtube(video_path, title, description):
    print("YouTube'ga yuklash boshlandi...", flush=True)
    token_file = None
    for candidate in ["token.json", "youtube_token.json"]:
        if os.path.exists(candidate):
            token_file = candidate
            break

    if not token_file and os.environ.get("YOUTUBE_TOKEN_JSON"):
        token_file = "token.json"
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(os.environ["YOUTUBE_TOKEN_JSON"])

    if not token_file:
        raise RuntimeError("YouTube token fayli topilmadi (token.json).")

    creds = Credentials.from_authorized_user_file(
        token_file, ["https://www.googleapis.com/auth/youtube.upload"]
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    youtube = build("youtube", "v3", credentials=creds)

    # Toshkent vaqti (UTC+5) bilan soat 16:00 ga rejalashtirish (16:00 UZT = 11:00 UTC)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    publish_utc = now_utc.replace(hour=11, minute=0, second=0, microsecond=0)
    if publish_utc <= now_utc + datetime.timedelta(minutes=15):
        publish_utc = publish_utc + datetime.timedelta(days=1)
    publish_at = publish_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    body = {
        "snippet": {
            "title": title[:95],
            "description": description + "\n\n#nimauchun #stickman #qiziqarlifaktlar #ilm",
            "tags": ["nima uchun", "stickman", "qiziqarli faktlar", "psixologiya", "ilm fan"],
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print("Yuklanmoqda:", int(status.progress() * 100), "%", flush=True)

    print("MUVAFFAQIYATLI YUKLANDI! Video ID:", response.get("id"), flush=True)
    print("Rejalashtirilgan vaqt (UTC):", publish_at, "(Toshkent 16:00)", flush=True)


def main():
    os.makedirs("build", exist_ok=True)
    pack = generate_script()
    print("Mavzu tanlandi:", pack["title_uz"], flush=True)

    clip_files = []
    total = len(pack["scenes"])
    poses_cycle = ["think", "shock", "brain", "run", "point", "idea", "tired", "happy"]

    for idx, scene in enumerate(pack["scenes"], start=1):
        print("--- Sahna", idx, "/", total, "tayyorlanmoqda ---", flush=True)
        img_path = "build/scene_" + str(idx) + ".png"
        aud_path = "build/scene_" + str(idx) + ".mp3"
        clip_path = "build/clip_" + str(idx) + ".mp4"

        pose = scene.get("pose") or poses_cycle[(idx - 1) % len(poses_cycle)]
        draw_stickman_scene(pose, idx, img_path)
        asyncio.run(generate_voice(scene["narration_uz"], aud_path))
        create_scene_clip(img_path, aud_path, scene.get("camera_move", "zoom_in"), clip_path)
        clip_files.append(clip_path)

    concat_list = "build/clips.txt"
    with open(concat_list, "w") as f:
        for c in clip_files:
            f.write("file '" + os.path.abspath(c) + "'\n")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list,
            "-c",
            "copy",
            "final_video.mp4",
        ],
        check=True,
    )

    print("TAYYOR! Video muvaffaqiyatli yig'ildi: final_video.mp4", flush=True)
    upload_to_youtube("final_video.mp4", pack["title_uz"], pack["description_uz"])


if __name__ == "__main__":
    main()
