# Publicação das evidências de desempenho da issue 95

## Resultado

As evidências necessárias para revisar volume, ruptura e planos PostgreSQL
foram sanitizadas e versionadas em `evidence/performance/issue-95/`. O conjunto
contém 188 arquivos, totaliza 1.915.509 bytes e não depende do diretório
`artifacts/`, que permanece ignorado por conter as saídas originais locais.

| Categoria | Arquivos | Conteúdo |
| --- | ---: | --- |
| `reference_run` | 8 | ambiente, workload, resumo, 39/39 oráculos, relatório, amostras e recursos da V05 |
| `rupture_run` | 22 | limites, resultados por degrau, métricas de cgroup e rodadas completas V00 dos dois envelopes |
| `postgres_plan_before` | 76 | `run.json`, SQL e planos JSON anteriores à migration 0027 |
| `postgres_plan_after` | 76 | `run.json`, SQL e planos JSON posteriores à migration 0027 |
| `migration_comparison` | 2 | sondas equivalentes antes/depois do índice |
| `manifest` | 4 | manifestos V00, V01, V02 e V05 efetivamente usados |

O inventário `evidence/performance/issue-95/index.json` associa categoria,
origem, caminho publicado, tamanho e SHA-256 de cada arquivo. O arquivo
`evidence/performance/issue-95/SHA256SUMS` também cobre o próprio índice. O
campo `scope` distingue o material incluído das saídas deliberadamente omitidas.

## Verificação

Em um clone limpo:

```bash
cd evidence/performance/issue-95
sha256sum -c SHA256SUMS
```

O publicador é determinístico e pode reconstruir o diretório a partir das
fontes locais declaradas:

```bash
backend/.venv/bin/python scripts/publish_performance_evidence.py \
  --spec evidence/performance/issue-95-publication.json
```

Para evitar sobrescrita acidental, o destino deve estar ausente ou vazio antes
da reconstrução.

## Sanitização

O publicador substitui caminhos absolutos do workspace e do diretório pessoal,
redige chaves sensíveis em JSON e rejeita padrões de senha, tokens Bearer e
URLs PostgreSQL com credenciais. A varredura do conjunto publicado passou sem
ocorrências. Dados funcionais sintéticos, identificadores de execução e hashes
foram preservados porque são necessários para reconciliar os resultados.

Os nomes antigos da migration encontrados nas saídas históricas não alteram o
conteúdo medido: a migration atualmente versionada é
`0027_index_rule_evaluations_workorder.sql`, conforme declarado no índice.
