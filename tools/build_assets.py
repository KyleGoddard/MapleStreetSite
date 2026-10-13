"""Rebuilds the site's images and web font from the game's own art.

usage: uv run --with pillow --with fonttools --with brotli tools/build_assets.py GAME_DIR [SHOTS_DIR]

GAME_DIR is the game's godot/ folder. SHOTS_DIR, if given, holds 3x screenshots taken with the
game's --shot flag (hero.png at 1920x1200, the rest at 1920x1080); without it the screenshots
already in img/ are left alone.
"""
import json, os, re, shutil, sys
from PIL import Image
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

game = sys.argv[1]
shots = sys.argv[2] if len(sys.argv) > 2 else None
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
img = os.path.join(site, "img")
os.makedirs(os.path.join(img, "shots"), exist_ok=True)
os.makedirs(os.path.join(site, "fonts"), exist_ok=True)
asset = lambda *p: os.path.join(game, "assets", *p)

# --- straight copies: the site scales these up itself, with image-rendering: pixelated
for src, dst in [("title.png", "logo.png"), ("artifacts.png", "artifacts.png"), ("minigames.png", "minigames.png"),
                 ("props/pumpkin_l_lit.png", "pumpkin_l.png"), ("props/pumpkin_m_lit.png", "pumpkin_m.png"),
                 ("props/pumpkin_s_lit.png", "pumpkin_s.png")]:
    shutil.copy(asset(src), os.path.join(img, dst))

icon = Image.open(asset("icon.png")).convert("RGB")
icon.resize((32, 32), Image.LANCZOS).save(os.path.join(img, "favicon.png"))
icon.resize((180, 180), Image.LANCZOS).save(os.path.join(img, "touch-icon.png"))

# --- costumes: one row per costume, the three front-facing walk frames of a 24x44 sheet
wardrobe = json.load(open(asset("wardrobe.json")))
FW, FH = 24, 44
atlas = Image.new("RGBA", (FW * 3, FH * len(wardrobe["costumes"])))
for row, c in enumerate(wardrobe["costumes"]):
    sheet = Image.open(asset(wardrobe["sheets"][c["id"]][row % 4]["tex"])).convert("RGBA")
    frames = sheet.crop((0, 0, FW * 3, FH))
    if not c["free"]:                     # costumes still to be earned are a secret: only their shadow goes on the site,
        px = frames.load()                # the flat purple shape the costume screen shows for a locked one
        for y in range(FH):
            for x in range(FW * 3):
                alpha = px[x, y][3]
                if alpha:
                    px[x, y] = (107, 61, 184, 255 if alpha > 204 else int(alpha * 0.6))
    atlas.paste(frames, (0, row * FH))
atlas.save(os.path.join(img, "costumes.png"))

# --- screenshots: back down to the game's native pixels, losing any blur from the window's scaling
if shots:
    for f in sorted(os.listdir(shots)):
        if not f.endswith(".png"):
            continue
        im = Image.open(os.path.join(shots, f)).convert("RGB")
        im = im.resize((im.width // 3, im.height // 3), Image.NEAREST)
        if f == "hero.png":
            im = im.crop((0, 28, im.width, im.height - 50))      # lose the HUD, top and bottom
            im.save(os.path.join(img, "hero.png"), optimize=True)
            # the link preview: the street, dimmed as the title screen dims it, under the logo
            og = im.resize((im.width * 2, im.height * 2), Image.NEAREST)
            og = og.crop(((og.width - 1200) // 2, 0, (og.width + 1200) // 2, 630)).convert("RGBA")
            og = Image.alpha_composite(og, Image.new("RGBA", og.size, (8, 5, 18, 150)))
            logo = Image.open(asset("title.png")).convert("RGBA")
            logo = logo.resize((logo.width * 4, logo.height * 4), Image.NEAREST)
            og.alpha_composite(logo, ((1200 - logo.width) // 2, (630 - logo.height) // 2))
            og.convert("RGB").save(os.path.join(img, "og.png"), optimize=True)
        else:                             # kept at 2x: the page scales these down, and that wants spare pixels
            im.resize((im.width * 2, im.height * 2), Image.NEAREST).save(os.path.join(img, "shots", f), optimize=True)

# --- the game's 5x7 bitmap font, as a web font: one square per pixel, 8 pixels to the em
fnt = open(asset("font.fnt")).read()
strip = Image.open(asset("font.png")).convert("RGBA")
PX, EM = 100, 800
glyphs, cmap, metrics = {}, {}, {}

def outline(x0, y0, w, h):
    pen = TTGlyphPen(None)
    for y in range(h):
        x = 0
        while x < w:
            if strip.getpixel((x0 + x, y0 + y))[3] > 127:
                run = x
                while x < w and strip.getpixel((x0 + x, y0 + y))[3] > 127:
                    x += 1
                top, bot = (7 - y) * PX, (6 - y) * PX
                pen.moveTo((run * PX, bot)); pen.lineTo((run * PX, top))
                pen.lineTo((x * PX, top)); pen.lineTo((x * PX, bot)); pen.closePath()
            else:
                x += 1
    return pen.glyph()

glyphs[".notdef"] = TTGlyphPen(None).glyph(); metrics[".notdef"] = (6 * PX, 0)
for m in re.finditer(r"char id=(\d+) x=(\d+) y=(\d+) width=(\d+) height=(\d+) xoffset=(-?\d+) yoffset=(-?\d+) xadvance=(\d+)", fnt):
    cp, x, y, w, h, _, _, adv = map(int, m.groups())
    name = "u%04X" % cp
    glyphs[name] = outline(x, y, w, h); cmap[cp] = name; metrics[name] = (adv * PX, 0)
if 32 not in cmap:
    glyphs["space"] = TTGlyphPen(None).glyph(); cmap[32] = "space"; metrics["space"] = (4 * PX, 0)
cmap.setdefault(0xA0, cmap[32])
fb = FontBuilder(EM, isTTF=True)
fb.setupGlyphOrder(list(glyphs))
fb.setupCharacterMap(cmap)
fb.setupGlyf(glyphs)
fb.setupHorizontalMetrics(metrics)
fb.setupHorizontalHeader(ascent=7 * PX, descent=-PX)
fb.setupNameTable({"familyName": "Maple Street", "styleName": "Regular"})
fb.setupOS2(sTypoAscender=7 * PX, sTypoDescender=-PX, sTypoLineGap=0, usWinAscent=7 * PX, usWinDescent=PX, sxHeight=7 * PX, sCapHeight=7 * PX)
fb.setupPost()
fb.font.flavor = "woff2"
fb.save(os.path.join(site, "fonts", "maple.woff2"))
print("built:", ", ".join(sorted(os.listdir(img))), "and fonts/maple.woff2 with", len(cmap), "characters")
