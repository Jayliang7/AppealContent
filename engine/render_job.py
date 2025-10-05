# engine/render_job.py
# Render a single video from a Job JSON, using the same look/behavior as hello_video.py.
# Usage:
#   python engine/render_job.py data/jobs/example.json

from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from moviepy import CompositeVideoClip, ImageClip, AudioFileClip
from moviepy.video.fx.FadeIn import FadeIn
from moviepy.audio.fx.AudioFadeIn import AudioFadeIn

# Project root
ROOT = Path(__file__).resolve().parent.parent  # .../AppealContent

# ------------------------------
# Utilities
# ------------------------------

def load_job(job_relpath: str) -> dict:
    job_path = (ROOT / job_relpath).resolve()
    if not job_path.exists():
        raise FileNotFoundError(f"Job file not found: {job_path}")
    try:
        return json.loads(job_path.read_text())
    except Exception as e:
        raise RuntimeError(f"Failed to parse job JSON: {e}")

def load_template(job: dict) -> dict:
    # "template": "fade_in_meme@0.2"
    tname, _, _tver = job.get("template", "fade_in_meme@0.2").partition("@")
    tpath = ROOT / "templates" / tname / "template.json"
    if tpath.exists():
        return json.loads(tpath.read_text())
    # Fallback to sensible defaults if template file is missing.
    return {
        "canvas": { "width": 1080, "height": 1350, "fps": 30, "duration": 6.13 },
        "export": { "codec": "libx264", "audio_codec": "aac", "bitrate": "6M", "preset": "medium" }
    }

def wrap_to_two_lines(caption: str, draw, font, max_width: int) -> list[str]:
    """Break caption into up to 2 lines that fit in max_width; ellipsize if needed."""
    if not caption or max_width <= 0:
        return [""]

    def width(text: str) -> int:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l

    def fit_chars(line: str) -> str:
        ell = "…"
        base = line.rstrip()
        if width(ell) > max_width:
            return ""
        while base and width(base + ell) > max_width:
            base = base[:-1]
        return (base + ell) if base else ell

    words = caption.strip().split()
    lines, current = [], []
    overflow = False

    for w in words:
        test = ((" ".join(current) + " " + w) if current else w)
        if width(test) <= max_width:
            current.append(w)
        else:
            if current:
                lines.append(" ".join(current))
                current = []
            else:
                lines.append(fit_chars(w))
            if len(lines) == 2:
                overflow = True
                break
            if width(w) <= max_width:
                current = [w]
            else:
                lines.append(fit_chars(w))
                if len(lines) == 2:
                    overflow = True
                    break

    if current and len(lines) < 2:
        candidate = " ".join(current)
        if width(candidate) <= max_width:
            lines.append(candidate)
        else:
            lines.append(fit_chars(candidate))

    lines = lines[:2]
    if overflow and lines:
        lines[-1] = fit_chars(lines[-1])
    return lines or [""]

# ------------------------------
# Core render
# ------------------------------

def render(job: dict) -> Path:
    # 1) Canvas + export from template (or fallback)
    template = load_template(job)
    canvas = template.get("canvas", {})
    WIDTH   = int(canvas.get("width", 1080))
    HEIGHT  = int(canvas.get("height", 1350))
    FPS     = int(canvas.get("fps", 30))
    DURATION= float(canvas.get("duration", 6.13))

    export  = template.get("export", {})
    vcodec  = export.get("codec", "libx264")
    acodec  = export.get("audio_codec", "aac")
    bitrate = export.get("bitrate", "6M")
    preset  = export.get("preset", "medium")

    # 2) Resolve inputs from job JSON
    image_path     = (ROOT / job["image_path"]).resolve()
    music_path     = (ROOT / job["music_path"]).resolve()
    watermark_path = (ROOT / job["watermark_path"]).resolve()
    caption_text   = job["caption_text"]
    out_path       = (ROOT / job["export"]["filename"]).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 3) Build AUDIO (trim + fade-in)
    music = AudioFileClip(music_path.as_posix())
    if music.duration > DURATION:
        music = music.subclipped(0, DURATION)
    music = music.with_effects([AudioFadeIn(1.5)])  # fade-in only

    # 4) Build CAPTION BAR (same logic as hello_video.py)
    BAR_HEIGHT = HEIGHT // 5  # 1/5th of screen
    TEXT_BOX   = { "x": 36, "y": 24, "w": WIDTH - 72, "h": BAR_HEIGHT - 48 }
    TEXT_COLOR = (17, 17, 17, 255)        # near-black
    BAR_COLOR  = (255, 255, 255, 255)     # white

    # create bar image & draw text (max 2 lines)
    bar_img = Image.new("RGBA", (WIDTH, BAR_HEIGHT), BAR_COLOR)

    # Font (fallback to default if missing)
    # Prefer font from template if present, else Inter-Bold.ttf
    font_path = template.get("layers", [{}])
    # Try to extract font field from text layer, else default path:
    font_file = None
    for layer in template.get("layers", []):
        if layer.get("type") == "text" and layer.get("font"):
            font_file = layer["font"]
            break
    if not font_file:
        font_file = "assets/fonts/Inter-Bold.ttf"

    try:
        font = ImageFont.truetype((ROOT / font_file).as_posix(), 50)
    except Exception:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(bar_img)
    lines = wrap_to_two_lines(caption_text, draw, font, max_width=TEXT_BOX["w"])

    # vertical centering inside TEXT_BOX
    l, t, r, b = draw.textbbox((0, 0), "Ay", font=font)
    line_h = b - t
    total_h = line_h * len(lines)

    x0, y0, w, h = TEXT_BOX["x"], TEXT_BOX["y"], TEXT_BOX["w"], TEXT_BOX["h"]
    y_start = y0 + (h - total_h) // 2

    for i, line in enumerate(lines):
        l, t, r, b = draw.textbbox((0, 0), line, font=font)
        text_w = r - l
        x = x0 + (w - text_w) // 2
        y = y_start + i * line_h
        draw.text((x, y), line, font=font, fill=TEXT_COLOR)

    bar_clip = (
        ImageClip(np.array(bar_img))
        .with_duration(DURATION)
        .with_position((0, 0))
    )

    # 5) Build BACKGROUND with cover-fit crop
    with Image.open(image_path) as im:
        src_w, src_h = im.size
    scale = max(WIDTH / src_w, HEIGHT / src_h)
    scaled_w, scaled_h = int(src_w * scale), int(src_h * scale)
    x1 = max(0, (scaled_w - WIDTH) // 2)
    y1 = max(0, (scaled_h - HEIGHT) // 2)

    bg_clip = (
        ImageClip(image_path.as_posix())
        .resized((scaled_w, scaled_h))
        .cropped(x1=x1, y1=y1, width=WIDTH, height=HEIGHT)
        .with_duration(DURATION)
    )

    # 6) Build WATERMARK bottom-left (~4% margins), 30% scale of source
    left_margin   = WIDTH // 25
    bottom_margin = HEIGHT // 25
    logo_base = (
        ImageClip(watermark_path.as_posix())
        .resized(0.3)
        .with_opacity(1)     # 100% opacity to match hello_video.py
        .with_duration(DURATION)
    )
    lx = left_margin
    ly = HEIGHT - int(logo_base.h) - bottom_margin
    logo = logo_base.with_position((lx, ly))

    # 7) Composite + fade-in video + attach audio
    final = (
        CompositeVideoClip([bg_clip, bar_clip, logo])
        .with_effects([FadeIn(1.5)])   # global video fade-in
        .with_audio(music)
    )

    # 8) Export
    final.write_videofile(
        filename=out_path.as_posix(),
        fps=FPS,
        codec=vcodec,
        audio_codec=acodec,
        preset=preset,
        bitrate=bitrate,
    )

    print(f"✅ Wrote {out_path}")
    return out_path

# ------------------------------
# CLI entrypoint
# ------------------------------

def main():
    if len(sys.argv) != 2:
        print("Usage: python engine/render_job.py data/jobs/example.json")
        sys.exit(2)
    job = load_job(sys.argv[1])
    try:
        render(job)
    except Exception as e:
        print(f"❌ Render failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
