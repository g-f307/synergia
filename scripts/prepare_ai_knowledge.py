"""Verify synthetic assets or render readable knowledge; never runs a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_knowledge import DATA, read, validate_corpus


def render_cards(cards: list[dict]) -> str:
    lines = [
        "# Fichas experimentais da PoC #183",
        "",
        "Material fictício, sem homologação operacional. Gerado de "
        "`data/synthetic/ai-knowledge-v1/knowledge.json`; não editar separadamente.",
        "",
        "Indício compatível não é causa comprovada. Procedimentos são apenas "
        "verificações humanas no domínio simulado.",
        "",
    ]
    for card in cards:
        lines += [
            f"## {card['id']} — {card['title']}",
            "",
            f"Versão {card['version']}; estado `{card['status']}`; "
            f"trecho `{card['passage_id']}`.",
            "",
            card["situation"],
            "",
            f"**Escopo:** {card['scope']}",
            "",
            f"**Vocabulário:** {', '.join(card['vocabulary'])}.",
            "",
        ]
        for state, criterion in card["criteria"].items():
            lines += [f"- `{state}`: {criterion}"]
        lines += [
            "",
            f"**Verificação {card['verification']['id']}:** "
            + card["verification"]["text"],
            "",
            card["display_policy"],
            "",
            card["limits"],
            "",
            f"**Campos pertinentes:** {', '.join(card['fact_fields'])}.",
            "",
        ]
        if card["status"] == "archived":
            lines += [
                f"Substituída por `{card['superseded_by']}`; excluída por código.",
                "",
            ]
        if "examples" in card:
            lines += [
                "**Exemplo de desenvolvimento:** " + card["examples"]["positive"],
                "",
                "**Contraexemplo:** " + card["examples"]["counterexample"],
                "",
                "Os exemplos ficam fora do prompt inicial; uso posterior exige "
                "variante de desenvolvimento registrada.",
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["verify", "render"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = validate_corpus()
    if args.command == "render":
        if args.output is None:
            parser.error("render requires --output")
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(render_cards(read(DATA / "knowledge.json")))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
