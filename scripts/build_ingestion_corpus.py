"""Explicitly write frozen fixtures, or verify bytes and expected adapter results."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ingestion_corpus import (  # noqa: E402
    CONFIGURATION,
    CORPUS,
    VERSION,
    canonical,
    corpus_cases,
    digest,
    execute,
    golden,
    verify_manifest,
)


def write(directory):
    directory.mkdir(parents=True, exist_ok=True)
    cases = []
    for name, source, content in corpus_cases():
        workbook = directory / f"{name}.xlsx"
        workbook.write_bytes(content)
        report, result = execute(workbook, source)
        expected = canonical(golden(report, result))
        (directory / f"{name}.json").write_bytes(expected)
        cases.append(
            {
                "id": name,
                "source": source,
                "input": workbook.name,
                "input_sha256": digest(content),
                "golden": f"{name}.json",
                "golden_sha256": digest(expected),
            }
        )
    (directory / "manifest.json").write_bytes(
        canonical(
            {
                "generator_version": VERSION,
                "schema_version": VERSION,
                "seed": 141,
                "contains_real_data": False,
                "configuration": CONFIGURATION,
                "cases": cases,
            }
        )
    )


def verify(directory):
    manifest = verify_manifest(directory)
    generated = {name: content for name, _, content in corpus_cases()}
    if set(generated) != {case["id"] for case in manifest["cases"]}:
        raise ValueError("Cobertura do corpus divergente")
    for case in manifest["cases"]:
        if digest(generated[case["id"]]) != case["input_sha256"]:
            raise ValueError("Regeneração não reproduz fixture congelada")
        report, result = execute(directory / case["input"], case["source"])
        expected = json.loads((directory / case["golden"]).read_text())
        if golden(report, result) != expected:
            raise ValueError("Resultado diverge do gabarito congelado")
    print(f"Corpus de ingestão: {len(manifest['cases'])} casos verificados")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--directory", type=Path, default=CORPUS)
    args = parser.parse_args()
    if args.write:
        # Generation is explicit and never performed by verification or tests.
        with tempfile.TemporaryDirectory() as temp:
            write(Path(temp))
            args.directory.mkdir(parents=True, exist_ok=True)
            for path in Path(temp).iterdir():
                (args.directory / path.name).write_bytes(path.read_bytes())
    else:
        verify(args.directory)


if __name__ == "__main__":
    main()
