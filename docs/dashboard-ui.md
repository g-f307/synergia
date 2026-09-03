# Dashboard operacional

`/dashboard` consome exclusivamente `GET /indicators` e exige
`dashboard.read`. A API aplica o escopo efetivo no servidor; o filtro opcional
`organization_id` somente estreita as concessões do ator e retorna `403` para
uma organização fora desse conjunto.

`date_from` e `date_to` usam a data de início persistida da execução
(`executions.started_at`). Ambos são inclusivos e a API rejeita um intervalo
invertido com `422 invalid_period`. A interface preserva os filtros como
`organization`, `dateFrom` e `dateTo` na URL e os encaminha à consulta de
execução relacionada.

As consultas relacionadas são paginadas, preservam organização, período e
página na URL e exigem, além de `dashboard.read`, a permissão própria da
entidade. O servidor aplica a interseção dos dois escopos organizacionais.

A resposta informa `generated_at`, a origem lógica `synergia.operational`, as
organizações ativas visíveis e os filtros efetivamente aplicados. Esse horário
identifica o cálculo do agregado; a interface também informa quando recebeu a
resposta. Agregados não substituem eventos e detalhes auditáveis.

Valores numéricos iguais a zero são exibidos como zero. Chaves esperadas que
não vierem na resposta aparecem como “Ausente” e tornam o resultado parcial.
Falhas `403`, indisponibilidade e resultado vazio possuem mensagens textuais
próprias, sem depender apenas de cor.

## Evidências sintéticas

As capturas usam uma resposta interceptada localmente, sem credenciais nem
dados reais: 20 execuções, 230 Workorders, 48 pendências e quantidades
persistíveis de 6.800 planejadas, 6.412 produzidas, 6.298 recebidas e 6.017
liberadas.

- [desktop, 1440 × 1000](evidence/issue-60-dashboard-desktop.png);
- [móvel, 390 × 844](evidence/issue-60-dashboard-mobile.png).
