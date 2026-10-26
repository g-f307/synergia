# Orçamento estimado de memória da ingestão excedido

## Responsável e severidade

Plataforma lidera com apoio do backend e da equipe de dados. O alerta é crítico
porque a ingestão foi estimada acima do limite configurado e deve ser rejeitada
antes de comprometer a disponibilidade do serviço.

## O que o alerta mede

O alerta compara duas grandezas do mesmo modelo de orçamento:

- `synergia_ingestion_estimated_memory_bytes`: estimativa da última ingestão,
  calculada a partir de registros e células normalizados;
- `synergia_ingestion_memory_budget_bytes`: limite aplicado à mesma ingestão.

Essas métricas não representam o RSS do processo. O alerta pode se recuperar
quando uma ingestão posterior fica dentro do orçamento ou quando um resultado
terminal anterior ao pipeline zera explicitamente o par de métricas.

## Diagnóstico

1. Confirme no painel **Ingestion estimated memory budget** se a estimativa
   excede o limite.
2. Correlacione o horário com `execution_id` e `correlation_id` nos logs.
3. Verifique se o resultado foi `rejected` com código
   `workbook_memory_limit`.
4. Confira quantidade de arquivos, linhas, células e fonte, sem inspecionar nem
   registrar conteúdo de célula.
5. Verifique se houve alteração recente dos limites por fonte.

## Ação

1. Não aumente o limite durante o incidente sem medição e aprovação.
2. Oriente a divisão do arquivo ou a remoção de linhas, colunas e abas fora do
   contrato.
3. Se o arquivo deveria caber, reproduza com massa sintética equivalente e
   compare a estimativa com a calibração em `docs/xlsx-ingestion-budget.md`.
4. Somente após nova medição, proponha ajuste versionado do orçamento.

## Recuperação e validação

Envie uma massa sintética conhecida que fique abaixo do orçamento e confirme:

- ingestão terminal sem `workbook_memory_limit`;
- estimativa menor ou igual ao orçamento no painel;
- alerta resolvido após a janela configurada;
- API, readiness e filas operacionais saudáveis.

## Rollback e escalonamento

Reverta qualquer aumento não validado do orçamento. Escale para plataforma se
o alerta persistir após uma ingestão menor; escale para backend se a estimativa
divergir da contagem normalizada. Não reinicie o serviço apenas para limpar a
métrica e não registre arquivo, nome original, caminho ou conteúdo do cliente.
