# Relatório final de validação da Etapa 3

## Resultado

A aplicação web foi validada como produto integrado sobre os contratos reais da
API e o modelo persistido no PostgreSQL. O cenário automatizado da issue #63
percorre autenticação, importação de massas sintéticas versionadas, consulta da
execução, busca de Workorder e fila/detalhe de pendências. Nenhuma etapa usa o
`data.js` do protótipo ou respostas simuladas.

## Cobertura executável

- usuário operador com escopo na organização sintética A;
- usuário de consulta restrito à organização sintética B;
- sessão persistida revogada e redirecionamento ao login;
- upload aceito, upload corrompido rejeitado e recuperação após indisponibilidade;
- consulta e pendências produzidas pelo pipeline real;
- interface em `pt-BR` e `en-US`, desktop e viewport móvel;
- navegação por teclado, nomes acessíveis e auditoria Axe sem violações sérias ou críticas;
- inspeção dos logs do navegador contra tokens, senhas e caminhos internos.

O job `Banco e dados sintéticos` cria um banco exclusivo, aplica todas as
migrations desde zero, prepara somente identidades e organizações sintéticas e
executa Playwright com FastAPI e Angular reais. O artefato `fluxo-web-e2e`
contém relatório HTML, traces, capturas e vídeos da execução.

## Limites e próximos passos

A Etapa 3 permanece operacional e somente leitura onde o backend ainda não
oferece decisão humana. Aprovação/rejeição de pendências, atribuição,
notificações externas, relatórios finais e exportações continuam registradas
como capacidades da Etapa 4; não são simuladas pela interface atual.

