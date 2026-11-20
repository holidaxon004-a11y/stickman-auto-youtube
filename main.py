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

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

SYSTEM_PROMPT = (
    "You are a professional 'Why?' Stickman video scriptwriter. "
    "Pick one fascinating 'Why...?' science or psychology question and write a 35-scene English script. "
    "Each scene needs narration_en (12-18 words, conversational English), "
    "pose ('think', 'shock', 'run', 'idea', 'brain', 'point', 'tired', 'happy'), "
    "and camera_move ('zoom_in', 'zoom_out', 'pan_right', 'pan_left', 'impact_shake'). "
    'Return ONLY JSON: {"title_en": "Why...?", "description_en": "...", "scenes": [{"scene_number": 1, "narration_en": "...", "pose": "think", "camera_move": "zoom_in"}]}'
)


def generate_script():
    models = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-pro"]
    last_err = None
    for m in models:
        try:
            print("1. Trying model:", m, flush=True)
            resp = client.models.generate_content(
                model=m,
                contents="Create a fascinating 35-scene 'Why...?' stickman script in English.",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.8,
                ),
            )
            data = json.loads(resp.text)
            if len(data.get("scenes", [])) >= 15:
                print("Success:", m, "Scenes:", len(data["scenes"]), flush=True)
                return data
        except Exception as e:
            print(m, "failed:", e, flush=True)
            last_err = e
            time.sleep(3)
    raise RuntimeError("No model worked: " + str(last_err))


def wline(draw, pts, fill=(20, 20, 20), width=8, seed=1):
    rng = random.Random(seed)
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        steps = max(int(math.hypot(x2 - x1, y2 - y1) / 25), 2)
        seg = []
        for s in range(steps + 1):
            t = s / steps
            j = 0 if (s == 0 or s == steps) else rng.uniform(-1.2, 1.2)
            seg.append((x1 + (x2 - x1) * t + j, y1 + (y2 - y1) * t + j))
        draw.line(seg, fill=fill, width=width, joint="curve")


def draw_frame(pose, s_idx, f_idx, out_path):
    img = Image.new("RGB", (1280, 720), (252, 252, 250))
    d = ImageDraw.Draw(img)
    blk = (22, 22, 24)
    acc = (232, 68, 42)
    ph = f_idx * 0.45
    bob = int(math.sin(ph) * 7)
    wave = int(math.cos(ph) * 18)
    seed = s_idx * 100 + (f_idx % 3)

    wline(d, [(160, 590), (1120, 590)], fill=blk, width=6, seed=s_idx)

    cx = 560 if pose in ("point", "brain", "idea") else 640
    if pose == "run":
        cx += int(math.sin(ph * 0.5) * 25)

    lean = -24 if pose == "shock" else (30 if pose == "run" else (18 if pose == "tired" else 0))
    hx = cx + lean
    hy = 220 + bob + (22 if pose == "tired" else 0)
    r = 56

    d.ellipse([hx - r, hy - r, hx + r, hy + r], outline=blk, width=7)
    es = 12 if pose in ("point", "idea", "brain") else 0
    d.ellipse([hx - 22 + es, hy - 12, hx - 10 + es, hy], fill=blk)
    d.ellipse([hx + 10 + es, hy - 12, hx + 22 + es, hy], fill=blk)

    talk = abs(int(math.sin(f_idx * 1.1) * 14))
    if pose == "shock":
        d.ellipse([hx - 12, hy + 12, hx + 12, hy + 34 + talk // 2], outline=blk, width=6)
    elif talk > 6:
        d.ellipse([hx - 14, hy + 12, hx + 14, hy + 16 + talk], outline=blk, width=5)
    else:
        d.arc([hx - 20, hy + 6, hx + 20, hy + 30], start=15, end=165, fill=blk, width=6)

    neck = (hx, hy + r)
    hip = (cx, 435 + bob // 2)
    wline(d, [neck, ((neck[0] + hip[0]) // 2 + lean // 3, 355), hip], fill=blk, width=8, seed=seed)
    sh = (hx + lean // 4, hy + r + 28)

    if pose == "think":
        wline(d, [sh, (hx - 65, 345), (hx - 22, hy + r - 6)], fill=blk, width=7, seed=seed)
        wline(d, [sh, (cx + 65, 360 + wave // 2), (cx + 35, 425)], fill=blk, width=7, seed=seed)
        wline(d, [hip, (cx - 45, 515), (cx - 50, 590)], fill=blk, width=8, seed=seed)
        wline(d, [hip, (cx + 45, 515), (cx + 50, 590)], fill=blk, width=8, seed=seed)
        qy = hy - 95 + bob
        d.arc([hx + 90, qy, hx + 150, qy + 65], start=180, end=45, fill=acc, width=10)
        wline(d, [(hx + 142, qy + 55), (hx + 120, qy + 85)], fill=acc, width=10, seed=seed)
        d.ellipse([hx + 114, qy + 96, hx + 128, qy + 110], fill=acc)
    elif pose == "shock":
        wline(d, [sh, (hx - 90, 240 - wave), (hx - 105, 170 - wave)], fill=blk, width=7, seed=seed)
        wline(d, [sh, (hx + 90, 240 - wave), (hx + 105, 170 - wave)], fill=blk, width=7, seed=seed)
        wline(d, [hip, (cx - 65, 515), (cx - 75, 590)], fill=blk, width=8, seed=seed)
        wline(d, [hip, (cx + 60, 515), (cx + 65, 590)], fill=blk, width=8, seed=seed)
        b = 14 + abs(wave) // 2
        for bx, by in [(hx - 115, hy - 60), (hx + 115, hy - 60), (hx, hy - 105)]:
            wline(d, [(bx - b, by - b), (bx + b, by + b)], fill=acc, width=8, seed=seed)
            wline(d, [(bx + b, by - b), (bx - b, by + b)], fill=acc, width=8, seed=seed)
    elif pose == "run":
        sw = int(math.sin(ph * 1.4) * 55)
        wline(d, [sh, (hx + 65 - sw // 2, 295), (hx + 110 - sw, 260)], fill=blk, width=7, seed=seed)
        wline(d, [sh, (hx - 65 + sw // 2, 315), (hx - 105 + sw, 355)], fill=blk, width=7, seed=seed)
        wline(d, [hip, (cx + 55 + sw // 2, 505), (cx + 95 + sw, 585)], fill=blk, width=8, seed=seed)
        wline(d, [hip, (cx - 55 - sw // 2, 505), (cx - 95 - sw, 580)], fill=blk, width=8, seed=seed)
        for sy in [220, 290, 360, 430]:
            sx = (f_idx * 25) % 90
            wline(d, [(280 - sx, sy), (420 - sx, sy)], fill=acc, width=7, seed=seed)
    elif pose in ("idea", "brain"):
        wline(d, [sh, (hx + 85, 280 - wave // 2), (hx + 125, 205 - wave)], fill=blk, width=7, seed=seed)
        wline(d, [sh, (cx - 55, 360), (cx - 35, 425)], fill=blk, width=7, seed=seed)
        wline(d, [hip, (cx - 45, 515), (cx - 50, 590)], fill=blk, width=8, seed=seed)
        wline(d, [hip, (cx + 45, 515), (cx + 50, 590)], fill=blk, width=8, seed=seed)
        bx, by = hx + 170, 180 + bob
        d.ellipse([bx - 36, by - 36, bx + 36, by + 36], outline=acc, width=9)
        wline(d, [(bx - 16, by + 36), (bx + 16, by + 36)], fill=blk, width=7, seed=seed)
        rl = 65 + abs(wave)
        for ang in range(0, 360, 45):
            rad = math.radians(ang + f_idx * 6)
            wline(d, [(bx + math.cos(rad) * 48, by + math.sin(rad) * 48), (bx + math.cos(rad) * rl, by + math.sin(rad) * rl)], fill=acc, width=7, seed=seed)
    elif pose == "point":
        wline(d, [sh, (hx + 100, 300), (hx + 185, 285 + wave // 2)], fill=blk, width=7, seed=seed)
        wline(d, [sh, (cx - 55, 360), (cx - 35, 425)], fill=blk, width=7, seed=seed)
        wline(d, [hip, (cx - 45, 515), (cx - 50, 590)], fill=blk, width=8, seed=seed)
        wline(d, [hip, (cx + 45, 515), (cx + 50, 590)], fill=blk, width=8, seed=seed)
        tx, ty = 880, 285
        p = abs(wave) // 2
        d.ellipse([tx - 62 - p, ty - 62 - p, tx + 62 + p, ty + 62 + p], outline=blk, width=7)
        d.ellipse([tx - 30, ty - 30, tx + 30, ty + 30], outline=acc, width=8)
        d.ellipse([tx - 10, ty - 10, tx + 10, ty + 10], fill=acc)
    else:
        wline(d, [sh, (cx - 65, 375 - wave), (cx - 95, 320 - wave)], fill=blk, width=7, seed=seed)
        wline(d, [sh, (cx + 65, 375 + wave), (cx + 95, 320 + wave)], fill=blk, width=7, seed=seed)
        wline(d, [hip, (cx - 45, 515), (cx - 50, 590)], fill=blk, width=8, seed=seed)
        wline(d, [hip, (cx + 45, 515), (cx + 50, 590)], fill=blk, width=8, seed=seed)
        p = abs(wave) // 3
        d.ellipse([hx + 95 - p, hy - 75 - p, hx + 140 + p, hy - 30 + p], outline=acc, width=8)

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
                await asyncio.sleep(1.5)
                return
        except Exception as e:
            print("Voice retry", attempt + 1, e, flush=True)
            last_err = e
            await asyncio.sleep(4)
    raise RuntimeError("TTS failed: " + str(last_err))


def get_duration(audio_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
    return float(subprocess.check_output(cmd).decode().strip())


def make_clip(pose, s_idx, aud_path, move, clip_path):
    dur = get_duration(aud_path) + 0.35
    fps = 12
    n_frames = max(int(dur * fps), 12)
    fdir = f"build/frames_{s_idx}"
    os.makedirs(fdir, exist_ok=True)
    for i in range(n_frames):
        draw_frame(pose, s_idx, i, f"{fdir}/f_{i:04d}.png")

    f_str = str(int(dur * 30))
    if move == "zoom_in":
        z = "zoom='min(zoom+0.001,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif move == "zoom_out":
        z = "zoom='if(lte(zoom,1.0),1.18,max(1.001,zoom-0.001))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif move == "pan_right":
        z = "zoom='1.10':x='(iw-iw/zoom)*(on/" + f_str + ")':y='ih/2-(ih/zoom/2)'"
    elif move == "pan_left":
        z = "zoom='1.10':x='(iw-iw/zoom)*(1-on/" + f_str + ")':y='ih/2-(ih/zoom/2)'"
    else:
        z = "zoom='1.08':x='iw/2-(iw/zoom/2)+sin(on*0.7)*6':y='ih/2-(ih/zoom/2)+cos(on*0.7)*5'"

    vf = f"fps=30,zoompan={z}:d=1:s=1280x720:fps=30,format=yuv420p"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", f"{fdir}/f_%04d.png", "-i", aud_path, "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "aac", "-b:a", "192k", "-t", str(dur), clip_path],
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
            "privacyStatus": "private",
            "publishAt": pub.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st:
            print("Progress:", int(st.progress() * 100), "%", flush=True)
    print("UPLOADED! Video ID:", resp.get("id"), flush=True)


def main():
    os.makedirs("build", exist_ok=True)
    pack = generate_script()
    scenes = pack["scenes"][:35]
    print("Topic:", pack["title_en"], "| Scenes:", len(scenes), flush=True)

    clips = []
    poses = ["think", "shock", "brain", "run", "point", "idea", "tired", "happy"]
    for idx, sc in enumerate(scenes, start=1):
        print(f"--- Scene {idx}/{len(scenes)} ---", flush=True)
        aud = f"build/scene_{idx}.mp3"
        clp = f"build/clip_{idx}.mp4"
        pose = sc.get("pose") or poses[(idx - 1) % len(poses)]
        asyncio.run(generate_voice(sc["narration_en"], aud))
        make_clip(pose, idx, aud, sc.get("camera_move", "zoom_in"), clp)
        clips.append(clp)

    with open("build/clips.txt", "w") as f:
        for c in clips:
            f.write("file '" + os.path.abspath(c) + "'\n")

    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "build/clips.txt", "-c", "copy", "final_video.mp4"], check=True)
    print("DONE: final_video.mp4", flush=True)
    upload_youtube("final_video.mp4", pack["title_en"], pack["description_en"])


if __name__ == "__main__":
    main()
