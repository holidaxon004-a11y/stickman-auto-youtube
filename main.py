import os
import json
import time
import shutil
import asyncio
import requests
import subprocess
from google import genai
from google.genai import types
import edge_tts

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

STYLE_LOCK = (
    "Classic whiteboard stickman animation. Completely flat, uniform, digitally clean white paper background "
    "with faint paper grain and no gradient, no vignette, no drop shadow, no three-dimensional surface. "
    "All figures and objects are drawn in solid black hand-drawn marker line, uniform medium-thick stroke weight "
    "throughout, with slightly imperfect wobbling hand-drawn edges and visible marker tip texture. "
    "Stick figures: a plain circle head, a single line torso that bends under force, two line arms, two line legs, "
    "simple rounded joints, no neck, no hands, no feet. Minimal face: two small black dot eyes and a single curved mouth. "
    "Drawn motion marks: speed lines, motion arcs, impact bursts in black marker. "
    "Single accent color: warm marker red-orange used sparingly as a flat highlight on the most important element. "
    "No visible words, letters, or numbers anywhere in the image."
)

SYSTEM_PROMPT = (
    "Siz professional 'Nima uchun?' (ilm-fan, psixologiya, inson miyasi va hayotiy qiziqarli faktlar) mavzusidagi Stickman video rejissyori va ssenariynavisisiz. "
    "Sizning vazifangiz — bitta qiziqarli 'Nima uchun...?' mavzusini tanlash va uni 8 sahnadan iborat (~60 soniyalik) dinamik stickman video paketi ko'rinishida tayyorlash. "
    "QOIDALAR: "
    "1. Mavzu: Odamlar o'ziga beradigan, lekin javobini bilmaydigan qiziqarli savol. "
    "2. O'zbekcha matn (narration_uz): Har bir sahna uchun 14-22 so'zdan iborat, do'stona, jonli, og'zaki o'zbek tilida ('siz' shaklida) yozilsin. Uydirma statistika ishlatmang. "
    "3. Har bir sahna bitta aniq harakat yoyiga (anticipation -> action -> settle) ega bo'lsin. Kadrlar almashib tursin (yaqin plan, uzoq plan, pastki rakurs, qiyshiq kadr). "
    "4. Rasm prompti (image_prompt_en): Ingliz tilida, birinchi kadrdagi eng keskin harakat lahzasini (anticipation yoki impact) tasvirlasin. Ichida HECH QANDAY matn, harf, raqam yoki rang kodi bo'lmasin. "
    "5. Kamera harakati (camera_move): 'zoom_in', 'zoom_out', 'pan_right', 'pan_left', 'impact_shake' dan birini tanlang. "
    "FAQAT quyidagi JSON formatda javob qaytaring: "
    '{"title_uz": "YouTube sarlavha", "description_uz": "Tavsif", "scenes": [{"scene_number": 1, "narration_uz": "Matn", "image_prompt_en": "Prompt", "camera_move": "zoom_in"}]}'
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


def generate_image(prompt_en, output_path, fallback_img=None):
    full_prompt = prompt_en + ". " + STYLE_LOCK
    encoded_prompt = requests.utils.quote(full_prompt)
    for attempt in range(1, 6):
        try:
            print("   Rasm urinish", attempt, "...", flush=True)
            seed = int(time.time()) + attempt * 17
            url = (
                "https://image.pollinations.ai/prompt/"
                + encoded_prompt
                + "?width=1280&height=720&nologo=true&model=flux&seed="
                + str(seed)
            )
            resp = requests.get(url, timeout=(15, 45))
            if resp.status_code == 200 and len(resp.content) > 5000:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                print("   Rasm tayyor!", flush=True)
                return output_path
            else:
                print("   Server javobi:", resp.status_code, flush=True)
        except Exception as e:
            print("   Urinish xatosi:", e, flush=True)
        time.sleep(5)

    if fallback_img and os.path.exists(fallback_img):
        print("   Zaxira rasm ishlatildi (jarayon to'xtamadi)", flush=True)
        shutil.copy(fallback_img, output_path)
        return output_path

    raise RuntimeError("Birinchi rasmni ham yuklab bo'lmadi.")


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


def main():
    os.makedirs("build", exist_ok=True)
    pack = generate_script()
    print("Mavzu tanlandi:", pack["title_uz"], flush=True)

    clip_files = []
    last_good_img = None
    total = len(pack["scenes"])
    for idx, scene in enumerate(pack["scenes"], start=1):
        print("--- Sahna", idx, "/", total, "tayyorlanmoqda ---", flush=True)
        img_path = "build/scene_" + str(idx) + ".png"
        aud_path = "build/scene_" + str(idx) + ".mp3"
        clip_path = "build/clip_" + str(idx) + ".mp4"

        last_good_img = generate_image(scene["image_prompt_en"], img_path, last_good_img)
        asyncio.run(generate_voice(scene["narration_uz"], aud_path))
        create_scene_clip(img_path, aud_path, scene.get("camera_move", "zoom_in"), clip_path)
        clip_files.append(clip_path)
        time.sleep(4)

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

    with open("metadata.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "title": pack["title_uz"],
                "description": pack["description_uz"],
                "tags": ["nima uchun", "stickman", "qiziqarli faktlar", "psixologiya", "ilm fan"],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("TAYYOR! Video muvaffaqiyatli yig'ildi: final_video.mp4", flush=True)


if __name__ == "__main__":
    main()
