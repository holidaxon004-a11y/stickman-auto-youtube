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
    "You are a professional 'Why?' (science, psychology, human brain, and fascinating everyday mysteries) Stickman video director and scriptwriter. "
    "Your task is to pick one compelling 'Why...?' topic and create a deep, engaging 35-scene (~4-minute) stickman video script in natural conversational English. "
    "RULES: "
    "1. Topic: A fascinating question people wonder about with a surprising scientific or psychological explanation (e.g., 'Why Does Your Brain Make You Procrastinate?', 'Why Do You Forget Why You Walked Into a Room?'). "
    "2. Scene count: Strictly 35 scenes (hook, relatable problem, brain/body mechanism, real-life examples, surprising facts, and strong takeaway). "
    "3. English narration (narration_en): 12-18 words per scene, friendly, vivid, spoken conversational English addressing the viewer as 'you'. Do not invent fake statistics or studies. "
    "4. Choose a fitting pose for each scene: 'think', 'shock', 'run', 'idea', 'brain', 'point', 'tired', 'happy'. "
    "5. Choose a camera_move: 'zoom_in', 'zoom_out', 'pan_right', 'pan_left', 'impact_shake'. "
    "Return ONLY valid JSON in this exact format: "
    '{"title_en": "Catchy YouTube Title (Why...?)", "description_en": "Engaging video description", "scenes": [{"scene_number": 1, "narration_en": "Spoken English narration", "pose": "think", "camera_move": "zoom_in"}]}'
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
            print("1. Trying model:", model_name, flush=True)
            response = client.models.generate_content(
                model=model_name,
                contents="Create a brand-new, fascinating, relatable 'Why...?' 35-scene stickman video script in English.",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.8,
                ),
            )
            data = json.loads(response.text)
            if len(data.get("scenes", [])) >= 15:
                print("Success! Model used:", model_name, "Scenes:", len(data["scenes"]), flush=True)
                return data
        except Exception as e:
            print(model_name, "failed:", e, flush=True)
            last_err = e
            time.sleep(3)
    raise RuntimeError("No working model found: " + str(last_err))


def wobble_line(draw, pts, fill=(20, 20, 20), width=9, seed=1):
    rng = random.Random(seed)
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        steps = max(int(math.hypot(x2 - x1, y2 - y1) / 22), 2)
        seg = []
        for s in range(steps + 1):
            t = s / steps
            jitter = 0 if (s == 0 or s == steps) else rng.uniform(-1.3, 1.3)
            seg.append((x1 + (x2 - x1) * t + jitter, y1 + (y2 - y1) * t + jitter))
        draw.line(seg, fill=fill, width=width, joint="curve")


def draw_stickman_frame(pose, scene_idx, frame_idx, output_path):
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), (252, 252, 250))
    draw = ImageDraw.Draw(img)

    black = (22, 22, 24)
    accent = (232, 68, 42)
    phase = frame_idx * 0.45
    bob = int(math.sin(phase) * 7)
    arm_wave = int(math.cos(phase) * 18)
    seed = scene_idx * 100 + (frame_idx % 3)

    # Whiteboard ground line
    wobble_line(draw, [(160, 590), (1120, 590)], fill=black, width=6, seed=scene_idx)

    cx = 560 if pose in ("point", "brain", "idea") else 640
    if pose == "run":
        cx += int(math.sin(phase * 0.5) * 25)

    lean = -24 if pose == "shock" else (30 if pose == "run" else (18 if pose == "tired" else 0))
    hx = cx + lean
    hy = 220 + bob + (22 if pose == "tired" else 0)
    r = 56

    # Head
    draw.ellipse([hx - r, hy - r, hx + r, hy + r], outline=black, width=7)

    # Eyes
    eye_shift = 12 if pose in ("point", "idea", "brain") else 0
    draw.ellipse([hx - 22 + eye_shift, hy - 12, hx - 10 + eye_shift, hy], fill=black)
    draw.ellipse([hx + 10 + eye_shift, hy - 12, hx + 22 + eye_shift, hy], fill=black)

    # Talking mouth animation
    talk_open = abs(int(math.sin(frame_idx * 1.1) * 14))
    if pose == "shock":
        draw.ellipse([hx - 12, hy + 12, hx + 12, hy + 34 + talk_open // 2], outline=black, width=6)
    elif talk_open > 6:
        draw.ellipse([hx - 14, hy + 12, hx + 14, hy + 16 + talk_open], outline=black, width=5)
    else:
        draw.arc([hx - 20, hy + 6, hx + 20, hy + 30], start=15, end=165, fill=black, width=6)

    # Torso
    neck = (hx, hy + r)
    hip = (cx, 435 + bob // 2)
    wobble_line(draw, [neck, ((neck[0] + hip[0]) // 2 + lean // 3, 355), hip], fill=black, width=8, seed=seed)
    shoulder = (hx + lean // 4, hy + r + 28)

    if pose == "think":
        wobble_line(draw, [shoulder, (hx - 65, 345), (hx - 22, hy + r - 6)], fill=black, width=7, seed=seed)
        wobble_line(draw, [shoulder, (cx + 65, 360 + arm_wave // 2), (cx + 35, 425)], fill=black, width=7, seed=seed)
        wobble_line(draw, [hip, (cx - 45, 515), (cx - 50, 590)], fill=black, width=8, seed=seed)
        wobble_line(draw, [hip, (cx + 45, 515), (cx + 50, 590)], fill=black, width=8, seed=seed)
        qy = hy - 95 + bob
        draw.arc([hx + 90, qy, hx + 150, qy + 65], start=180, end=45, fill=accent, width=10)
        wobble_line(draw, [(hx + 142, qy + 55), (hx + 120, qy + 85)], fill=accent, width=10, seed=seed)
        draw.ellipse([hx + 114, qy + 96, hx + 128, qy + 110], fill=accent)

    elif pose == "shock":
        wobble_line(draw, [shoulder, (hx - 90, 240 - arm_wave), (hx - 105, 170 - arm_wave)], fill=black, width=7, seed=seed)
        wobble_line(draw, [shoulder, (hx + 90, 240 - arm_wave), (hx + 105, 170 - arm_wave)], fill=black, width=7, seed=seed)
        wobble_line(draw, [hip, (cx - 65, 515), (cx - 75, 590)], fill=black, width=8, seed=seed)
        wobble_line(draw, [hip, (cx + 60, 515), (cx + 65, 590)], fill=black, width=8, seed=seed)
        burst = 14 + abs(arm_wave) // 2
        for bx, by in [(hx - 115, hy - 60), (hx + 115, hy - 60), (hx, hy - 105)]:
            wobble_line(draw, [(bx - burst, by - burst), (bx + burst, by + burst)], fill=accent, width=8, seed=seed)
            wobble_line(draw, [(bx + burst, by - burst), (bx - burst, by + burst)], fill=accent, width=8, seed=seed)

    elif pose == "run":
        swing = int(math.sin(phase * 1.4) * 55)
        wobble_line(draw, [shoulder, (hx + 65 - swing // 2, 295), (hx + 110 - swing, 260)], fill=black, width=7, seed=seed)
        wobble_line(draw, [shoulder, (hx - 65 + swing // 2, 315), (hx - 105 + swing, 355)], fill=black, width=7, seed=seed)
        wobble_line(draw, [hip, (cx + 55 + swing // 2, 505), (cx + 95 + swing, 585)], fill=black, width=8, seed=seed)
        wobble_line(draw, [hip, (cx - 55 - swing // 2, 505), (cx - 95 - swing, 580)], fill=black, width=8, seed=seed)
        for sy in [220, 290, 360, 430]:
            shift_x = (frame_idx * 25) % 90
            wobble_line(draw, [(280 - shift_x, sy), (420 - shift_x, sy)], fill=accent, width=7, seed=seed)

    elif pose in ("idea", "brain"):
        wobble_line(draw, [shoulder, (hx + 85, 280 - arm_wave // 2), (hx + 125, 205 - arm_wave)], fill=black, width=7, seed=seed)
        wobble_line(draw, [shoulder, (cx - 55, 360), (cx - 35, 425)], fill=black, width=7, seed=seed)
        wobble_line(draw, [hip, (cx - 45, 515), (cx - 50, 590)], fill=black, width=8, seed=seed)
        wobble_line(draw, [hip, (cx + 45, 515), (cx + 50, 590)], fill=black, width=8, seed=seed)
        bx, by = hx + 170, 180 + bob
        draw.ellipse([bx - 36, by - 36, bx + 36, by + 36], outline=accent, width=9)
        wobble_line(draw, [(bx - 16, by + 36), (bx + 16, by + 36)], fill=black, width=7, seed=seed)
        ray_len = 65 + abs(arm_wave)
        for ang in range(0, 360, 45):
            rad = math.radians(ang + frame_idx * 6)
            wobble_line(
                draw,
                [(bx + math.cos(rad) * 48, by + math.sin(rad) * 48),
                 (bx + math.cos(rad) * ray_len, by + math.sin(rad) * ray_len)],
                fill=accent,
                width=7,
                seed=seed,
            )

    elif pose == "point":
        wobble_line(draw, [shoulder, (hx + 100, 300), (hx + 185, 285 + arm_wave // 2)], fill=black, width=7, seed=seed)
        wobble_line(draw, [shoulder, (cx - 55, 360), (cx - 35, 425)], fill=black, width=7, seed=seed)
        wobble_line(draw, [hip, (cx - 45, 515), (cx - 50, 590)], fill=black, width=8, seed=seed)
        wobble_line(draw, [hip, (cx + 45, 515), (cx + 50, 590)], fill=black, width=8, seed=seed)
        tx, ty = 880, 285
        pulse = abs(arm_wave) // 2
        draw.ellipse([tx - 62 - pulse, ty - 62 - pulse, tx + 62 + pulse, ty + 62 + pulse], outline=black, width=7)
        draw.ellipse([tx - 30, ty - 30, tx + 30, ty + 30], outline=accent, width=8)
        draw.ellipse([tx - 10, ty - 10, tx + 10, ty + 10], fill=accent)

    else:
        wobble_line(draw, [shoulder, (cx - 65, 375 - arm_wave), (cx - 95, 320 - arm_wave)], fill=black, width=7, seed=seed)
        wobble_line(draw, [shoulder, (cx + 65, 375 + arm_wave), (cx + 95, 320 + arm_wave)], fill=black, width=7, seed=seed)
        wobble_line(draw, [hip, (cx - 45, 515), (cx - 50, 590)], fill=black, width=8, seed=seed)
        wobble_line(draw, [hip, (cx + 45, 515), (cx + 50, 590)], fill=black, width=8, seed=seed)
        pulse = abs(arm_wave) // 3
        draw.ellipse([hx + 95 - pulse, hy - 75 - pulse, hx + 140 + pulse, hy - 30 + pulse], outline=accent, width=8)

    img.save(output_path, "PNG")


async def generate_voice(text_en, output_path):
    communicate = edge_tts.Communicate(text_en, "en-US-AndrewNeural", rate="+4%")
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


def create_animated_scene_clip(pose, scene_idx, audio_path, move, clip_path):
    duration = get_audio_duration(audio_path) + 0.35
    anim_fps = 12
    total_anim_frames = max(int(duration * anim_fps), 12)
    frames_dir = f"build/frames_{scene_idx}"
    os.makedirs(frames_dir, exist_ok=True)

    for f_i in range(total_anim_frames):
        frame_file = f"{frames_dir}/f_{f_i:04d}.png"
        draw_stickman_frame(pose, scene_idx, f_i, frame_file)

    out_frames = int(duration * 30)
    f_str = str(out_frames)
    if move == "zoom_in":
        zoom_expr = "zoom='min(zoom+0.001,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif move == "zoom_out":
        zoom_expr = "zoom='if(lte(zoom,1.0),1.18,max(1.001,zoom-0.001))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif move == "pan_right":
        zoom_expr = "zoom='1.10':x='(iw-iw/zoom)*(on/" + f_str + ")':y='ih/2-(ih/zoom/2)'"
    elif move == "pan_left":
        zoom_expr = "zoom='1.10':x='(iw-iw/zoom)*(1-on/" + f_str + ")':y='ih/2-(ih/zoom/2)'"
    else:
        zoom_expr = "zoom='1.08':x='iw/2-(iw/zoom/2)+sin(on*0.7)*6':y='ih/2-(ih/zoom/2)+cos(on*0.7)*5'"

    vf = f"fps=30,zoompan={zoom_expr}:d=1:s=1280x720:fps=30,format=yuv420p"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(anim_fps),
            "-i",
            f"{frames_dir}/f_%04d.png",
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
    print("Starting YouTube upload...", flush=True)
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
        raise RuntimeError("YouTube token file not found (token.json).")

    creds = Credentials.from_authorized_user_file(
        token_file, ["https://www.googleapis.com/auth/youtube.upload"]
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    youtube = build("youtube", "v3", credentials=creds)

    # Schedule for 16:00 UZT (11:00 UTC)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    publish_utc = now_utc.replace(hour=11, minute=0, second=0, microsecond=0)
    if publish_utc <= now_utc + datetime.timedelta(minutes=15):
        publish_utc = publish_utc + datetime.timedelta(days=1)
    publish_at = publish_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    body = {
        "snippet": {
            "title": title[:95],
            "description": description + "\n\n#why #stickman #psychology #sciencefacts #explained",
            "tags": ["why", "stickman animation", "psychology facts", "science explained", "human brain"],
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
            print("Uploading:", int(status.progress() * 100), "%", flush=True)

    print("SUCCESSFULLY UPLOADED! Video ID:", response.get("id"), flush=True)


def main():
    os.makedirs("build", exist_ok=True)
    pack = generate_script()
    scenes = pack["scenes"][:35]
    print("Selected topic:", pack["title_en"], "| Total scenes:", len(scenes), flush=True)

    clip_files = []
    total = len(scenes)
    poses_cycle = ["think", "shock", "brain", "run", "point", "idea", "tired", "happy"]

    for idx, scene in enumerate(scenes, start=1):
        print("--- Rendering animated scene", idx, "/", total, "---", flush=True)
        aud_path = f"build/scene_{idx}.mp3"
        clip_path = f"build/clip_{idx}.mp4"

        pose = scene.get("pose") or poses_cycle[(idx - 1) % len(poses_cycle)]
        asyncio.run(generate_voice(scene["narration_en"], aud_path))
        create_animated_scene_clip(pose, idx, aud_path, scene.get("camera_move", "zoom_in"), clip_path)
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

    print("DONE! 35-scene animated video compiled: final_video.mp4", flush=True)
    upload_to_youtube("final_video.mp4", pack["title_en"], pack["description_en"])


if __name__ == "__main__":
    main()
