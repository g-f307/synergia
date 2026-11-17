# Dashboard operacional

`/dashboard` consome exclusivamente `GET /indicators` e exige
`dashboard.read`. A API aplica o escopo efetivo no servidor; o filtro opcional
`organization_id` somente estreita as concessões do ator e retorna `403` para
uma organização fora desse conjunto.

O painel e o catálogo compartilham os filtros de organização, fonte, formato,
situação, estado técnico, ciclo legado, identificador e período de início
(`executions.started_at`). Os dias escolhidos na interface são convertidos no
fuso do perfil para instantes UTC inclusivos; o fim do dia preserva microssegundos.
A URL usa `organization_id`, `source`, `file_type`, `outcome`, `status`,
`lifecycle`, `execution_id`, `date_from` e `date_to`. Links antigos com
`organization`, `dateFrom` e `dateTo` continuam aceitos e são normalizados.

A API `0.15.0` acrescenta `execution_summary`, com situações canônicas e o escopo
efetivo de `dashboard.read`. A interface usa esse agregado para o total, as
concluídas e as sete categorias do gráfico, sem somar o mapa técnico legado.
Fonte, formato e situação possuem controles próprios; filtros recebidos por link
são preservados. A API recebe o período em `started_from`/`started_to`.
O mapa `executions` e os parâmetros de data antigos continuam compatíveis.
Consultar o [contrato e a compatibilidade temporal](execution-monitoring.md#compatibilidade-dos-indicadores).

As consultas relacionadas são paginadas, preservam organização, período e
demais filtros e página na URL e exigem, além de `dashboard.read`, a permissão própria da
entidade. O servidor aplica a interseção dos dois escopos organizacionais.

A resposta informa `generated_at`, a origem lógica `synergia.operational`, as
organizações ativas visíveis e os filtros efetivamente aplicados. Esse horário
identifica o cálculo do agregado; a interface também informa quando recebeu a
resposta. A interface identifica a permissão, as organizações e os filtros
aplicados ao conjunto apresentado. Links para catálogo, consultas relacionadas
e Modo TV preservam o recorte. Cada tela respeita sua própria permissão;
comparações só são equivalentes quando escopos e filtros coincidem.
Agregados não substituem eventos e detalhes auditáveis.

Atualizações mantêm o conjunto anterior até a nova resposta completa chegar.
Em falha, os dados e o recorte anteriores permanecem identificados como
desatualizados; perda de autorização remove os dados exibidos. URLs com período
inválido não disparam consultas sem esse filtro.

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

A reconciliação canônica e as evidências atualizadas de 390/768/1440 px, temas
e zoom estão no [relatório da #193](execution-reconciliation-validation.md).
