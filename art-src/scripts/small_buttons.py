"""Smaller copies of launcher buttons for places where the full-size one is too heavy: the Play page's DUALBOX sits
beside PLAY at three quarters of its size. Made from the finished pictures in assets\\ui, so they stay in step.
Usage: python small_buttons.py [kit folder]   ->  assets\\ui\\dualbox_small.png, _hover, _off"""
import os
import sys
from PIL import Image

SMALL = {"dualbox": (244, 72)}

if __name__ == "__main__":
    kit = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    ui = os.path.join(kit, "assets", "ui")
    for name, size in SMALL.items():
        for suffix in ("", "_hover", "_off"):
            source = os.path.join(ui, f"{name}{suffix}.png")
            if os.path.exists(source):
                Image.open(source).convert("RGBA").resize(size, Image.LANCZOS).save(os.path.join(ui, f"{name}_small{suffix}.png"))
    print("ok")
