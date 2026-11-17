# Persistência interna da assistência por execução

A migration `0038` cria `ai_assistances` e o histórico imutável
`ai_assistance_events`. Cada resultado pertence à organização e à execução;
consultas da aplicação devem verificar a permissão e reconstruir o conjunto de
referências autorizadas antes de chamar o repositório. Não há rota nesta entrega.

A migration incremental `0040` acrescenta os registros de execução dos workers
na auditoria existente de operações de dados. O [contrato de observabilidade](ai-assistance-observability.md)
descreve contagens, sucesso atômico, falhas, heartbeat e rollback que preserva o
histórico. Para executar os CLIs atualizados, aplicar essa migration previamente.
O repositório valida novamente o contrato e as referências em leitura, e registra
falha de integridade sem devolver o resultado inválido.
Na finalização, `elapsed_ms` deve coincidir com `provenance.timings.total_ms`;
a mesma consistência é verificada novamente na leitura. Cada ator de evento é
validado em `identity_users` na transação que registra o evento; uma identidade
inexistente interrompe a operação sem persistir alterações ou projeções.

```text
execução + organização ── reserva (processing) ── conclusão
                              │                  ├─ ready (model)
                              │                  ├─ insufficient_evidence (deterministic)
                              │                  └─ rejected (deterministic)
                              └─ expiração/retenção ── remoção
                                        └─ evento imutável → auditoria → fila Graylog
```

A chave única inclui organização, execução, hashes de contexto/prompt, digest e
versão; valores nulos de digest são comparados como iguais. Reserva e finalização
são transações distintas: nunca mantenha uma conexão aberta para inferência. Uma
reserva abandonada expira após dois minutos e pode ser substituída; o UUID antigo
não pode finalizar a nova reserva. A orquestração da #189 chama `find` antes
de reservar e resolve conflitos de reserva sem nova inferência.

A política padrão é 30 dias, com faixa de 1 a 365; quando habilitada em
homologação ou produção a variável `SYNERGIA_AI_ASSISTANCE_RETENTION_DAYS` é
obrigatória. Um agendador externo executa o worker finito com a mesma política
operacional dos demais workers: uma invocação processa no máximo um lote, sem
laço permanente. A identidade técnica informada deve existir em `identity_users`.

```bash
read -r -p 'UUID da identidade técnica existente: ' AI_ASSISTANCE_ACTOR_ID
export AI_ASSISTANCE_ACTOR_ID
PYTHONPATH=backend backend/.venv/bin/python scripts/expire_ai_assistance.py \
  --actor-id "$AI_ASSISTANCE_ACTOR_ID" --batch-size 100 --dry-run
```

Conferir quantidade e intervalo da prévia antes do lote efetivo, que exclui os
elegíveis e não usa `--apply`:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/expire_ai_assistance.py \
  --actor-id "$AI_ASSISTANCE_ACTOR_ID" --batch-size 100
```

Ambos os modos mostram somente quantidade e intervalo de expiração. A seleção
usa `FOR UPDATE SKIP LOCKED`; várias invocações podem ser
repetidas até esgotar os vencidos. Os eventos persistem sob a retenção de auditoria.
Não inclua credenciais em argumentos, comandos de evidência ou saída. Configure
`DATABASE_URL` pelo mecanismo seguro do ambiente.

A tabela guarda somente resultado validado e metadados de proveniência; prompt,
contexto completo e resposta bruta não são gravados. Os eventos registram apenas
identificadores, tempos, estados, modelo, hashes e códigos; o trigger grava uma
projeção no mecanismo de fila do Graylog na mesma transação. O envio à infraestrutura
externa depende da configuração e operação do worker existente.

Para suspender a operação, desligar somente a geração conforme o
[runbook](runbooks/ai-assistance.md), preservando leitura e dados. Não executar
rollback SQL para esse fim. A reversão histórica de 0038 é destrutiva (remove
resultados/eventos) e exige backup e decisão operacional explícita; não é o
procedimento de contingência da #191. O rollback 0040 preserva o histórico e a
aceitação dos datasets, removendo os guardas novos; ver
[atualização e rollback](deployment/update-and-rollback.md#assistência-de-ia-suspensão-e-rollback).
