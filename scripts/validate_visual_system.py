from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "web/src/styles.css"
SHELL = ROOT / "web/src/app/app.component.html"
SHELL_STYLES = ROOT / "web/src/app/app.component.css"
EVIDENCE = ROOT / "docs/evidence"


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.removeprefix("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _luminance(value: str) -> float:
    channels = []
    for channel in _rgb(value):
        normalized = channel / 255
        linear = (
            normalized / 12.92
            if normalized <= 0.04045
            else ((normalized + 0.055) / 1.055) ** 2.4
        )
        channels.append(linear)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_luminance(foreground), _luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def validate() -> None:
    css = STYLES.read_text(encoding="utf-8").lower()
    shell = (
        SHELL.read_text(encoding="utf-8")
        + SHELL_STYLES.read_text(encoding="utf-8")
    ).lower()
    all_css = css + shell
    required_tokens = {
        "--syn-primary:#a50034",
        "--syn-bg:#f3f4f6",
        "--syn-sidebar-width:260px",
        "--syn-header-height:72px",
        "font-family:lgeiheadline",
        "font-family:lgeitext",
    }
    missing = sorted(token for token in required_tokens if token not in css)
    if missing:
        raise ValueError(f"Tokens visuais ausentes: {missing}")
    for asset in ("logo-horizontal.png", "simbolo.png", "lgeitextttf-regular.ttf"):
        if asset not in css + shell:
            raise ValueError(f"Ativo visual oficial não utilizado: {asset}")
    for breakpoint in ("1365px", "1023px", "767px"):
        if not re.search(rf"@media\([^)]*{breakpoint}", all_css):
            raise ValueError(f"Breakpoint responsivo ausente: {breakpoint}")
    if "data.js" in css + shell or "prototype-pages" in css + shell:
        raise ValueError("A aplicação não pode depender do runtime do protótipo")
    checks = (
        ("#111111", "#ffffff"),
        ("#a50034", "#ffffff"),
        ("#ffffff", "#087f62"),
        ("#ffffff", "#b4232c"),
    )
    failures = [pair for pair in checks if _contrast(*pair) < 4.5]
    if failures:
        raise ValueError(f"Contraste AA insuficiente: {failures}")
    for capture in ("issue-69-login-desktop.png", "issue-69-login-mobile.png"):
        path = EVIDENCE / capture
        if not path.is_file() or path.stat().st_size < 5_000:
            raise ValueError(f"Captura visual ausente ou inválida: {capture}")
    print(
        "Sistema visual validado: tokens, ativos, contraste AA, "
        "3 breakpoints e capturas."
    )


if __name__ == "__main__":
    validate()
