# Revisão consolidada da preparação do piloto — issue #146 / PR #160

## Escopo e estado

Esta revisão parte de `22deec9` e verifica novamente os pedidos das quatro
rodadas do PR, independentemente de terem sido descritos como resolvidos.
Ela valida o mecanismo de decisão; **não registra uma execução assistida**.
O registro oficial continua `not_decided`, com 12 cenários pendentes, seis
pré-condições pendentes e nenhum aceite aprovado. A issue #146 permanece aberta.

## Matriz de atendimento

Os testes estão em
[`test_stage6_pilot.py`](../../backend/tests/test_stage6_pilot.py). Cada entrada
abaixo foi exercitada na revisão consolidada, além da leitura do código.

| Rodada / pedido | Regra conferida | Testes principais |
| --- | --- | --- |
| R1 — coleções vazias ou incompletas | Conjuntos exatos de pré-condições, dependências, cenários e critérios | `test_review_collection_contract` |
| R1 — SMTP condicional | PC-06 define a obrigatoriedade de S-12 e as decisões permitidas | `test_smtp_release_matrix` |
| R1 — campos compostos sensíveis | Nomes normalizados são inspecionados recursivamente | `test_credential_shaped_fields_are_forbidden` |
| R1 — critérios pendentes | Todos os critérios devem ter o estado específico exigido para liberar | `test_every_unresolved_criterion_blocks_release`, `test_criterion_status_cannot_be_swapped` |
| R1 — arquivo genérico como evidência | Evidência executada deve ter arquivo dedicado por cenário | `test_execution_evidence_must_be_in_evidence_directory`, `test_execution_evidence_must_match_and_belong_to_scenario` |
| R2 — cenários principais opcionais | S-01–S-11 permanecem obrigatórios | `test_every_core_scenario_remains_required` |
| R2 — exceção ampla para falhas | Falha em qualquer cenário principal impede as duas formas de liberação | `test_core_failure_blocks_both_release_decisions` |
| R2 — critérios bloqueados ou apenas ensaiados | `blocked`, `pending` e `rehearsed` impedem liberação | `test_every_unresolved_criterion_blocks_release` |
| R2 — vínculo de evidência | Arquivo, ID, estado e sanitização devem corresponder ao cenário | `test_execution_evidence_must_match_and_belong_to_scenario`, `test_execution_metadata_and_result_contract` |
| R2 — duplicatas | As quatro coleções contratuais possuem IDs únicos | `test_review_collection_contract` |
| R3 — troca de estados entre critérios | AC-08 exige `ci_gate`; os demais exigem `accepted` | `test_criterion_status_cannot_be_swapped` |
| R3 — evidência sem registro da execução | Instante com fuso, ambiente, papel e resultados tipados são obrigatórios | `test_execution_metadata_and_result_contract` |
| R4 — resultados vazios | Ao menos uma contagem, código ou observação válida é necessária; espaços são recusados | `test_execution_needs_meaningful_results`, `test_each_sanitized_result_kind_is_sufficient` |
| R4 — credenciais e caminhos internos | Formatos com espaço ou separador e caminhos Unix, Windows e UNC são recusados | `test_sensitive_observation_variants_are_rejected` |

## Correções complementares

- A exceção de falha SMTP requer uma limitação `accepted` vinculada a S-12,
  com responsável e prazo. Uma limitação não relacionada não serve de aceite
  (`test_smtp_exception_needs_accepted_related_limitation`).
- Tipos JSON incorretos e membros malformados são recusados com `ValueError`,
  em vez de erros incidentais de acesso a propriedades ou de hash
  (`test_malformed_collections_are_rejected_clearly`,
  `test_malformed_collection_members_are_rejected_clearly`).
- Justificativas, responsáveis e rótulos também são inspecionados quanto aos
  formatos sensíveis reconhecidos; mensagens de erro não repetem os valores
  recebidos (`test_sensitive_text_is_rejected_beyond_observations`,
  `test_cli_errors_do_not_echo_supplied_values`).
- Datas futuras e links simbólicos para fora do repositório são recusados
  (`test_execution_metadata_and_result_contract`,
  `test_external_symlink_cannot_supply_execution_evidence`).
- Na autorrevisão, foram conferidas 1.638 alterações de valores nas folhas do
  registro, sem exceções inesperadas nesses casos. Dois casos complementares
  revelaram lacunas e foram corrigidos: cabeçalhos que aceitavam booleanos ou
  decimais em lugar de inteiros e links simbólicos circulares que causavam
  `RuntimeError`. Há regressões específicas para ambos e para o CLI lendo JSON
  inválido (`test_schema_header_requires_actual_integers`,
  `test_circular_evidence_symlink_is_rejected_clearly`,
  `test_cli_invalid_document_is_rejected_without_traceback`).
- O relógio dos testes é fixo, sem dependência de SMTP, credenciais ou serviços
  externos. A fixture copia somente os arquivos de referência declarados no
  contrato, sem copiar todo `docs/`, arquivos ignorados ou planilhas locais.

## Validação executada

O primeiro checkpoint ampliado reproduziu **42 falhas e 140 testes aprovados**.
Depois das correções:

| Verificação | Resultado |
| --- | --- |
| `backend/.venv/bin/python -m pytest -q backend/tests/test_stage6_pilot.py` | **246 aprovados** (46 existentes e 200 adicionais) |
| `backend/.venv/bin/python -m pytest -q -m 'not integration' backend/tests` | **1281 aprovados**, 672 testes de integração não selecionados; 15 avisos de depreciação Starlette |
| `backend/.venv/bin/ruff check backend scripts` | Aprovado |
| Validador Etapa 6 | `not_decided`, zero execuções, seis pré-condições pendentes, zero aceites |
| Validadores Etapa 5, identidade e observabilidade da homologação | Aprovados; decisões externas continuam pendentes |
| Modelo de ameaças, matriz de acesso, mapa de jornadas, HTTP, matriz de segurança e `security_release.py validate` | Aprovados |
| `git diff --check` | Aprovado |

A execução sem integração exigiu permissão para os testes HTTP locais. Uma
tentativa inicial esgotou o espaço temporário porque a fixture antiga copiava
todo `docs/` por caso; foram removidas somente as cópias temporárias dessa
execução e a fixture foi corrigida antes de repetir a validação.

## Limitações e revisão humana

Não foram executados nesta correção testes de integração PostgreSQL, containers,
E2E, envio real de e-mail, backup, restauração ou rollback. As referências desses
ensaios anteriores não representam uma nova execução assistida.

O validador confere estrutura e consistência dos registros. Não autentica os
participantes, não comprova sozinho a execução, não consulta aprovações no
GitHub e não garante a detecção de todo dado pessoal ou segredo possível.
Os resultados e a privacidade precisam de revisão humana, e os aceites do PO e
do responsável técnico devem ser conferidos no PR antes da liberação.

As correções não alteram API, banco, migrations, frontend ou regras do domínio.
O contrato documental ainda em revisão fica mais restritivo para registros
malformados e para a exceção SMTP. Nenhuma evidência real ou credencial foi
adicionada, e o estado de preparação do piloto foi preservado.
