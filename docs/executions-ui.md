# Monitor e detalhe de execuções

As rotas `/executions` e `/executions/:executionId` implementam a jornada da
issue #59. Como a API vigente não possui listagem global, o monitor localiza uma
execução pelo identificador seguro e abre seu detalhe sem consultar arquivos ou
o banco diretamente.

## Contrato visual

O ciclo público (`active`, `completed`, `partial` ou `failed`) é apresentado em
destaque. O estado persistido permanece separado, junto da tentativa, origem e
versões do pipeline e do catálogo de regras. Assim, um término parcial não é
confundido com uma execução ainda ativa.

O detalhe reúne contagens, histórico cronológico, divergências, classificações,
pendências e evidências. Aba, página, fonte e severidade são mantidas na URL para
que a consulta possa ser compartilhada e restaurada.

## Segurança e operações

- A entrada exige `execution.read` e continua limitada ao escopo organizacional
  aplicado pelo servidor.
- Divergências e evidências somente aparecem com `artifact.read`.
- O download só é oferecido para evidência marcada como disponível e para quem
  possui `artifact.export`; rejeições e artefatos ausentes não geram link.
- O reprocessamento exige `execution.reprocess`, confirmação explícita e cria
  outra execução. O detalhe original continua visível e aponta para a tentativa
  nova.
- Todas as chamadas usam o cliente HTTP autenticado. Nenhum conteúdo do arquivo
  original é interpretado pela aplicação web.

## Estados e validação

O componente representa carregamento, vazio, parcial, erro, acesso negado,
recurso inexistente, conflito e indisponibilidade conforme o envelope estável da
API. Os testes Angular cobrem o contrato HTTP, filtros, ciclo parcial, histórico,
restrição de ações, download e criação de uma nova tentativa. A persistência e o
isolamento organizacional permanecem cobertos pela suíte de integração
PostgreSQL do acompanhamento de execuções.
