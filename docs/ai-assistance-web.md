# Assistência no detalhe da execução

A interface operacional fica em `/executions/:executionId`, no Resumo, após os
indicadores principais e antes dos grupos de quantidades. Referência visual:
o próprio detalhe de execução, seu shell e scroll interno; tokens, `syn-badge`
e `syn-alert` compartilhados. O alerta da assistência usa `--syn-text` sobre a
superfície semântica de erro, preservando contraste nos dois temas. A rota
experimental `/ai/quality` foi retirada da aplicação operacional na #192;
#179 e #183 permanecem apenas como antecedentes experimentais offline.

## Permissões e geração

A sessão precisa de `execution.read` e de ao menos uma permissão
`ai.assistance.read`/`ai.assistance.generate`. Sem essa combinação, o componente
nem é instanciado. A capability do backend deve confirmar o recurso habilitado
e a operação permitida. O backend continua verificando a organização em cada
chamada: a descoberta global de capability não substitui autorização da execução.

| Situação | Comportamento |
| --- | --- |
| Recurso desligado ou sem permissões | Card ausente |
| Execução ativa ou lifecycle desconhecido | Explicação, sem consulta/geração |
| Somente leitura | Consulta o resultado atual, sem botão de geração |
| Geração suspensa por configuração | Mantém leitura e resultado; capability remove o botão. Se o POST retornar suspensão após o clique, consulta novamente a capability e o resultado |
| Somente geração | Não chama o endpoint de leitura; permite geração explícita |
| Sem resultado atual (GET 404) | Explicação e botão, se autorizado |
| Resultado atual | Exibe conteúdo, origem e data; não oferece regeneração |
| Geração pendente | Botão desabilitado, anúncio curto; clique duplo não envia novo POST |
| Timeout ou geração concorrente | Consulta do resultado antes de nova tentativa |
| 429 | Orientação para aguardar; consulta não executa inferência |
| 403 | Mensagem de permissão, sem repetir a operação |
| 401 | Mensagem de sessão expirada e entrada novamente; interceptor mantém o fluxo global de sessão |
| 503, rede ou erro inesperado | Falha local da assistência; resumo e abas continuam utilizáveis |

Os únicos pedidos operacionais são os do cliente de contrato `1.0.0`:
`GET /executions/{id}/ai-assistance/latest` e
`POST /executions/{id}/ai-assistance`, com `{}`. Não há geração ao abrir a tela,
entrada livre, seleção de modelo, parâmetros nem comunicação direta com o runtime.
A resposta real do POST é validada contra o OpenAPI publicado no E2E. O card
também recusa versão, identidade, estados, data ou limites de conteúdo incompatíveis
antes de apresentar o resultado.

O componente cancela descoberta de capability, leitura e geração ao ser destruído
ou receber outra execução. Cancelar o cliente não garante interromper trabalho já
iniciado no servidor; o backend mantém prazo, reservas e idempotência documentados
em [ai-assistance-api.md](ai-assistance-api.md). Voltar ao Resumo consulta o
resultado existente. Mudanças de rota e query params são acompanhadas pelo detalhe;
pedidos antigos de abas não podem sobrescrever a aba atual.

## Apresentação e referências

Conteúdo remoto é interpolado como texto Angular, inclusive achados, verificações
e limitações. Não se utiliza HTML dinâmico. Endpoint, modelo, digest, hashes e
resposta bruta não são exibidos. Textos de interface têm catálogos PT/EN; o conteúdo
persistido mantém o idioma retornado pelo backend, sem tradução que altere fatos.

| Prefixo | Aba |
| --- | --- |
| DIV | Divergências |
| PEN | Pendências |
| CLA | Classificações |
| EVI | Evidências |
| HIS | Histórico |

Os links preservam filtros e origem de navegação, fixam `page=1` e acrescentam
`reference` à URL. Divergências/evidências não ganham link quando a sessão não pode
abrir essas abas. A partir da API `0.17.0` (#227), cada item de `state_history`,
`divergences`, `classifications`, `pending-items` e `evidences` expõe seu `ref_id`
determinístico (`DIV-*`, `PEN-*`, `CLA-*`, `EVI-*`, `HIS-*`) e os endpoints
paginados aceitam o parâmetro opcional `reference` para resolver automaticamente
a página que contém o registro. A aba destaca o registro correspondente com
`data-reference-match="true"`, badge técnica e status explícito de localização
(`assistance.referenceLocated` ou `assistance.referenceNotFound`), preservando
o comportamento ao atualizar a página e no histórico do navegador.

## Validação reproduzível

1. Use um banco PostgreSQL 16 **descartável** cujo nome contenha `e2e`, com as
   migrations aplicadas até `0039` e os usuários sintéticos de
   `scripts/bootstrap_web_e2e.py`. Nunca use o banco operacional.
2. Instale dependências em `web` com `npm ci` e o FFmpeg do Playwright com
   `npx playwright install ffmpeg`. Configure Chrome via `E2E_BROWSER_CHANNEL=chrome`
   ou `E2E_BROWSER_EXECUTABLE_PATH`.
3. Exporte `DATABASE_URL` e, se necessário, `E2E_PYTHON` apontando ao Python do
   ambiente backend; execute `npm run e2e:assistance` em `web`.
4. Consulte os relatórios, imagens, vídeos e JSONs Axe em
   `web/reports/e2e-assistance-{html,results}/`.

A configuração dedicada inicia API em loopback `8001` e web em `4201`
(sobrescritas por `E2E_AI_API_PORT`/`E2E_AI_WEB_PORT`). O entry point
`scripts/serve_assistance_e2e.py` exige `SYNERGIA_ENV=test` e banco `e2e`.
Autenticação, autorização, projeção, validação, persistência, rate limit e rotas
são reais; somente o provider é controlado, sem modelo ou GPU. O cenário 503
anterior à geração é injetado no transporte do navegador. O caso de texto longo
também altera apenas a resposta no navegador. A suíte não reutiliza `ai-quality`.

Use banco novo ao repetir muitas execuções dentro de dez minutos: o limitador
real continua em vigor, inclusive no E2E. Não existe chave para desativá-lo.
A configuração comum `npm run e2e` continua validando o recurso desligado.
A CI executa ambas as suítes e publica os artefatos.

As verificações incluem Axe no card, temas claro/escuro, 390/768/1440 px, conteúdo
longo, teclado e movimento reduzido. Para zoom de 250%, um perfil temporário do
Chromium configura o zoom do navegador; o teste exige DPR 2,5, viewport efetivo
até 576 px em janela de 1440 px e CSS zoom igual a 1. O perfil é apagado ao final.
