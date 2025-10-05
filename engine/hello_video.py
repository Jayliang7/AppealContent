# engine/hello_video.py
# goal: create a plain 1080x1350, ~6s, 30fps MP4 to verify the pipeline end-to-end

from moviepy import CompositeVideoClip, ImageClip, AudioFileClip
from moviepy.video.fx.FadeIn import FadeIn
from moviepy.audio.fx.AudioFadeIn import AudioFadeIn

from PIL import Image, ImageDraw, ImageFont
import numpy as np

from pathlib import Path

# ground the path to be robust whereever we run it from
ROOT = Path(__file__).resolve().parent.parent #project root

OUTPUT = ROOT / "output" / "hello.mp4"
logo_path = ROOT / "assets" / "logos" / "appeal_black.png"
FONT_PATH = ROOT / "assets" / "fonts" / "Inter-Bold.ttf"
images_dir = ROOT / "assets" / "images"
music_path = ROOT / "assets" / "music" / "testsong.mp3"

# --- settings ---
WIDTH = 1080
HEIGHT = 1350
FPS = 30
DURATION = 6.13 # seconds

# --- caption bar settings ---

BAR_HEIGHT = HEIGHT // 5  # 1/5th of screen height``
CAPTION = "POV: me when bro says nigga like nigga u ain't funny stupid bitchass nigga fuck u"  # put any test text here
TEXT_BOX = { "x": 36, "y": 24, "w": WIDTH - 72, "h": BAR_HEIGHT - 48 }  # padding inside the bar
INITIAL_FONT_SIZE = 50
TEXT_COLOR = (17, 17, 17, 255)  # near-black
BAR_COLOR  = (255, 255, 255, 255)  # white

# make sure output exists
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

# -- build audio with fades --- 
music = AudioFileClip(music_path.as_posix())

# if longer than video than trim; if shorter, don't loop
if music.duration > DURATION:
    music = music.subclipped(0, DURATION)
# fade in
# music = music.with_effects([AudioFadeIn(1.5)])

# --- choose an image from assets/images ---
candidates = []
for ext in ("*.png", "*.jpg", "*.jpeg"):
    candidates.extend(images_dir.glob(ext))
if not candidates:
    raise FileNotFoundError(f"No images found in {images_dir}")
image_path = candidates[0]  # just pick the first one for now

# --- TOP WHITE BAR + SINGLE CENTERED CAPTION ---
# make a white RGBA image for top bar
bar_img = Image.new("RGBA", (WIDTH, BAR_HEIGHT), BAR_COLOR) 

# load a font (fallback if TTF not found)
try:
    font = ImageFont.truetype(FONT_PATH.as_posix(), INITIAL_FONT_SIZE)
except Exception:
    font = ImageFont.load_default()

# --- TEXT WRAPPING ---
def wrap_to_two_lines(caption: str, draw, font, max_width: int) -> list[str]:
    """
    Build up to 2 lines that each fit within max_width (in pixels).
    If more text remains after 2 lines, ellipsize the 2nd line.
    Guarantees every returned line's width <= max_width.
    """
    # Fast exits
    if not caption or max_width <= 0:
        return [""]  # keep pipeline safe

    words = caption.strip().split()
    lines: list[str] = []
    current: list[str] = []
    overflow = False  # becomes True if we run out of room

    def width(text: str) -> int:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l

    def fit_chars(line: str) -> str:
        """Shrink characters until it fits; add ellipsis. Used for overlong single words or ellipsizing last line."""
        # try Unicode ellipsis; if it doesn't render well in your font, change to '...'
        ell = "…"
        # remove trailing spaces before adding ellipsis
        base = line.rstrip()
        # If even a single char + ellipsis doesn't fit, return ellipsis only
        if width(ell) > max_width:
            return ""  # degenerate, caller may handle as empty
        while base and width(base + ell) > max_width:
            base = base[:-1]
        return (base + ell) if base else ell

    for w in words:
        test = ((" ".join(current) + " " + w) if current else w)

        if width(test) <= max_width:
            current.append(w)
        else:
            # finalize current line (even if empty we must handle w)
            if current:
                lines.append(" ".join(current))
                current = []
            else:
                # The single word itself is wider than max_width.
                # Hard-truncate it with ellipsis and use it as the line.
                lines.append(fit_chars(w))

            if len(lines) == 2:
                overflow = True  # we already used 2 lines; more words remain
                break

            # start a fresh line with this word if it fits, else truncate word to line
            if width(w) <= max_width:
                current = [w]
            else:
                lines.append(fit_chars(w))
                if len(lines) == 2:
                    overflow = True
                    break

    # Flush remaining words if we still have room (<2 lines)
    if current and len(lines) < 2:
        candidate = " ".join(current)
        if width(candidate) <= max_width:
            lines.append(candidate)
        else:
            # shouldn't happen often, but be safe
            lines.append(fit_chars(candidate))

    # Enforce max 2 lines
    lines = lines[:2]

    # If we overflowed (i.e., more text left), ellipsize the last line to indicate truncation
    if overflow and lines:
        lines[-1] = fit_chars(lines[-1])

    # Always return at least one line
    if not lines:
        lines = [""]

    return lines

# --- draw wrapped caption (max 2 lines) INTO bar_img, then create bar_clip ---
draw = ImageDraw.Draw(bar_img)

lines = wrap_to_two_lines(CAPTION, draw, font, max_width=TEXT_BOX["w"])

# measure line height robustly
l, t, r, b = draw.textbbox((0, 0), "Ay", font=font)
line_h = b - t
total_h = line_h * len(lines)

# center vertically in TEXT_BOX
x0, y0, w, h = TEXT_BOX["x"], TEXT_BOX["y"], TEXT_BOX["w"], TEXT_BOX["h"]
y_start = y0 + (h - total_h) // 2

# draw each line centered horizontally
for i, line in enumerate(lines):
    l, t, r, b = draw.textbbox((0, 0), line, font=font)
    text_w = r - l
    x = x0 + (w - text_w) // 2
    y = y_start + i * line_h
    draw.text((x, y), line, font=font, fill=TEXT_COLOR)

# now convert the UPDATED bar_img to a clip
bar_clip = (
    ImageClip(np.array(bar_img))
    .with_duration(DURATION)
    .with_position((0, 0))
)

# --- cover-fit background clip ---
with Image.open(image_path) as im:
    src_w, src_h = im.size

scale = max(WIDTH / src_w, HEIGHT / src_h)
scaled_w, scaled_h = int(src_w * scale), int(src_h * scale)

# how much to crop from the scaled image to hit exact canvas size
x1 = max(0, (scaled_w - WIDTH) // 2)
y1 = max(0, (scaled_h - HEIGHT) // 2)

bg_clip = (
    ImageClip(image_path.as_posix())
    .resized((scaled_w, scaled_h))
    .cropped(x1=x1, y1=y1, width=WIDTH, height=HEIGHT)
    .with_duration(DURATION)
)

# --- CREATE WATERMARK --- 
# margins 
left_margin = WIDTH // 25
bottom_margin = HEIGHT // 25

logo_base = (
    ImageClip(logo_path.as_posix())
    .resized(0.3)  # scale logo to 30% of original size
    .with_opacity(1)  # set opacity to 100%
    .with_duration(DURATION)  # match video duration
)

# compute pixel position: x = left_margin, y = canvas height - logo_height - bottom_margin
lx = left_margin
ly = HEIGHT - int(logo_base.h) - bottom_margin

logo = logo_base.with_position((lx, ly))

# create composite clip 
final = CompositeVideoClip([bg_clip, bar_clip, logo]).with_effects([FadeIn(1.5)]).with_audio(music)

# export final file
final.write_videofile(
    filename=OUTPUT.as_posix(),
    fps=FPS,
    codec="libx264",
    audio_codec="aac",
    preset="medium",
    bitrate="6M",
)

print(f"✅ Wrote {OUTPUT}")