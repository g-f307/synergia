"""Consolida manualmente um conjunto de exportações do Production Plan R+F."""
import argparse
import json
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from openpyxl import load_workbook


def consolidate(files):
    columns, sources, records = [], [], []
    keys = set()
    for source_id, path in enumerate(files, 1):
        match = re.fullmatch(r"Production_Plan_(NW\d+)\.xlsx", path.name)
        if not match:
            raise ValueError("Nome fora do padrão do exportador.")
        with ZipFile(path) as archive:
            if archive.testzip():
                raise ValueError(f"XLSX corrompido: {path.name}")
        book = load_workbook(path, read_only=True)
        try:
            if book.sheetnames != ["Production_Plan_R+F"]:
                raise ValueError(f"Aba inesperada: {path.name}")
            sheet = book.active
            # O NFP pode declarar A1 como dimensão de uma planilha inteira.
            sheet.reset_dimensions()
            rows = iter(sheet.rows)
            header = [c.value for c in next(rows, ())]
            dates = header[2:]
            if (header[:2] != ["Plant", "Target ID"] or not dates
                    or not all(isinstance(d, str) and re.fullmatch(r"\d{2}/\d{2}", d) for d in dates)
                    or len(set(dates)) != len(dates) or (columns and dates != columns)):
                raise ValueError(f"Cabeçalho incompatível: {path.name}")
            columns = dates
            tally, summaries = Counter(), []
            for number, row in enumerate(rows, 2):
                if len(row) != len(header):
                    raise ValueError(f"Largura inesperada: {path.name}, linha {number}")
                plant, target = row[0].value, row[1].value
                if target is None and plant in (None, " ") and all(
                    c.data_type == "f" and c.value.startswith("=SUMIFS(") and "null:null" in c.value
                    for c in row[2:]
                ):
                    summaries.append(number)
                    continue
                if not all(isinstance(v, str) and v.strip() for v in (plant, target)):
                    raise ValueError(f"Identificação incompleta: {path.name}, linha {number}")
                if (plant, target) in keys:
                    raise ValueError(f"Plant e Target ID repetidos: {path.name}, linha {number}")
                quantities = {}
                for day, cell in zip(dates, row[2:], strict=True):
                    v = cell.value
                    if v is None:
                        continue
                    if cell.data_type != "n" or type(v) not in (int, float) or v < 0 or v != int(v):
                        raise ValueError(f"Quantidade inesperada: {path.name}, linha {number}, {day}")
                    quantities[day] = int(v)
                keys.add((plant, target))
                tally[plant] += 1
                records.append(dict(source_id=source_id, source_row=number, plant=plant,
                                    target_id=target, quantities_by_day=quantities))
            sources.append(dict(id=source_id, file=path.name, sheet=sheet.title,
                                sha256=sha256(path.read_bytes()).hexdigest(),
                                requested_plant=match[1], requested_plant_present=match[1] in tally,
                                detail_rows=tally.total(), detail_rows_by_plant=dict(tally),
                                excluded_summary_rows=summaries))
        finally:
            book.close()
    return dict(report="Production Plan [R+F]", date_columns=columns, day_format="MM/DD",
                sources=sources, record_count=len(records), records=records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.suffix.lower() != ".json":
        parser.error("O destino deve ser um arquivo JSON.")
    result = consolidate(args.files)
    with NamedTemporaryFile(mode="w", dir=args.output.parent, encoding="utf-8", delete=False) as out:
        temp = Path(out.name)
        try:
            json.dump(result, out, ensure_ascii=False, allow_nan=False, indent=2)
            out.write("\n")
            out.close()
            temp.replace(args.output)
        finally:
            temp.unlink(missing_ok=True)
    print(f"{result['record_count']} registros salvos em {args.output}")
