# Evidência de validação — Issue #231 (Orçamento de prompt, schema e runtime real no Qwen3)

## Metadados da execução

- **Issue**: [#231](https://github.com/g-f307/synergia/issues/231)
- **Branch / Commit de código avaliado**: `fix/231-ai-assistance-runtime-budget` — `84a86c4e01cf755eb61413d85eba67e3046a6c8d` (`84a86c4`)
- **Runtime**: Ollama `0.40.15` (`llamacpp`, `OLLAMA_HOST=0.0.0.0:11434`)
- **Modelo e digest pinados**: `qwen3:4b-instruct-2507-q4_K_M` (`sha256:0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`)
- **Opções enviadas pelo provider (`backend/app/ai_assistance_provider.py`)**: `temperature=0`, `seed=42`, `num_ctx=8192`, `num_predict=1536` (timeout HTTP/provider preservado em `30 s`, sem enfraquecer validações nem alterar o contrato `1.0.0`)
- **Hardware**: AMD Ryzen 7 5800H (16 threads) + NVIDIA GeForce GTX 1650 (4096 MiB VRAM, driver `620.70.06`), Fedora Linux 45
- **Alocação observada (`ollama ps`)**: `3.5 GB`, `21%/79% CPU/GPU`, `CONTEXT 8192`

## Revisão do schema dinâmico e compactação do prompt

1. **Deduplicação em `$defs.Finding`**: `request_schema["$defs"]["Finding"]` usa exclusivamente `anyOf` (sem repetir `properties`/enums planos), vinculando diretamente `title`, `explanation` e `evidence_refs` via `const` para os até 2 grupos mais prioritários de `deterministic_triage_findings(context)` (`minItems=1`, `maxItems=len(triage_preview)`). O validador `_decode` continua validando integralmente contra o contexto completo (até 5 achados) e o fallback determinístico permanece inalterado.
2. **Projeção compacta do prompt**: `prepare_prompt` valida o snapshot canônico completo (`serialize_snapshot`/`canonical_bytes`), mas projeta no bloco `data` do prompt apenas os itens referenciados pelos achados priorizados (mais 1 representante por seção não vazia, preservando `counts`, `sufficiency`, `truncated_sections` e `required_limitations`), acompanhado de um `prompt_hint` compacto (`summary`, `human_checks`, `limitations`, `findings_max`) sem duplicar o schema JSON inteiro no texto do usuário.

### Tamanhos medidos no commit `84a86c4`

| Cenário | `prompt` (bytes) | `request_schema` (bytes) | Ramos `anyOf` | Referências no contexto |
| --- | ---: | ---: | ---: | ---: |
| Pequeno (importação válida 1 linha `GMES/OQC`) | 2.501 | 1.818 | 2 | 11 |
| `GMES/OQC` 3 linhas | 2.485 (antes 8.482) | 1.761 (antes 4.459) | 2 | 15 |
| `GMES/OQC` 24 linhas | 3.041 (antes 10.439) | 2.016 (antes 3.228) | 2 | 26 |
| `wo-composite.xlsx` | 2.899 (antes 7.119) | 1.990 (antes 2.850) | 2 | 24 |

## Validação automatizada (commit `84a86c4`)

- **Testes unitários de IA** (`test_ai_assistance_generator.py`, `provider`, `service`, `context`, `campaign`): **111/111 aprovados**, incluindo validação positiva e negativa contra o próprio `request_schema` enviado ao Ollama para contextos pequeno, agrupado e truncado.
- **Corpus congelado**: `python scripts/generate_ai_assistance_corpus.py --verify` aprovado (`manifest_sha256: 5e775bb47ae5d63a5f5e30730b85f94690f1d23e85738567f034a3db656a0bf0`).
- **Campanha controlada (`ci-fake`)**: **30/30 aprovados** (`27 ready` com `origin=model`, `3 insufficient_evidence` determinísticos, `0 rejected`, `0 unavailable`, microbenchmark `prepare_prompt` p95 = `1,570 ms`).
- **Lint e higiene**: `ruff check` e `git diff --check` aprovados.

## Matriz de validação real a frio no endpoint HTTP (`http://127.0.0.1:18001`, timeout real de 30 s)

Execução sequencial a frio (sem cache prévio para o novo `prompt_hash` do commit `84a86c4`; rate limit limpo apenas para isolar a matriz; timeout rigorosamente em `30 s` e validações intactas).

| Cenário (`execution_id`) | HTTP | Tempo total | `state` | `origin` | Achados retornados | Resolução de referências (API `0.17.0`) |
| --- | :---: | ---: | --- | --- | --- | --- |
| **1. Pequeno — importação válida 1 linha `GMES/OQC`** (`2f8a1b9f-1a6e-4a87-9902-058925907314`, 2 pend., 2 clas.) | `200` | `20.249 ms` | `ready` | `model` | `2`: `[Pendência aberta em Qualidade: oqc_pending]` (`WO-SM-021B2F`) e `[Pendência aberta em Qualidade: missing_reason]` (`WO-SM-021B2F`) | **2/2 `PEN-*` resolvidas** em `GET /pending-items` (`page=1/1`, `matched=true`) |
| **2. `GMES/OQC` 3 linhas** (`933b404b-3d14-41ad-a70e-7788f3c321ce`, 4 pend., 4 clas.) | `200` | `19.792 ms` | `ready` | `model` | `2`: `[Pendência aberta: oqc_hold]` (`WO-90A70F-002`) e `[Pendência aberta em Qualidade: oqc_pending]` (`WO-90A70F-001`) | **2/2 `PEN-*` resolvidas** em `GET /pending-items` (`page=1/1`, `matched=true`) |
| **3. `GMES/OQC` 24 linhas** (`686bd231-c8f7-4c8d-b75d-dd9d3ae09fbc`, 44 pend., 44 clas., 1 aviso) | `200` | `24.765 ms` | `ready` | `model` | `2`: `[Pendência aberta: oqc_hold]` (`WO-B81EE7-022`, 1 `PEN-*`) e `[Pendência aberta em Qualidade: oqc_pending]` (3 `PEN-*` agrupadas) | **4/4 `PEN-*` resolvidas** em `GET /pending-items`: `PEN-8f460740...` → **`page=3/3` (`matched=true`)**; 3 `PEN-*` → `page=1/3` (`matched=true`) |
| **4. `wo-composite.xlsx`** (`176bcf47-8fa9-413e-8e2c-78253b651316`, 41 erros, 3 avisos) | `200` | `27.948 ms` | `ready` | `model` | `2`: `[Divergência (error): invalid_header]` (3 `DIV-*` em `structure`) e `[Divergência (error) em record]` (3 `DIV-*` em `record`) | **6/6 `DIV-*` resolvidas** em `GET /divergences` (`page=1/3`, `matched=true`) |

### Histórico de falhas intermediárias preservadas (antes da projeção compacta e limite de 2 grupos)

- No commit intermediário `5161a18` (somente deduplicação `anyOf` com até 5 grupos, sem projeção compacta do `data` no prompt): os cenários `GMES/OQC 3 linhas`, `GMES/OQC 24 linhas` e `wo-composite.xlsx` a frio expiraram em `HTTP 504` (`~29,1 s`) por excesso de tokens de entrada (`2.827`–`4.328` tokens) somados à geração de 5 achados em offload parcial (`21%/79% CPU/GPU` na GTX 1650 de 4 GB).
- No commit `3f6bec0` (projeção compacta com até 3 grupos): `Pequeno` (`25,0 s`) e `GMES/OQC 3 linhas` (`25,4 s`) concluíram em `ready`, enquanto `GMES/OQC 24 linhas` e `wo-composite.xlsx` ainda atingiram `HTTP 504` (`~29,1 s`) por gerarem ~410 tokens de saída com 9 hashes de referência.
- Com o ajuste final em `84a86c4` (até 2 grupos priorizados no schema da requisição), **4/4 cenários obrigatórios concluíram a frio em `HTTP 200` (`state=ready`, `origin=model`) entre `19,8 s` e `27,9 s`**, com **14/14 referências resolvidas (`matched=true`)**, incluindo resolução automática da página `3/3` no cenário de 24 linhas.

## Conclusões

- **Orçamento de contexto (`num_ctx=8192`) e compactação**: nenhuma falha de estouro de `4096` tokens (`HTTP 503`) ocorreu nos 4 cenários; os prompts ficaram entre `2.485 B` e `3.041 B`.
- **Integridade do JSON (`num_predict=1536`)**: não foi observado truncamento de JSON (`invalid_json`) em nenhuma das 4 respostas concluídas nesta matriz.
- **Margem na GTX 1650 (4 GB VRAM)**: o cenário mais denso (`wo-composite.xlsx`) concluiu a frio em `27,9 s` operando em `79% GPU / 21% CPU` (margem estreita de ~2 s frente ao limite de `30 s` nesse hardware específico); em GPUs com ≥ 6–8 GB de VRAM (100% offload), a margem tende a ser substancialmente maior.
