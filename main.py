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
        swing = int(math.sin(phase * 1.
