"""Regenerate architecture.png (PIL). Dark theme matching the original diagram,
updated to show Foundry IQ (Azure AI Search) as the grounding layer."""

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 820
BG = (13, 17, 23)
BOX = (26, 34, 48)
WHITE = (235, 239, 245)
MUTE = (160, 170, 184)
GRAY = (120, 130, 145)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def f(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def center(draw, cx, y, text, font, fill):
    w = draw.textlength(text, font=font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill)


def box(x, y, w, h, border, title, subs=None, title_size=22, radius=14):
    d.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=BOX, outline=border, width=3)
    cx = x + w / 2
    ty = y + (16 if subs else (h - title_size) / 2 - 2)
    center(d, cx, ty, title, f(title_size, True), WHITE)
    if subs:
        yy = ty + title_size + 8
        for s in subs:
            center(d, cx, yy, s, f(15), MUTE)
            yy += 20
    return (cx, y, x + w, y + h, x, y + h / 2, x + w, y + h / 2)  # cx, top, ...


def arrow(p1, p2, color=GRAY, width=3, label=None):
    d.line([p1, p2], fill=color, width=width)
    import math
    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    L = 12
    for da in (-0.4, 0.4):
        d.line([p2, (p2[0] - L * math.cos(ang - da), p2[1] - L * math.sin(ang - da))],
               fill=color, width=width)
    if label:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        d.text((mx + 6, my - 18), label, font=f(13), fill=MUTE)


# Title
center(d, W / 2, 26, "Day Zero Compass — Architecture", f(30, True), WHITE)

# Streamlit UI
ux, uy, uw, uh = 360, 76, 560, 74
box(ux, uy, uw, uh, (210, 70, 70), "Streamlit UI — two modes",
    ["Is this opportunity real? (scam check)   •   Plan my learning path"], 20)
ui_bottom = (ux + uw / 2, uy + uh)

# Pipeline container
px, py, pw, ph = 60, 196, 1160, 196
d.rounded_rectangle([px, py, px + pw, py + ph], radius=16, fill=(18, 24, 34),
                    outline=(70, 90, 120), width=2)
d.text((px + 20, py + 12), "Agent steps — focused, cached GPT-4o calls",
       font=f(17, True), fill=WHITE)

steps = [("1. Assess", "profile → JSON"), ("2. Plan", "90-day path"),
         ("3. Match", "cited opportunities"), ("4. Verify", "scams & pitfalls")]
sw, sh, gap = 250, 96, 20
sx = px + 24
sy = py + 64
step_boxes = []
for title, sub in steps:
    step_boxes.append(box(sx, sy, sw, sh, (70, 120, 200), title, [sub], 21))
    sx += sw + gap

# Hero verifier note inside the strip
d.text((px + 24, py + ph - 26),
       "Scam check reuses the same spine: Extract → Check → Verdict (+ real alternative)",
       font=f(14), fill=MUTE)

arrow(ui_bottom, ((px + pw / 2), py), GRAY)

# Bottom row: Disk cache | Foundry IQ grounding | GitHub Models
row_y = 440
# Disk cache
cb = box(60, row_y, 330, 110, (40, 150, 95), "Disk cache (.cache/)",
         ["SHA-256 of prompt / query → JSON", "re-runs cost zero quota"], 20)
# Foundry IQ (center, highlighted)
fb = box(440, row_y, 400, 130, (66, 135, 245), "Foundry IQ — Azure AI Search",
         ["agentic retrieval over the indexed", "verified knowledge base · cited",
          "kb_retrieve() grounds Match + Check"], 21)
# GitHub Models
gb = box(890, row_y, 330, 110, (130, 110, 230), "GitHub Models (Microsoft)",
         ["GPT-4o · models.github.ai/inference", "auth: GITHUB_TOKEN (models:read)"], 19)

# knowledge.json feeding Foundry IQ (+ local fallback)
kx, ky, kw, kh = 440, 650, 400, 110
box(kx, ky, kw, kh, (224, 168, 22), "data/knowledge.json (human-verified)",
    ["opportunities + known scams, each cited", "indexed into Foundry IQ · local fallback"], 19)

# Arrows: steps -> Foundry IQ ; Foundry IQ -> knowledge.json ; steps -> models/cache
fb_top = (440 + 200, row_y)
arrow((step_boxes[2][0], py + ph), (fb_top[0] - 40, row_y), (224, 168, 22),
      label="grounding")
arrow((step_boxes[3][0], py + ph), (fb_top[0] + 40, row_y), (224, 168, 22))
arrow((640, ky), (640, row_y + 130), (224, 168, 22), label="index + fallback")
arrow((step_boxes[0][0], py + ph), (220, row_y), GRAY, label="cache")
arrow((step_boxes[3][0], py + ph + 4), (1010, row_y), (150, 130, 220),
      label="inference")

# Footer
center(d, W / 2, 792, "Graceful fallback at every layer — no Azure / no Tavily / no quota "
       "never breaks the app.", f(14), GRAY)

img.save("architecture.png")
print("wrote architecture.png", img.size)
