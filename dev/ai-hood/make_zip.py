"""Builds the zip we send Sunie: python make_zip.py [folder to put it in]   (default: this folder)
The .sh files keep their "can be run" mark inside the zip."""
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "XIFO-AI-hood.zip"
FILES = ("README.txt", "add-ai-hood.sh", "remove-ai-hood.sh", "add-ai-hood.bat", "remove-ai-hood.bat")


def build(target_dir=HERE):
    path = os.path.join(target_dir, NAME)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            with open(os.path.join(HERE, name), "rb") as handle:
                data = handle.read()
            info = zipfile.ZipInfo("XIFO-AI-hood/" + name, date_time=(2026, 11, 22, 18, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3                                   # Unix: so the mode below is used when unzipping
            info.external_attr = (0o755 if name.endswith(".sh") else 0o644) << 16
            z.writestr(info, data)
    return path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else HERE))
