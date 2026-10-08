#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd "$script_dir/../.." && pwd)"
kickoff_dir="${KICKOFF_DIR:-$repository_root/Kickoff}"
source_file="$script_dir/demo-day-synergia.tex"
output_file="$script_dir/synergia-demo-day.pdf"

required_files=(
  "synergiakickoff.cls"
  "assets/marca/synergia-horizontal-branca.png"
  "assets/fotos/card-lucas.png"
  "assets/fotos/card-gabriel.png"
  "assets/fotos/card-rebecca.png"
  "assets/fotos/card-marcelo.png"
  "assets/fotos/card-carlos.png"
  "assets/fotos/card-gustavo.png"
)

missing_files=()
for relative_path in "${required_files[@]}"; do
  if [[ ! -f "$kickoff_dir/$relative_path" ]]; then
    missing_files+=("$relative_path")
  fi
done

if ((${#missing_files[@]} > 0)); then
  printf 'Erro: os ativos autorizados do kickoff não foram encontrados em %s.\n' "$kickoff_dir" >&2
  printf 'Arquivos ausentes:\n' >&2
  printf '  - %s\n' "${missing_files[@]}" >&2
  printf 'Obtenha o pacote oficial com o PO ou mentor da equipe e consulte docs/demo-day/README.md.\n' >&2
  exit 2
fi

if ! command -v lualatex >/dev/null 2>&1; then
  printf 'Erro: lualatex não está disponível no PATH.\n' >&2
  exit 3
fi

build_dir="$(mktemp -d "${TMPDIR:-/tmp}/synergia-pitch-build-XXXXXX")"
tex_cache_dir="$(mktemp -d "${TMPDIR:-/tmp}/synergia-tex-cache-XXXXXX")"
cleanup() {
  rm -rf "$build_dir" "$tex_cache_dir"
}
trap cleanup EXIT

cp "$kickoff_dir/synergiakickoff.cls" "$build_dir/"
ln -s "$kickoff_dir/assets" "$build_dir/assets"

(
  cd "$build_dir"
  TEXMFVAR="$tex_cache_dir" lualatex -interaction=nonstopmode -halt-on-error "$source_file"
  TEXMFVAR="$tex_cache_dir" lualatex -interaction=nonstopmode -halt-on-error "$source_file"
)

generated_pdf="$build_dir/demo-day-synergia.pdf"
if [[ ! -f "$generated_pdf" ]]; then
  printf 'Erro: a compilação não gerou %s.\n' "$generated_pdf" >&2
  exit 4
fi

cp "$generated_pdf" "$output_file"
printf 'Apresentação gerada em %s\n' "$output_file"
