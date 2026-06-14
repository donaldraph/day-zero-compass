"""Regenerate architecture.png (PIL), matching the current app:

  User -> Streamlit (two modes) -> GPT-4o on GitHub Models (the reasoning brain)
  -> three evidence layers (structural reasoning, Foundry IQ/Azure AI Search,
     Tavily live web) -> verdict + citations + safe alternative.

Microsoft components are labelled. Dark theme.
"""

import math
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 860
BG = (13, 17, 23)
BOX = (26, 34, 48)
WHITE = (235, 239, 245)
MUTE = (165, 175, 189)
GRAY = (120, 130, 145)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# colours
RED = (210, 70, 70)        # Streamlit UI
PURPLE = (140, 110, 230)   # GitHub Models (Microsoft)
BLUE = (90, 150, 220)      # structural reasoning
MSBLUE = (66, 135, 245)    # Foundry IQ / Azure AI Search (Microsoft)
AMBER = (210, 168, 34)     # Tavily live web
GREEN = (40, 165, 105)     # verdict output


def f(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def center(cx, y, text, font, fill):
    w = d.textlength(text, font=font)
    d.text((cx - w / 2, y), text, font=font, fill=fill)


def box(x, y, w, h, border, title, subs=None, title_size=20, ms=False):
    d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=BOX, outline=border, width=3)
    cx = x + w / 2
    ty = y + (12 if subs else (h - title_size) / 2 - 2)
    center(cx, ty, title, f(title_size, True), WHITE)
    yy = ty + title_size + 6
    if ms:  # a clear, centered Microsoft label under the title
        center(cx, yy, "● Microsoft", f(13, True), (120, 180, 255))
        yy += 20
    for s in (subs or []):
        center(cx, yy, s, f(14), MUTE)
        yy += 19
    return {"cx": cx, "top": (cx, y), "bot": (cx, y + h), "x": x, "y": y, "w": w, "h": h}


def arrow(p1, p2, color=GRAY, width=3):
    d.line([p1, p2], fill=color, width=width)
    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    for da in (-0.45, 0.45):
        d.line([p2, (p2[0] - 14 * math.cos(ang - da), p2[1] - 14 * math.sin(ang - da))],
               fill=color, width=width)


center(640, 22, "Day Zero Compass — Architecture", f(30, True), WHITE)

# 1. User
user = box(515, 68, 250, 60, GRAY, "User", ["pastes an offer, or a profile"], 18)

# 2. Streamlit UI — two modes
ui = box(330, 158, 620, 74, RED, "Streamlit app — two modes",
         ["Scam Check  (is this real?)      ·      Learning Path  (plan my way in)"], 20)

# 3. GPT-4o on GitHub Models — the reasoning brain
brain = box(360, 268, 560, 104, PURPLE, "GPT-4o  ·  GitHub Models",
            ["the reasoning brain: runs every step,", "cached on disk so re-runs cost no quota"],
            20, ms=True)

# 4. Three evidence layers
center(640, 396, "Three evidence layers feeding the verdict", f(16, True), MUTE)
ey, eh, ew = 420, 150, 380
e1 = box(40, ey, ew, eh, BLUE, "Structural reasoning",
         ["reads it like a careful person:", "domain weighting, what it asks you to",
          "hand over. Catches scams never seen."], 19)
e2 = box(450, ey, ew, eh, MSBLUE, "Foundry IQ  ·  Azure AI Search",
         ["verified, cited grounding: documented", "scams + real programs. Never the gate —",
          "absence proves nothing."], 19, ms=True)
e3 = box(860, ey, ew, eh, AMBER, "Tavily live web verification",
         ["checks the real source, surfaces a", "deadline if found. Labelled web-sourced,",
          "lower trust than the knowledge base."], 19)

# 5. Verdict output
verdict = box(290, 628, 700, 86, GREEN, "Verdict  +  citations  +  safe alternative",
              ["red / amber / green  ·  never a false all-clear  ·  cites every source"], 20)

# arrows: vertical spine
arrow(user["bot"], ui["top"])
arrow(ui["bot"], brain["top"])
# brain fans out to the three layers
for e in (e1, e2, e3):
    arrow((brain["cx"], brain["y"] + brain["h"]), (e["cx"], ey), PURPLE)
# layers converge into the verdict
for e in (e1, e2, e3):
    arrow((e["cx"], ey + eh), (verdict["cx"] + (e["cx"] - verdict["cx"]) * 0.18, 628),
          (90, 150, 120))

# footer
center(640, 748, "Microsoft components: GitHub Models (GPT-4o) and Foundry IQ / Azure AI Search.",
       f(15), MUTE)
center(640, 772, "Falls back through the layers so it never breaks.  Built with GitHub Copilot.",
       f(15), GRAY)

img.save("architecture.png")
print("wrote architecture.png", img.size)
