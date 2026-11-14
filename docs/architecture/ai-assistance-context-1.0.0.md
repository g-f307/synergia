# Contexto determinístico da assistência — 1.0.0

Issue [#186](https://github.com/g-f307/synergia/issues/186), dependente da #185.
[ADR 0002](0002-ai-assistance.md).
[Schema](../contracts/execution-assistance-context-1.0.0.schema.json).
[Evidências](../evidence/issue-186-ai-assistance-context.md).

## Serviço e fronteiras

`ExecutionContextBuilder(PostgresContextReader(database_url)).build(actor, execution_id)`
é interno e recebe UUID, coerente com a #185. Não cria rota, prompt, modelo,
persistência ou interface. Funciona sem runtime de IA e com a flag desligada.
A orquestração #189 também exigirá a permissão de assistência antes de chamá-lo.

1. Sem `execution.read`, 403 antes de abrir conexão.
2. Transação `REPEATABLE READ READ ONLY`; subject filtrado por execução e escopo
   organizacional no SQL. Escopo global só quando explicitamente concedido;
   organização nula é invisível. Revalida escopo antes de consultar os detalhes.
3. Execução invisível/inexistente retorna o mesmo 404; nenhum detalhe é consultado.
4. Mapeamento idêntico ao resumo: completed/duplicate → completed;
   completed_with_errors → partial; failed/validation_failed/cancelled → failed.
   Demais estados, incluindo reprocessing, retornam 409 antes dos detalhes.
5. Contagens e cinco coleções no mesmo snapshot MVCC, combinando organização e
   execution_id no SQL. Transação fechada antes da canonicalização.
6. Projeção explícita, modelos estritos, truncamento, hash e métricas agregadas.

`ContextReader`/`ContextReadSession` separam leitura e política. O adaptador usa
as tabelas dos repositórios de consulta/monitoramento. Métodos públicos antigos
retornam prosa, atores e histórico ilimitado: o adaptador dedicado restringe a
projeção. Contagens são as mesmas de `get_execution().counts`, comparadas em teste.

## Allowlist

| Seção | Campos permitidos | Campos excluídos da origem |
| --- | --- | --- |
| subject | execution_id, organization_id, source, status, attempt, pipeline_version, rule_catalog_version, started_at, finished_at | ator, usuário, sessão, failure_reason, metadados livres |
| counts | os 15 contadores de ExecutionCounts, inteiros não negativos | linhas importadas e payloads |
| divergences | ref_id, severity, code conhecido ou null, scope, occurred_at | reason, details, coluna/aba, valores de origem |
| pending_items | ref_id, rule_id conhecido ou null, status, priority_score, created_at | reason, evidence, responsável, identificadores livres |
| classifications | ref_id, rule_id conhecido ou null, state, data_quality, priority_score, classified_at | justification, reason, evidence, responsável, entity_id |
| evidences | ref_id, safe_name sintético, evidence_type, media_type normalizado, size_bytes, sha256, available | nome original, storage_key, path, binário, conteúdo, MIME livre |
| state_history | ref_id, from_state, to_state, state_version, occurred_at | ator, usuário, reason, log bruto |

Não transporta prosa livre do banco. Códigos/regras pertencem à allowlist
versionada em `ai_assistance_context_policy.py`, enumerada no schema e validada
no Pydantic; desconhecidos ficam null. Novos códigos exigem atualização consciente.
A versão do catálogo de origem permanece explícita no subject.

NFKC substitui controles por espaços e compacta espaços. Comprimento excedido
omite o valor inteiro ou recusa campo obrigatório, sem cortar frases/negações.
Prosa de origem é excluída sem reinterpretá-la. Campos extras de um adaptador não
entram na projeção. Dados inválidos recebem 422 genérico; erro de banco, 503
genérico. Não expõe conteúdo, parâmetros SQL ou mensagem interna nas exceções/logs.

Nome seguro: `evidence-<hash opaco>.<csv|json|xlsx|bin>`. MIME vem da extensão
suportada. `available` representa elegibilidade **persistida**: inspeção aceita
na mesma execução, não descartada e storage_key presente. Não lê filesystem nem
atesta existência física futura. Download deve revalidar autorização/arquivo/hash.
Essa definição permite repetir o mesmo contexto para o mesmo estado persistido.

## Seleção e orçamento

| Coleção | Ordem SQL | Limite |
| --- | --- | --- |
| divergences | error antes de warning; created_at ASC, id ASC | 20 |
| pending_items | priority_score DESC NULLS LAST; created_at ASC, id ASC | 20 |
| classifications | classified_at ASC, classification_id ASC com collation C | 20 |
| evidences | source_files.id ASC | 20 |
| state_history | occurred_at DESC, id DESC | 10 |

Histórico são as últimas transições da execução terminal, incluindo estados
intermediários. Cada SQL busca limite + 1 para detectar excesso; sentinela não
entra no documento. São sete SELECTs fixos mais SET da transação; sem N+1.

O limite de **8192 bytes UTF-8 inclui o envelope, hash e generated_at**. Se
excedido, remove o último item da última coleção preenchida: history, evidences,
classifications, pending, divergences. Preserva a ordem de retenção da issue.
Não corta campos no meio. `truncated_sections` registra seções afetadas por limite
de quantidade ou bytes, uma vez, na ordem canônica. Contagens totais são mantidas.

Política versionada, sem modelo ou heurística variável. Suficiência exige ao
menos uma divergência/pendência/classificação retida ou evidência disponível.
Só contagens, histórico ou evidência indisponível geram `insufficient`.
Recalcula após truncar; não acrescenta fatos para completar lacunas.

## Canonicalização e referências

Datas UTC com microssegundos fixos e Z; chaves ordenadas, UTF-8 sem ASCII escaping,
separadores estáveis, sem NaN. O payload canônico exclui generated_at e o próprio
context_sha256. SHA-256 calculado após normalização/truncamento. O envelope tem
instante variável; JSON canônico e hash são iguais para o mesmo estado.
Timestamp de largura fixa impede que a geração altere o truncamento.

`ref_id = prefixo + SHA256(JSON([versão, seção, execução, ID persistido]))[:32]`.
Prefixos DIV-/PEN-/CLA-/EVI-/HIS-. Não copia IDs livres das classificações.
Referências são estáveis, específicas da execução e únicas; duplicidades são
recusadas. `context.evidence_refs()` fornece o conjunto autorizado à #185.
Consumidores devem usar `serialize_snapshot`, que revalida hash e orçamento e
detecta alteração posterior de coleções antes de enviar à próxima etapa.

## Observabilidade e consultas

Somente métricas `synergia_ai_assistance_contexts` por sufficiency,
`synergia_ai_assistance_context_bytes` e `synergia_ai_assistance_context_truncations`
por seção. Labels fechadas, sem execução, organização, arquivo, prompt ou texto.

Usa índices existentes por execução e a PK da execução; nenhuma migration nova.
O fixture de planos contém duas organizações e 1.000 itens por execução em cada
coleção de divergências/pendências/classificações, mais fonte e histórico.
EXPLAIN ANALYZE/BUFFERS/JSON cobre contagens e cinco coleções, limites e execução
única por consulta. Medições estão na evidência vinculada acima. Não estabelecem
SLA para todos os volumes; índice novo exigirá migration reversível e EXPLAIN.
