import os
import json
import time
import asyncio
import requests
import subprocess
from google import genai
from google.genai import types
import edge_tts

# 1. API va sozlamalar
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# Stickman Style Lock (sizning skill faylingizdan olingan asosiy standart)
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

SYSTEM_PROMPT = f"""
Siz professional "Nima uchun?" (ilm-fan, psixologiya, inson miyasi va hayotiy qiziqarli faktlar) mavzusidagi Stickman video rejissyori va ssenariynavisisiz.
Sizning vazifangiz — bitta qiziqarli "Nima uchun...?" mavzusini tanlash va uni 8 sahnadan iborat (~60 soniyalik) dinamik stickman video paketi ko'rinishida tayyorlash.

QOIDALAR:
1. Mavzu: Odamlar o'ziga beradigan, lekin javobini bilmaydigan qiziqarli savol (masalan: "Nima uchun miyamiz dangasalikni yaxshi ko'radi?", "Nima uchun uyquda yiqilib tushgandek cho'chib uyg'onamiz?" va h.k.).
2. O'zbekcha matn (narration_uz): Har bir sahna uchun 14–22 so'zdan iborat, do'stona, jonli, og'zaki o'zbek tilida ("siz" shaklida) yozilsin. Hech qanday uydirma statistika yoki soxta tadqiqotlar qo'shilmasin.
3. Har bir sahna bitta aniq harakat yoyiga (anticipation -> action -> settle) ega bo'lsin. Bir xil zerikarli kadrlar takrorlanmasin (yaqin plan, uzoq plan, pastki rakurs, qiyshiq kadrlar almashib tursin).
4. Rasm prompti (image_prompt_en): Ingliz tilida, birinchi kadrdagi eng keskin harakat lahzasini (anticipation yoki impact) tasvirlasin. Ichida HECH QANDAY matn, harf, raqam yoki rang kodi (#...) bo'lmasin!
5. Kamera harakati (camera_move): Quyidagilardan birini tanlang: "zoom_in", "zoom_out", "pan_right", "pan_left", "impact_shake".

FAQAT quyidagi JSON formatda javob qaytaring (boshqa hech qanday izoh yozmang):
{{
  "title_uz": "YouTube uchun qiziqarli sarlavha (Nima uchun...?)",
  "description_uz": "Video haqida qisqacha tavsif va teglar",
  "scenes": [
    {{
      "scene_number": 1,
      "narration_uz": "O'zbek tilidagi jonli nutq matni",
      "image_prompt_en": "Sahna tavsifi ingliz tilida...",
      "camera_move": "zoom_in"
    }}
  ]
}}
"""

def generate_script():
    print("1. Gemini (gemini-3.0-flash) orqali Stickman ssenariy yaratilmoqda...")
    response = client.models.generate_content(
        model="gemini-3.0-flash",
        contents="Yangi, juda qiziqarli va hayotiy 'Nima uchun...?' mavzusida 8 sahnalik stickman video ssenariysini yarat.",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.8
        )
    )
    return json.loads(response.text)

def generate_image(prompt_en, output_path):
    full_prompt = f"{prompt_en}. {STYLE_LOCK}"
    # 1-urinish: Google Imagen 3
    try:
        result = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=full_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9",
                output_mime_type="image/png"
            )
        )
        for generated_image in result.generated_images:
            generated_image.image.save(output_path)
            return True
    except Exception as e:
        print(f"Imagen API xatosi ({e}), zaxira generatorga o'tilmoqda...")

    # 2-urinish (Zaxira): Pollinations AI (bepul, kalitsiz)
    encoded_prompt = requests.utils.quote(full_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&nologo=true&seed={int(time.time())}"
    resp = requests.get(url, timeout=60)
    if resp.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return True
    raise RuntimeError("Rasm generatsiya qilib bo'lmadi.")

async def generate_voice(text_uz, output_path):
    # O'zbek tilidagi tabiiy erkak ovozi (Sardor)
    communicate = edge_tts.Communicate(text_uz, "uz-UZ-SardorNeural", rate="+5%")
    await communicate.save(output_path)

def get_audio_duration(audio_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    res = subprocess.check_output(cmd).decode().strip()
    return float(res)

def create_scene_clip(img_path, audio_path, move, clip_path):
    duration = get_audio_duration(audio_path) + 0.4
    frames = int(duration * 30)

    # Statik rasm bo'lib qolmasligi uchun dinamik kamera harakatlari
    if move == "zoom_in":
        zoom_expr = f"zoom='min(zoom+0.0015,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif move == "zoom_out":
        zoom_expr = f"zoom='if(lte(zoom,1.0),1.25,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif move == "pan_right":
        zoom_expr = f"zoom='1.15':x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)'"
    elif move == "pan_left":
        zoom_expr = f"zoom='1.15':x='(iw-iw/zoom)*(1-on/{frames})':y='ih/2-(ih/zoom/2)'"
    else:  # impact_shake
        zoom_expr = f"zoom='1.12':x='iw/2-(iw/zoom/2)+sin(on*0.8)*8':y='ih/2-(ih/zoom/2)+cos(on*0.8)*6'"

    vf = (
        f"scale=2560:1440,"
        f"zoompan={zoom_expr}:d={frames}:s=1280x720:fps=30,"
        f"format=yuv420p"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", img_path,
        "-i", audio_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration),
        clip_path
    ]
    subprocess.run(cmd, check=True)

def main():
    os.makedirs("build", exist_ok=True)
    pack = generate_script()
    print(f"Mavzu tanlandi: {pack['title_uz']}")

    clip_files = []
    for idx, scene in enumerate(pack["scenes"], start=1):
        print(f"--- Sahna {idx}/{len(pack['scenes'])} tayyorlanmoqda ---")
        img_path = f"build/scene_{idx}.png"
        aud_path = f"build/scene_{idx}.mp3"
        clip_path = f"build/clip_{idx}.mp4"

        generate_image(scene["image_prompt_en"], img_path)
        asyncio.run(generate_voice(scene["narration_uz"], aud_path))
        create_scene_clip(img_path, aud_path, scene.get("camera_move", "zoom_in"), clip_path)
        clip_files.append(clip_path)

    # Barcha sahnalarni bitta videoga birlashtirish
    concat_list = "build/clips.txt"
    with open(concat_list, "w") as f:
        for c in clip_files:
            f.write(f"file '{os.path.abspath(c)}'\n")

    final_video = "final_video.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list, "-c", "copy", final_video
    ], check=True)

    # Metadata faylini saqlash (YouTube yuklovchi skript o'qishi uchun)
    with open("metadata.json", "w", encoding="utf-8") as f:
        json.dump({
            "title": pack["title_uz"],
            "description": pack["description_uz"],
            "tags": ["nima uchun", "stickman", "qiziqarli faktlar", "psixologiya", "ilm fan"]
        }, f, ensure_ascii=False, indent=2)

    print("TAYYOR! Video muvaffaqiyatli yig'ildi:", final_video)

if __name__ == "__main__":
    main()
