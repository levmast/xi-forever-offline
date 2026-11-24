"""The HARDCORE menu's pictures, in all three looks, from the art in art-src (2026-11-23, hardcore modes).

    python hardcore_art.py            needs Pillow + numpy, the fonts the other button scripts use; about ten seconds

Writes, beside the launcher's other buttons (same names in every look, so a theme swaps them like any other button):
    assets\\ui\\hardcore.png, _hover, _off                 the HARDCORE button beside DUALBOX (dualbox_small's size)
    assets\\ui\\hc_card_iron.png, _hover, _off             the mode cards of the Hardcore menu (and steel, silver, and random:
                                                          the randomized mode coming later)
    assets\\press\\vaporwave-ui\\...                       the same names, in the vaporwave look (vice_buttons.py's style)
    assets\\press\\8bit-ui\\...                            the same names, in the 8-bit look (bit_buttons.py's style)

Art: Iron = the Warrior, Steel = the Dark Knight, Silver = the Shadow Lord, Random = the job art (art-src\\ff11-*.jpg, the user's art pack).
These are the first pictures: swap in finished art under the same names whenever it is ready.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps  # noqa: E402

KIT = os.path.abspath(os.path.join(HERE, '..', '..'))
UI = os.path.join(KIT, 'assets', 'ui')
WAVE = os.path.join(KIT, 'assets', 'press', 'vaporwave-ui')
BIT = os.path.join(KIT, 'assets', 'press', '8bit-ui')
SMALL = (244, 72)            # dualbox_small: HARDCORE sits beside it, the same size
CARD = (232, 330)

MODES = {
    'iron':   ('IRON',   'warrior',     (0.05, 0.0, 0.95, 0.80), ((96, 100, 112), (24, 26, 32)),  (196, 200, 210)),
    'steel':  ('STEEL',  'dark-knight', (0.0, 0.0, 1.0, 0.85),   ((60, 84, 120), (12, 18, 34)),   (150, 190, 236)),
    'silver': ('SILVER', 'shadow-lord', (0.0, 0.0, 1.0, 0.80),   ((120, 24, 30), (26, 6, 10)),    (236, 236, 248)),
    # (2026-11-23, the user) a randomized mode is coming later: its card is made now so it is ready
    'random': ('RANDOM', 'job-art',     (0.10, 0.0, 0.90, 0.50),  ((76, 40, 120), (18, 8, 34)),    (230, 200, 255)),
}
TAGLINE = {'iron': 'You earn everything', 'steel': 'Fall, and start again', 'silver': 'Death is final', 'random': 'Fate decides'}


# ------------------------------------------------------------------ the usual look (build.py's)
def default_look():
    import build as B
    import numpy as np
    from lib import frame, grayscale_off, hover_of, font, load, crop_frac, cover, vgrad, radial, text_spaced, unwhite

    B.BUTTONS['hardcore'] = ((325, 96), 'HARDCORE', [('dark-knight', (0.0, 0.0, 1.0, 0.6))], ((120, 24, 30), (30, 6, 10)))
    B.ANCHOR['hardcore'] = 0.5
    im = B.make_button('hardcore', 'dark')
    hv = hover_of(im)
    hv = frame(hv, 10, ((255, 244, 196), (230, 178, 70)), 3, hover=True, ink=(16, 12, 8))
    for state, picture in (('', im), ('_hover', hv), ('_off', grayscale_off(im))):
        picture.convert('RGBA').resize(SMALL, Image.LANCZOS).save(os.path.join(UI, 'hardcore' + state + '.png'))

    for key, (title, art, box, (top, bottom), metal) in MODES.items():
        w, h = CARD
        bg = vgrad(w, h, top, bottom).convert('RGBA')
        glow, gm = radial(w, h, w * 0.5, h * 0.36, w * 0.7, tuple(min(255, int(v * 1.5) + 30) for v in top), 0.5)
        bg = Image.composite(glow.convert('RGBA'), bg, gm)
        picture = cover(crop_frac(load(f'ff11-{art}.jpg'), box), w - 12, int(h * 0.68), 0.5, 0.1)
        if key != 'silver':       # art on white paper: cut the figure out so the card's colour shows round it
            picture = unwhite(picture)
        else:
            picture = picture.convert('RGBA')
        fade = Image.linear_gradient('L').resize(picture.size).point(lambda v: 255 if v < 150 else max(0, 255 - (v - 150) * 3))
        alpha = Image.fromarray((np.asarray(picture.split()[3], dtype=np.float32) * np.asarray(fade, dtype=np.float32) / 255).astype(np.uint8), 'L')
        picture.putalpha(alpha)
        halo = Image.new('RGBA', picture.size, metal + (0,))
        halo.putalpha(alpha.filter(ImageFilter.GaussianBlur(6)).point(lambda v: int(v * 0.5)))
        bg.alpha_composite(halo, (6, 6))
        bg.alpha_composite(picture, (6, 6))
        d = ImageDraw.Draw(bg)
        text_spaced(d, (w / 2, h * 0.79), title, font(40), metal, 4, 'mm', shadow=(0, 0, 0))
        text_spaced(d, (w / 2, h * 0.89), TAGLINE[key].upper(), font(12), (230, 214, 170), 1, 'mm')
        card = frame(bg, 12, ((250, 226, 150), (176, 128, 46)), 3, ink=(16, 12, 8))
        lit = frame(hover_of(card), 12, ((255, 244, 196), (230, 178, 70)), 3, hover=True, ink=(16, 12, 8))
        card.save(os.path.join(UI, f'hc_card_{key}.png'))
        lit.save(os.path.join(UI, f'hc_card_{key}_hover.png'))
        grayscale_off(card).save(os.path.join(UI, f'hc_card_{key}_off.png'))


# ------------------------------------------------------------------ the vaporwave look (vice_buttons.py's)
def wave_look():
    import vice_buttons as V
    V.BUTTONS['hardcore'] = ('HARDCORE', [('dark-knight', (0.0, 0.0, 1.0, 0.6))], 'night')
    normal = V.make_button('hardcore')
    normal.save(os.path.join(WAVE, 'hardcore.png'))
    V.make_button('hardcore', hover=True).save(os.path.join(WAVE, 'hardcore_hover.png'))
    V.off_of(normal).save(os.path.join(WAVE, 'hardcore_off.png'))
    # cards: the usual card in the sunset colours, with a neon rim
    for key in MODES:
        for state in ('', '_hover', '_off'):
            base = Image.open(os.path.join(UI, f'hc_card_{key}{state}.png')).convert('RGBA')
            grey = ImageOps.grayscale(base.convert('RGB'))
            tinted = ImageOps.colorize(grey, (20, 8, 52), (255, 120, 200), mid=(116, 28, 150)).convert('RGBA')
            tinted.putalpha(base.split()[3])
            if state == '_off':
                tinted = ImageEnhance.Color(tinted).enhance(0.15)
            d = ImageDraw.Draw(tinted)
            rim = (64, 226, 240) if state == '_hover' else (255, 64, 196)
            d.rounded_rectangle((1, 1, tinted.width - 2, tinted.height - 2), radius=14, outline=rim, width=3)
            tinted.save(os.path.join(WAVE, f'hc_card_{key}{state}.png'))


# ------------------------------------------------------------------ the 8-bit look (bit_buttons.py's)
def bit_look():
    import bit_buttons as P
    P.UI = UI
    P.BUTTONS['hardcore'] = ('HARDCORE', [('knight', 'Ready_00'), ('black', 'SkillReady_00')], 'red')
    for state, ending in (('normal', ''), ('hover', '_hover'), ('off', '_off')):
        P.make_button('hardcore', state).save(os.path.join(BIT, 'hardcore' + ending + '.png'))
    # cards: a console window with the mode's name and the usual card's picture made of big pixels
    for key, (title, *_rest) in MODES.items():
        for state, ending in (('normal', ''), ('hover', '_hover'), ('off', '_off')):
            w, h = CARD[0] // P.PX, CARD[1] // P.PX
            style = 'off' if state == 'off' else 'blue' + ('_hover' if state == 'hover' else '')
            art = P.window(w, h, style)
            src = Image.open(os.path.join(UI, f'hc_card_{key}.png')).convert('RGB')
            pic = src.crop((10, 10, src.width - 10, int(src.height * 0.70))).resize((w - 8, int(h * 0.62)), Image.BILINEAR)
            pic = pic.quantize(colors=24, method=Image.Quantize.MEDIANCUT).convert('RGBA')
            if state == 'off':
                pic = P.greyed(pic)
            art.alpha_composite(pic, (4, 4))
            colour = P.GREY if state == 'off' else (252, 236, 144) if state == 'hover' else P.WHITE
            tw, th = P.text_size(title, scale=2)
            P.draw_text(art, (w - tw) // 2, int(h * 0.74), title, colour, scale=2, shadow=None if state == 'off' else P.INK)
            P.to_screen(art, CARD).save(os.path.join(BIT, f'hc_card_{key}{ending}.png'))


if __name__ == '__main__':
    default_look()
    wave_look()
    bit_look()
    print('ok')
