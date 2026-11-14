# Evidências técnicas — issue 188

Os testes usam PostgreSQL 16 descartável e fixtures sintéticos. A migration `0038`
foi aplicada após `0001`–`0037` em banco limpo; o teste de rollback remove a tabela
e restaura a view anterior dentro de uma transação revertida. Os testes cobrem
reserva concorrente (um único vencedor), substituição de reserva abandonada,
finalização por token antigo recusada, transação revertida, reuso, leitura por
organização e contexto, registro inválido auditado, limpeza em lote, dry-run,
reexecução, projeção para fila e conversão GELF sem conteúdo de resultado.

O fixture de 3.000 reservas executa `ANALYZE` e `EXPLAIN` das consultas reais de
leitura e chave idempotente. Ambas usaram `Index Scan using ai_assistance_idempotency`
e `Index Only Scan using executions_id_organization_key`; a leitura ordenada usou
`Sort` sobre o resultado seletivo. As consultas são executadas no teste
`test_index_plans_with_representative_fixture`, que imprime os planos sem valores
reais de negócio. O índice `ai_assistance_latest` também fornece a ordenação por
organização/execução; o plano selecionado depende da distribuição de dados.

O teste `test_audit_projection_is_sanitized_and_exportable` compara os metadados da
view com a projeção na fila e converte um evento ao formato GELF. Isso comprova a
integração interna e a serialização, não uma entrega a servidor Graylog externo.
