# engine/render_job.py
from __future__ import annotations
import json, time, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from moviepy import CompositeVideoClip, ImageClip, AudioFileClip
from moviepy.video.fx.FadeIn import FadeIn as v_fadein
from moviepy.audio.fx.AudioFadeIn import AudioFadeIn as audio_fadein

ROOT = Path(__file__).resolve().parent.parent  # project root


def load_job(job_path: Path) -> dict:
    job = json.loads(job_path.read_text())
    tname, _, tver = job["template"].partition("@")
    job["_template_name"] = tname
    job["_template_ver"] = tver or "0.2"
    return job


def load_template(job: dict) -> dict:
    tpath = ROOT / "templates" / job["_template_name"] / "template.json"
    if not tpath.exists():
        raise FileNotFoundError(f"Template not found: {tpath}")
    return json.loads(tpath.read_text())


def wrap_to_two_lines(caption: str, draw, font, max_width: int) -> list[str]:
    if not caption or max_width <= 0:
        return [""]

    def width(txt):
        l, t, r, b = draw.textbbox((0, 0), txt, font=font)
        return r - l

    def ellipsize(txt):
        ell = "…"
        base = txt.rstrip()
        if width(ell) > max_width:
            return ""
        while base and width(base + ell) > max_width:
            base = base[:-1]
        return (base + ell) if base else ell

    words = caption.strip().split()
    lines, cur, overflow = [], [], False
    for w in words:
        cand = ((" ".join(cur) + " " + w) if cur else w)
        if width(cand) <= max_width:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
                cur = []
            else:
                lines.append(ellipsize(w))
            if len(lines) == 2:
                overflow = True
                break
            if width(w) <= max_width:
                cur = [w]
            else:
                lines.append(ellipsize(w))
                if len(lines) == 2:
                    overflow = True
                    break

    if cur and len(lines) < 2:
        cand = " ".join(cur)
        lines.append(cand if width(cand) <= max_width else ellipsize(cand))

    lines = lines[:2]
    if overflow and lines:
        lines[-1] = ellipsize(lines[-1])
    return lines or [""]


def build_cover_bg(image_path: Path, W: int, H: int, duration: float):
    with Image.open(image_path) as im:
        sw, sh = im.size
    scale = max(W / sw, H / sh)
    tw, th = int(sw * scale), int(sh * scale)
    x1 = max(0, (tw - W) // 2)
    y1 = max(0, (th - H) // 2)

    clip = ImageClip(image_path.as_posix()).resized((tw, th))
    clip = clip.cropped(x1=x1, y1=y1, width=W, height=H)
    return clip.with_duration(duration)


def build_caption_bar(template: dict, caption: str, W: int, duration: float):
    C = _caption_config(template)
    h = int(C["height"])
    bar_img = Image.new("RGBA", (W, h), _rgba(C["bar_color_rgba"]))
    draw = ImageDraw.Draw(bar_img)
    try:
        font = ImageFont.truetype(C["font"], C["font_size_init"])
    except Exception:
        font = ImageFont.load_default()

    tb = C["text_box"]
    max_w = int(tb["w"])
    lines = wrap_to_two_lines(caption, draw, font, max_w)

    l, t, r, b = draw.textbbox((0, 0), "Ay", font=font)
    line_h = b - t
    total_h = line_h * len(lines)

    x0, y0 = int(tb["x"]), int(tb["y"])
    w, hbox = int(tb["w"]), int(tb["h"])
    y_start = y0 + (hbox - total_h) // 2
    color = _rgba(C["text_color_rgba"])

    for i, line in enumerate(lines):
        l, t, r, b = draw.textbbox((0, 0), line, font=font)
        text_w = r - l
        x = x0 + (w - text_w) // 2
        y = y_start + i * line_h
        draw.text((x, y), line, font=font, fill=color)

    bar_clip = ImageClip(np.array(bar_img)).with_duration(duration).with_position((0, 0))

    # video fade effects
    if C.get("fade_in", 0):
        bar_clip = v_fadein(C["fade_in"])(bar_clip)
    if C.get("fade_out", 0):
        bar_clip = v_fadeout(C["fade_out"])(bar_clip)

    return bar_clip


def build_watermark(path: Path, W: int, H: int, template: dict, duration: float):
    wm = template["layers"][-1]
    opacity = float(wm.get("opacity", 1.0))
    scale_from_source = wm.get("scale_from_source", 0.3)
    logo = (
        ImageClip(path.as_posix())
        .resized(scale_from_source)
        .with_opacity(opacity)
        .with_duration(duration)
    )

    off_pct = wm.get("offset_pct_of_canvas", {"x": 4, "y": 4})
    offx = int(W * (off_pct["x"] / 100.0))
    offy = int(H * (off_pct["y"] / 100.0))
    x = 0 + offx
    y = H - int(logo.h) - offy
    return logo.with_position((x, y))


def _rgba(seq):
    return tuple(int(x) for x in seq)


def _caption_config(template: dict) -> dict:
    C = {
        "height": 270,
        "text_box": {"x": 36, "y": 24, "w": 1008, "h": 222},
        "text_color_rgba": [17, 17, 17, 255],
        "bar_color_rgba": [255, 255, 255, 255],
        "font": "assets/fonts/Inter-Bold.ttf",
        "font_size_init": 50,
        "fade_in": template.get("video", {}).get("effects", {}).get("fade_in", 0),
        "fade_out": 0,
    }
    return C


def main(job_relpath: str) -> None:
    job_path = ROOT / job_relpath
    job = load_job(job_path)
    template = load_template(job)

    canvas = template["canvas"]
    W, H = int(canvas["width"]), int(canvas["height"])
    FPS = int(canvas["fps"])
    DUR = float(canvas["duration"])

    img = ROOT / job["image_path"]
    mus = ROOT / job["music_path"]
    wmk = ROOT / job["watermark_path"]
    out_mp4 = ROOT / job["export"]["filename"]
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    bg = build_cover_bg(img, W, H, DUR)
    bar = build_caption_bar(template, job["caption_text"], W, DUR)
    logo = build_watermark(wmk, W, H, template, DUR)

    # load and trim audio
    music = AudioFileClip(mus.as_posix())
    if music.duration > DUR:
        music = music.subclipped(0, DUR)

    aud_cfg = template.get("audio", {})
    if aud_cfg.get("effects", {}).get("fade_in", 0):
        music = audio_fadein(aud_cfg["effects"]["fade_in"])(music)
    if aud_cfg.get("effects", {}).get("fade_out", 0):
        music = audio_fadeout(aud_cfg["effects"]["fade_out"])(music)

    final = CompositeVideoClip([bg, bar, logo]).with_audio(music).with_duration(DUR)

    vid_fx = template.get("video", {}).get("effects", {})
    if vid_fx.get("fade_in", 0):
        final = v_fadein(vid_fx["fade_in"])(final)
    if vid_fx.get("fade_out", 0):
        final = v_fadeout(vid_fx["fade_out"])(final)

    exp = template["export"]
    final.write_videofile(
        filename=out_mp4.as_posix(),
        fps=FPS,
        codec=exp["codec"],
        audio_codec=exp["audio_codec"],
        preset=exp["preset"],
        bitrate=exp["bitrate"],
    )

    meta = {
        "rendered_at": int(time.time()),
        "template": template["name"],
        "template_version": template["version"],
        "canvas": canvas,
        "inputs": {
            "image_path": job["image_path"],
            "caption_text": job["caption_text"],
            "music_path": job["music_path"],
            "watermark_path": job["watermark_path"],
        },
        "export": {**exp, "filename": job["export"]["filename"]},
    }

    out_json = out_mp4.with_suffix(".json")
    out_json.write_text(json.dumps(meta, indent=2))
    print(f"✅ Wrote {out_mp4} and {out_json}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python engine/render_job.py data/jobs/example.json")
        sys.exit(2)
    main(sys.argv[1])
