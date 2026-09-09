# Jornada web de relatórios

As rotas `/reports` e `/reports/:reportId` implementam o catálogo e a leitura
dos snapshots persistidos pela API. A aplicação web nunca recalcula dados nem
produz o conteúdo de uma exportação.

## Catálogo e geração

O catálogo consulta a versão mais recente de cada relatório. Organização,
tipo, estado, execução, ordenação, página e tamanho da página permanecem na URL.
O formulário de geração utiliza exclusivamente opções de `/reports/policy` e
exige uma organização explícita, inclusive para concessões globais.

`report.read` protege a jornada. Os controles adicionais são independentes:

- `report.generate`: formulário de geração;
- `report.export`: download de versão concluída;
- `report.cancel`: cancelamento de versão ainda em geração.

Ocultar um controle não substitui a autorização aplicada pelo backend.

## Visualização

O detalhe identifica UUID, versão, schema, execução, organização, responsável,
horário de referência e filtros. A aba de dados adapta as colunas ao tipo
`workorder_consolidated` ou `oqc_summary`; `null` aparece como indisponível e
zero permanece zero.

Versão, aba, páginas e URL de retorno são preservadas. Links para Workorder,
lote e pendência levam contexto de execução e Workorder quando necessário para
impedir resolução ambígua entre organizações. Snapshots antigos sem
`pending_item_id` continuam visíveis, apenas sem o link correspondente.

## Estados e segurança

Carregamento, vazio, parcial, geração obsoleta, falha, cancelamento, proibição,
ausência e indisponibilidade possuem apresentações distintas. Uma falha no
histórico não apaga um snapshot já obtido. Erros operacionais exibem apenas a
mensagem localizada e o correlation ID seguro.

CSV e JSON são baixados como `Blob` recebido do backend. A interface respeita o
nome controlado pelo `Content-Disposition`; nenhum dado do protótipo ou valor
fornecido pelo usuário é usado para fabricar relatórios no navegador.

As telas usam os catálogos `pt-BR` e `en-US`, navegação por teclado, tabs
semânticas, região rolável para tabelas e restauração de foco dos modais.
