# Evidência de validação — Issue #231 (Orçamento de prompt, schema e runtime real no Qwen3)

## Metadados da execução

- **Issue**: [#231](https://github.com/g-f307/synergia/issues/231)
- **Branch / Commit avaliado**: `fix/231-ai-assistance-runtime-budget` — `5161a187d53f1f29003834aca8472af68aa13fe0` (`5161a18`)
- **Runtime**: Ollama `0.40.15` (`llamacpp`, `OLLAMA_HOST=0.0.0.0:11434`)
- **Modelo e digest pinados**: `qwen3:4b-instruct-2507-q4_K_M` (`sha256:0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`)
- **Opções enviadas pelo provider (`backend/app/ai_assistance_provider.py`)**: `temperature=0`, `seed=42`, `num_ctx=8192`, `num_predict=1536` (sem aumento do timeout de `30 s` e sem afrouxar validações)
- **Hardware**: AMD Ryzen 7 5800H (16 threads) + NVIDIA GeForce GTX 1650 (4096 MiB VRAM, driver `620.70.06`), Fedora Linux 45
- **Alocação observada (`ollama ps`)**: `3.5 GB`, `21%/79% CPU/GPU`, `CONTEXT 8192`

## Revisão do schema dinâmico (`$defs.Finding`)

Para eliminar a duplicação entre enums planos (`properties`) e ramos coerentes (`anyOf`) preservando o vínculo exato entre `title`, `explanation` e `evidence_refs`:

- `request_schema["$defs"]["Finding"]` passou a usar exclusivamente `anyOf` (um ramo por achado priorizado de `deterministic_triage_findings`, com `const` para `title`, `explanation` e `evidence_refs`), sem repetir `properties`/enums planos no mesmo objeto.
- O prompt de usuário (`TEMPLATE`) recebe um `prompt_schema` compacto (`separators=(",", ":")`) contendo os enums essenciais (`summary`, `human_checks`, `limitations` e prévia dos títulos/explicações), sem duplicar listas de `evidence_refs`.
- Impacto medido:
  - `GMES/OQC 3 linhas`: `prompt` reduziu de `8.482 B` para `6.606 B`; `request_schema` reduziu de `4.459 B` para `2.909 B` (`-35%`).
  - Microbenchmark `prepare_prompt` p95 (campanha `ci-fake`, 30 casos): reduziu de `4,441 ms` (com `properties` + `anyOf`) para `1,527 ms` (apenas `anyOf`, sem duplicação).

| Cenário | `prompt` (bytes) | `request_schema` (bytes) | Ramos `anyOf` | Referências no contexto |
| --- | ---: | ---: | ---: | ---: |
| Pequeno (1 divergência) | 3.270 | 2.091 | 3 | 3 |
| `GMES/OQC` 3 linhas | 6.606 | 2.909 | 5 | 15 |
| `GMES/OQC` 24 linhas | 10.439 | 3.228 | 5 | 26 |
| `wo-composite.xlsx` | 7.119 | 2.850 | 5 | 24 |

## Validação automatizada (commit `5161a18`)

- **Testes unitários de IA** (`test_ai_assistance_generator.py`, `provider`, `service`, `context`, `campaign`): **111/111 aprovados**, incluindo validação positiva e negativa contra o próprio `request_schema` enviado ao Ollama para contextos pequeno, agrupado e truncado.
- **Corpus congelado**: `python scripts/generate_ai_assistance_corpus.py --verify` aprovado (`manifest_sha256: 9efa569ebd5eb49b99d45a015c69e7a987bb0f20e005fe6a53e65bf3770405bc`).
- **Campanha controlada (`ci-fake`)**: **30/30 aprovados** (`27 ready` com `origin=model`, `3 insufficient_evidence` determinísticos, `0 rejected`, `0 unavailable`, p95 `1,527 ms`).
- **Lint e higiene**: `ruff check` e `git diff --check` aprovados.

## Matriz de validação real no endpoint HTTP (`http://127.0.0.1:18001`, timeout real de 30 s)

Execução sequencial sem seleção de tentativas favoráveis (rate limit limpo apenas para isolar a matriz; sem alteração de timeout nem de validações). Todas as falhas ocorridas estão preservadas abaixo.

| Cenário (`execution_id`) | HTTP | Tempo total | `state` / erro | `origin` | Achados retornados | Resolução de referências (API `0.17.0`) |
| --- | :---: | ---: | --- | --- | --- | --- |
| **1. Pequeno — 1 divergência** (`632ea040-054b-4699-b112-3c69e1d459fd`) | `200` | `21.166 ms` | `ready` | `model` | `1`: `[Evidência registrada]` (`EVI-0d8a3c0e...`) | `GET /evidences?page=1&reference=EVI-0d8a3c0e...` → `page=1/0`, `matched=false` (execução legada no banco sem linha em `file_inspections`) |
| **2. `GMES/OQC` 3 linhas** (`933b404b-3d14-41ad-a70e-7788f3c321ce`, 4 pend., 4 clas.) | `504` | `29.100 ms` | `ai_assistance_timeout` (`runtime_timeout`) | `deterministic` (abandono) | — | Não executada (falha por timeout de 30 s) |
| **3. `GMES/OQC` 24 linhas** (`686bd231-c8f7-4c8d-b75d-dd9d3ae09fbc`, 44 pend., 44 clas., 1 aviso) | `504` | `29.096 ms` | `ai_assistance_timeout` (`runtime_timeout`) | `deterministic` (abandono) | — | Resolução direta da página 3 validada separadamente (`PEN-e273b86e...` → `page=3`, `matched=true`) |
| **4. `wo-composite.xlsx` — rodada a frio na matriz** (`176bcf47-8fa9-413e-8e2c-78253b651316`, 41 erros, 3 avisos) | `504` | `29.100 ms` | `ai_assistance_timeout` (`runtime_timeout`) | `deterministic` (abandono) | — | Não executada nesta tentativa (falha por timeout de 30 s) |
| **4b. `wo-composite.xlsx` — rodada com prefixo em cache** (`176bcf47-8fa9-413e-8e2c-78253b651316`, pré-deduplicação `anyOf`, mesmo timeout de 30 s) | `200` | `23.897 ms` | `ready` | `model` | `2`: `[Divergência (error): invalid_header]` (3 `DIV-*`) e `[Divergência (error) em record]` (3 `DIV-*`) | **6/6 `DIV-*` resolvidas** em `GET /divergences?page=1&reference=...` (`page=1/3`, `matched=true`) |

## Diagnóstico e limites observados

1. **Eliminados pela #231**:
   - **Estouro de `4096` tokens (`HTTP 503 ai_assistance_runtime_unavailable`)**: eliminado em todos os 4 cenários com `num_ctx=8192` e compactação do prompt.
   - **Truncamento de JSON (`invalid_json` por `num_predict=768`)**: eliminado com `num_predict=1536` e JSON compacto em linha única.
   - **Duplicação de enums no schema dinâmico**: eliminada substituindo `properties` planos por `anyOf` em `$defs.Finding`.
2. **Limite de hardware restante na GTX 1650 (4 GB VRAM)**:
   - Com `num_ctx=8192`, o modelo `qwen3:4b-instruct-2507-q4_K_M` ocupa `3,5 GB` e opera em offload parcial (`79% GPU / 21% CPU`). Nesse hardware, prompts acima de ~2.500 tokens a frio ainda podem exceder o orçamento de `30 s` (`HTTP 504 ai_assistance_timeout`).
   - O timeout de `30 s` e as validações de grounding/persistência foram mantidos intactos.
