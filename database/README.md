# Modelo persistente

O PostgreSQL é a fonte persistente do sistema. A planilha `WO Status.xlsx` é
somente uma fonte de importação e homologação; cada registro operacional aponta
para a execução e o arquivo que o originaram.

## Migrations

Os arquivos de `database/migrations/` são executados em ordem lexicográfica.
Partindo de um banco vazio:

```bash
export PGHOST=localhost PGPORT=5432 PGDATABASE=synergia
export PGUSER=synergia PGPASSWORD=synergia-local-only
python scripts/validate_project_assets.py
```

## Entidades e decisões

- `executions` registra tentativa, estado e vínculo de reprocessamento;
- `source_files` mantém metadados e SHA-256, com proteção contra duplicidade;
- `workorders`, `lots` e `serials` preservam identificadores como texto;
- `container_number` também é texto para preservar zeros à esquerda;
- todas as entidades operacionais apontam para `execution_id` e
  `source_file_id`;
- `pending_items` representa impedimentos anteriores à liberação;
- `holds` representa retenções pós-liberação e aceita razão ausente;
- `oqc_decisions` registra o estado da decisão sem automatizá-la;
- `classifications` preserva regra, versão, prioridade, justificativa e evidência;
- `rule_evaluations` registra também as regras que não foram acionadas;
- `consolidated_field_provenance` liga cada campo consolidado às linhas de origem;
- `audit_events` registra eventos e contexto adicional em `jsonb`;
- quantidades continuam `NULL` quando ausentes na origem; quando informadas, são
  não negativas e a liberação parcial exige quantidade liberada maior que zero
  e menor que a recebida.

Cada Workorder consolidada é uma unidade transacional independente. Uma falha
reverte lote, serial, classificação, pendência e proveniência daquela unidade,
registra `processing_persistence_failed` e não impede a confirmação das demais
Workorders da execução. Chaves estrangeiras compostas com `execution_id`
impedem relacionamentos entre execuções diferentes.

O arquivo original aceito é preservado em diretório controlado. O banco mantém
nome, extensão, tipo, tamanho, SHA-256 e somente a chave relativa de
armazenamento. A execução registra fonte, ator, início, fim, estado, motivo de
falha e eventual execução original em caso de duplicidade.

## Diagrama entidade-relacionamento

```mermaid
erDiagram
    executions ||--o{ executions : reprocessa
    executions ||--o{ source_files : importa
    source_files ||--o{ organizations : origina
    source_files ||--o{ workorders : origina
    organizations ||--o{ workorders : possui
    workorders ||--o{ lots : agrupa
    workorders ||--o{ serials : possui
    lots ||--o{ serials : identifica
    workorders ||--o{ pending_items : apresenta
    workorders ||--o{ holds : recebe
    workorders ||--o{ oqc_decisions : avalia
    workorders ||--o{ classifications : classifica
    workorders ||--o{ rule_evaluations : avalia_regra
    workorders ||--o{ consolidated_field_provenance : rastreia
    executions ||--o{ audit_events : registra
```

## Teste de persistência

Os testes de integração aplicam todas as migrations em PostgreSQL 16 e cobrem
persistência completa, continuidade parcial, rollback da unidade afetada,
integridade entre execuções, reinício do repositório e presença dos índices das
consultas críticas. A massa de referência está em
`data/synthetic/database_example.json`.
