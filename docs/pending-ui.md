# Fila e detalhe de pendências

As rotas `/pending-items` e `/pending-items/:pendingId` são consultas somente
leitura protegidas por `pending.read`. A API aplica o escopo organizacional do
token tanto na lista quanto no detalhe; um identificador pertencente a outra
organização responde como inexistente.

## Comportamento operacional

- A fila inicia em `status=open` e mantém filtros, ordenação e página na URL.
- Os filtros aceitos são estado, categoria, prioridade, área responsável,
  Workorder, lote, serial e execução.
- A ordenação é determinística e oferece atualização, prioridade e
  identificador, sempre com o identificador como desempate.
- O detalhe apresenta código e versão da regra, motivo, prioridade, área,
  vínculos operacionais e evidência liberada para consulta.
- Caminhos de armazenamento, identificadores internos de arquivo, segredos e
  tokens são removidos recursivamente da evidência antes da resposta HTTP.
- Registros incompletos e respostas geradas há mais de 24 horas são sinalizados;
  ausência de evidência é um estado válido e explícito.

As categorias visuais não alteram a decisão persistida. Elas apenas distinguem
pendência anterior à liberação, hold posterior à liberação, falha técnica,
liberação parcial e demais ocorrências operacionais. `partial_release` nunca é
apresentada como liberação integral.

## Cenário sintético e regressão

`data/synthetic/pending-ui-scenarios.json` contém casos determinísticos para as
quatro distinções críticas da interface. Os testes de componente exercitam a
fila vazia e preenchida, filtros e paginação na URL, estados parciais e antigos,
navegação, evidência presente/ausente e escaping de conteúdo ativo. Os testes
HTTP e PostgreSQL cobrem os mesmos filtros e o isolamento organizacional.
