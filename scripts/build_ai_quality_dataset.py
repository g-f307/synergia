"""Materialize fictional CSV/XLSX pairs and freeze byte hashes, never baseline gold."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/synthetic/ai-quality-v2"


def stable_workbook(headers: list, rows: list) -> bytes:
    workbook = Workbook()
    workbook.active.title = "Dados"
    workbook.active.append(headers)
    for row in rows:
        workbook.active.append(row)
    workbook.properties.created = datetime(2026, 1, 1)
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    result = io.BytesIO()
    # ZIP timestamps and core modified dates otherwise vary between executions.
    with ZipFile(buffer) as archive, ZipFile(result, "w", ZIP_DEFLATED) as output:
        for name in sorted(archive.namelist()):
            content = archive.read(name)
            if name == "docProps/core.xml":
                root = ElementTree.fromstring(content)
                for field in ("created", "modified"):
                    node = root.find(f"{{http://purl.org/dc/terms/}}{field}")
                    if node is not None:
                        node.text = "2026-01-01T00:00:00Z"
                content = ElementTree.tostring(root, encoding="utf-8")
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            output.writestr(info, content)
    return result.getvalue()


def materialize(dataset: Path = DATASET) -> dict:
    document = json.loads((dataset / "scenarios.json").read_text(encoding="utf-8"))
    entries = []
    for case in document["cases"]:
        directory = dataset / case["split"]
        directory.mkdir(parents=True, exist_ok=True)
        for extension in ("csv", "xlsx"):
            path = directory / f"{case['case_id']}.{extension}"
            if case.get("unreadable"):
                content = (
                    b'workorder_number,reason\n"unterminated'
                    if extension == "csv"
                    else b"not a ZIP"
                )
            elif extension == "csv":
                stream = io.StringIO(newline="")
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerows([case["headers"], *case["rows"]])
                content = stream.getvalue().encode()
            else:
                content = stable_workbook(case["headers"], case["rows"])
            path.write_bytes(content)
            entries.append(
                {
                    "case_id": case["case_id"],
                    "split": case["split"],
                    "source": case["source"],
                    "references_available": case["references_available"],
                    "file": path.relative_to(dataset).as_posix(),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    manifest = {
        "dataset_version": document["dataset_version"],
        "scenarios_sha256": hashlib.sha256(
            (dataset / "scenarios.json").read_bytes()
        ).hexdigest(),
        "files": entries,
    }
    (dataset / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def verify(dataset: Path = DATASET) -> list[str]:
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    failures = []
    if (
        hashlib.sha256((dataset / "scenarios.json").read_bytes()).hexdigest()
        != manifest["scenarios_sha256"]
    ):
        failures.append("scenarios.json")
    for item in manifest["files"]:
        path = dataset / item["file"]
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]
        ):
            failures.append(item["file"])
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        failures = verify()
        print(json.dumps({"failures": failures}))
        return int(bool(failures))
    print(json.dumps({"files": len(materialize()["files"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
