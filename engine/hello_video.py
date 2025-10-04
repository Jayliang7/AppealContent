# engine/hello_video.py
# goal: create a plain 1080x1920, 12s, 30fps MP4 to verify the pipeline end-to-end

from moviepy import ColorClip, TextClip, CompositeVideoClip, ImageClip
from moviepy.video.fx.FadeIn import FadeIn

from PIL import Image, ImageDraw, ImageFont
import numpy as np

from pathlib import Path

# ground the path to be robust whereever we run it from
ROOT = Path(__file__).resolve().parent.parent #project root

OUTPUT = ROOT / "output" / "hello2.mp4"
logo_path = ROOT / "assets" / "logos" / "appeal.png"

# --- settings ---
WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 2

# --- caption bar settings ---
BAR_HEIGHT = 220
CAPTION = "we said '5 minutes' and started a whole new life"  # put any test text here
TEXT_BOX = { "x": 36, "y": 24, "w": 1080 - 72, "h": BAR_HEIGHT - 48 }  # padding inside the bar
FONT_PATH = Path("assets/fonts/Inter-Bold.ttf")  # use your font if present
INITIAL_FONT_SIZE = 50
MIN_FONT_SIZE = 28
LINE_SPACING = 0.95  # 95% of font size
MAX_LINES = 2        # never more than two lines
TEXT_COLOR = (17, 17, 17, 255)  # near-black
BAR_COLOR  = (255, 255, 255, 255)  # white

# make sure output exists
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

# create bar rectangle
bar_img = Image.new("RGBA", (WIDTH, BAR_HEIGHT), BAR_COLOR) 
bar_clip = (
    ImageClip(np.array(bar_img), ismask=False)
    .with_duration(DURATION)
    .with_position((0,0)) 
)

#background color 
bg_color = (240, 240, 240) # light gray

#create solid color video clip and set duration
clip = ColorClip(size=(WIDTH, HEIGHT), color=bg_color).with_duration(DURATION)

# load and prepare logo
logo = (
    ImageClip(logo_path.as_posix())
    .resized(0.5)
    .with_opacity(0.5)
    .with_duration(DURATION)
    .with_position(("left", "bottom"))
)

# create composite clip 
final = CompositeVideoClip([clip, bar_clip, logo]).with_effects((FadeIn(1.5),))

# export final file
final.write_videofile(
    filename=OUTPUT.as_posix(),
    fps=FPS,
    codec="libx264",
    audio=False,
    preset="medium",
    bitrate="6M",
)

print(f"✅ Wrote {OUTPUT}")