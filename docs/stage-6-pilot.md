# Homologação assistida e decisão do piloto (Etapa 6)

A issue #146 fecha a Etapa 6 com uma decisão explícita: **liberar**, **liberar
com limitações** ou **bloquear** o piloto. Este documento define o roteiro, o
que já foi ensaiado com dados sintéticos e o que só os stakeholders podem
concluir. O estado vigente fica em
[`stage-6-pilot-decision.json`](stage-6-pilot-decision.json) e é verificado por
`scripts/validate_stage6_pilot.py`.

## Estado atual

A decisão é **`not_decided`**. Os ensaios sintéticos existem e estão ligados a
cada cenário, mas **nenhum cenário foi executado com os stakeholders**, as
seis pré-condições estão pendentes e os aceites do PO e do responsável técnico
estão `pending`. Ensaio sintético não substitui a execução assistida e não
autoriza o piloto nem a produção. Os portões corporativos da Etapa 5 e as
decisões ID-P01 a ID-P07 de identidade seguem abertos.

## Pré-condições

Cada item tem um responsável e começa `pending`. Nada é inventado: datas,
usuários, organizações e arquivos são definidos pelos responsáveis e
registrados aqui sem dados reais nem credenciais.

| ID | Pré-condição | Responsável |
| --- | --- | --- |
| PC-01 | Janela, ambiente e responsável pela operação | PO e plataforma |
| PC-02 | Usuários, papéis e organizações autorizados | identidade |
| PC-03 | Arquivos autorizados, fora do Git | PO |
| PC-04 | Identidade autorizada e fim do login local registrado | identidade |
| PC-05 | Destino de logs, métricas e alertas confirmado | plataforma |
| PC-06 | SMTP incluído ou excluído do roteiro | PO |

## Roteiro da jornada

Para cada cenário o ensaio sintético já tem evidência reproduzível. A coluna
de execução assistida só passa a `passed` quando os stakeholders concluírem o
passo e houver registro versionado sem dados reais.

| ID | Cenário | Obrigatório | Ensaio sintético |
| --- | --- | --- | --- |
| S-01 | Login → upload → execução → consulta → pendência → relatório | sim | E2E `operational-flow.spec.ts` |
| S-02 | Expiração de sessão volta ao login público sem contexto residual | sim | E2E e `test_auth.py` |
| S-03 | Arquivo válido | sim | corpus `ingestion-v1` |
| S-04 | Arquivo parcialmente válido | sim | corpus (`wo-drift`, `td-edge`) |
| S-05 | Registros duplicados | sim | corpus (`td-mixed`, `wo-composite`) |
| S-06 | Arquivo corrompido ou inválido não derruba a aplicação | sim | `test_imports.py` e E2E |
| S-07 | Arquivo acima do orçamento rejeitado de forma estruturada | sim | `test_ingestion_budget.py`, `test_ingestion_volume.py` |
| S-08 | Falha de uma organização não bloqueia nem expõe outra | sim | E2E e `test_authorization_persistence.py` |
| S-09 | Reconciliação, proveniência e reprocessamento | sim | corpus e `test_execution.py` |
| S-10 | Diagnóstico por logs, métricas e alertas sem conteúdo sensível | sim | contrato de observabilidade |
| S-11 | Backup, restauração e rollback | sim | runbook e relatório de recuperação |
| S-12 | Notificação por e-mail | **não**, só se aprovada | evidência SMTP da #143 |

## Critérios de aceite da issue

| Critério | Situação | Base |
| --- | --- | --- |
| Nenhum defeito crítico ou alto sem tratamento acordado | pendente | registro de defeitos da execução assistida |
| Arquivo inválido não derruba a aplicação nem bloqueia outras organizações | ensaiado | S-06, S-08 |
| Resultados reconciliáveis com a entrada autorizada | ensaiado (sintético) | S-03, S-09 |
| Sessão expirada volta ao login público | ensaiado | S-02 |
| Falha diagnosticável sem consultar conteúdo sensível | ensaiado | S-10 |
| Rollback e recuperação exercitados | ensaiado (sintético) | S-11 |
| Stakeholders concluem o roteiro e registram aceite ou pendências | pendente | aceites no PR |
| CI, containers, E2E e segurança aprovados | gate de CI | pipeline |
| Decisão e limitações publicadas sem dados reais | pendente | este registro |

"Ensaiado" significa evidência sintética reproduzível, não a execução com
dados reais.

## Regras do validador

`scripts/validate_stage6_pilot.py` recusa, em modo fail-closed:

- **`release` ou `release_with_limitations`** sem os dois aceites aprovados,
  sem todas as pré-condições `ready`, sem todos os cenários obrigatórios
  `passed` com evidência, ou com defeito crítico ou alto em aberto;
- **`release`** com limitações registradas, e **`release_with_limitations`**
  sem nenhuma;
- limitação sem responsável e prazo, defeito tratado sem responsável;
- qualquer decisão sem motivo registrado;
- evidência inexistente, com caminho absoluto ou fora do repositório;
- campos com forma de credencial (`password`, `token`, `secret`, `email`,
  `authorization`).

`block` exige apenas o motivo: bloquear nunca depende de aceite.

## Como registrar a execução assistida

1. Preencher as pré-condições conforme os responsáveis as concluírem
   (`pending` → `ready`).
2. Executar cada cenário com os stakeholders e registrar a evidência
   sanitizada em `docs/evidence/` (estados, contagens e códigos; nunca
   conteúdo de célula, nome original, caminho interno ou credencial).
3. Marcar o cenário como `passed` ou `failed`, apontando para a evidência.
4. Registrar defeitos com severidade e limitações com responsável e prazo.
5. Registrar a decisão e o motivo, e os aceites do PO e do responsável
   técnico no PR.
6. Rodar `python scripts/validate_stage6_pilot.py`.

A janela de uso segue o
[checklist de suporte](runbooks/pilot-support-window.md).

## Fora do escopo

Implantação irreversível em produção, aceite sem execução dos stakeholders,
correção de todas as pendências encontradas dentro desta issue e Modo TV ou IA
como requisito de saída.
