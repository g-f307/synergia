from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    index = (ROOT / "web/src/index.html").read_text(encoding="utf-8")
    if "Content-Security-Policy" not in index or "unsafe-eval" in index:
        raise SystemExit("Angular CSP is missing or permits unsafe-eval")

    forbidden = ("[innerHTML]", "bypassSecurityTrustHtml", "document.write(")
    violations: list[str] = []
    for path in (ROOT / "web/src").rglob("*"):
        if path.suffix not in {".ts", ".html"}:
            continue
        content = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            if pattern in content:
                violations.append(f"{path.relative_to(ROOT)}: {pattern}")
    if violations:
        raise SystemExit("Unsafe DOM sinks found:\n" + "\n".join(violations))

    print("HTTP, CSP and unsafe DOM sink baseline validated.")


if __name__ == "__main__":
    main()
