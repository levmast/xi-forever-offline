"""A thank-you banner for a release, in the launcher's look (parchment, the official FFXI job art, our wordmark).
Usage: python3 thanks.py OUT.png [VERSION]        (2026-11-22, for the v0.3.0 announcement in Discord)"""
import sys
from lib import *
from promo import lineup, logo, rule, line, footer, edge, INK
from wordmark import NAVY


def thanks(version, W=1920, H=1080, names=('paladin', 'white-mage', 'black-mage', 'thief'), seed=27):
    s = H / 540
    bg = parchment(W, H, seed)
    split = 0.45
    lineup(bg, names, int(W * split), W - int(28 * s), H - int(20 * s), int(H * 0.78))
    out = bg.convert('RGBA')
    cx = W * split / 2 + 8 * s
    lw = W * split - 70 * s
    y = logo(out, cx, H * 0.09, lw, H * 0.27)
    rule(out, cx, y + 28 * s, lw * 0.36, s)
    line(out, cx, y + 76 * s, 'THANK YOU,', round(38 * s), NAVY, round(5 * s), maxw=lw)
    line(out, cx, y + 122 * s, 'ADVENTURERS', round(38 * s), NAVY, round(5 * s), maxw=lw)
    y2 = y + 178 * s
    for text in ('To everyone who plays, tests, reports bugs,',
                 'shares ideas and stands behind this project.',
                 '',
                 f'{version} is out  ·  from Hurami and the team'):
        if text:
            line(out, cx, y2, text, round(17 * s), INK if 'is out' in text else NAVY, maxw=lw)
        y2 += 30 * s
    footer(out, s, cx, W * split - 40 * s)
    return edge(out, s)


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'thank-you.png'
    thanks(sys.argv[2] if len(sys.argv) > 2 else 'v0.3.0').convert('RGB').save(out, quality=92)
    print('wrote', out)
