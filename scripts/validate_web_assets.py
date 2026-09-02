from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PUBLIC = WEB / "public"
SOURCE = WEB / "src"
ASSET_REFERENCE = re.compile(r"(?:url\(['\"]?|(?:src|href)=['\"])(/assets/[^)'\"]+)")


def validate() -> int:
    missing: list[str] = []
    runtime_files = [
        path
        for path in SOURCE.rglob("*")
        if path.is_file() and path.suffix in {".css", ".html", ".ts"}
    ]
    for path in runtime_files:
        text = path.read_text(encoding="utf-8")
        if "prototype-pages" in text or "prototype-v1.0" in text:
            raise ValueError(f"Dependencia do prototipo em runtime: {path}")
        for reference in ASSET_REFERENCE.findall(text):
            target = PUBLIC / reference.removeprefix("/")
            if not target.is_file():
                missing.append(f"{path.relative_to(ROOT)} -> {reference}")
    if missing:
        raise ValueError("Referencias de ativos ausentes:\n" + "\n".join(missing))
    required = [
        PUBLIC / "assets/logos/logo-horizontal.png",
        PUBLIC / "assets/logos/logo-negativa-horizontal.png",
        PUBLIC / "assets/fonts/LGEITextTTF-Regular.ttf",
        PUBLIC / "assets/fonts/JetBrainsMono-Regular.ttf",
    ]
    absent = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if absent:
        raise ValueError(f"Ativos obrigatorios ausentes: {absent}")
    print(f"Ativos web validados: {len(runtime_files)} arquivos de codigo")
    return 0


if __name__ == "__main__":
    raise SystemExit(validate())
