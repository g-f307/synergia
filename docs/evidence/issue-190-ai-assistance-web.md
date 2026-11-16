# Issue #190 — assistência no resumo da execução

## Escopo e ambiente

Validação em 15/11/2026, sobre `main` base `ab0f431`, com Node 22.18,
Python 3.12, Chrome Headless 156, Angular 20 e PostgreSQL 16 descartável.
Dados, usuários e organizações sintéticos. Nenhum runtime de modelo foi iniciado,
nenhum peso foi baixado e não houve inferência em GPU.

Referência visual: detalhe de execução existente, mantendo shell, moldura,
scroll interno, abas e indicadores. Guia e reprodução:
[ai-assistance-web.md](../ai-assistance-web.md).

## Critérios e evidências

| Critério da issue | Implementação e prova |
| --- | --- |
| Assistência no resumo | Componente entre `.summary-highlights` e `.summary-groups`; posição conferida no E2E |
| Sem geração automática ou texto livre | GET ao abrir, POST `{}` apenas no botão; E2E acompanha pedidos e impede clique duplo |
| Permissões e elegibilidade | Sessão + capability; lifecycle terminal; testes de leitura/geração independentes e recurso desligado |
| Referências nas abas corretas | Cinco prefixos cobertos por testes Angular; DIV exercitado por teclado no navegador, preservando filtros, origem e página coerente |
| Estados e ações | Carregando, vazio, ativo, gerando, pronto, insuficiente, rejeitado, indisponível, 401/403/409/429/503/504 e inesperado cobertos por testes |
| Falha isolada | E2E 503 mantém resumo e permite abrir Histórico; pedidos obsoletos cancelados ao trocar rota/aba ou destruir componente |
| Conteúdo somente como texto | Teste com markup malicioso confirma texto literal e ausência de elementos injetados; metadados de runtime não renderizados |
| Layout, contraste e acesso | Axe sem violações no card; temas claro/escuro, 390/768/1440 px, conteúdo longo, teclado, movimento reduzido e zoom real 250% |

As referências são opacas no contrato atual. A interface abre a aba e comunica
qual referência localizar, sem simular uma correspondência com o ID nativo nem
um destaque que não existe. Abas de artefatos exigem a permissão correspondente.

## Resultados locais

| Comando/validação | Resultado |
| --- | --- |
| `npm test -- --watch=false --browsers=ChromeHeadless` | 412 testes Angular aprovados |
| `npm run e2e` | 24 testes da jornada existente aprovados |
| `npm run e2e:assistance` | 7 testes aprovados com API e PostgreSQL reais e provider controlado |
| Axe no card | 27 auditorias sem violações; relatório resumido e hashes dos JSONs originais abaixo |
| `pytest -q backend/tests/test_web_i18n.py backend/tests/test_ai_assistance_contract.py backend/tests/test_ai_assistance_routes.py` | 82 testes aprovados |
| `npm run lint` | Aprovado |
| `npm run build` | Aprovado; avisos de orçamento CSS em componentes preexistentes |
| `ruff check . ../scripts` no backend | Aprovado |
| `python scripts/validate_visual_system.py` | Aprovado |
| `python scripts/validate_i18n.py` | 1048 chaves PT/EN, sem ausências ou órfãs |
| `git diff --check` | Aprovado |

O alerta compartilhado apresentava contraste insuficiente no tema escuro quando
usado nesta entrega. O card passou a usar `--syn-text` no alerta sobre a superfície
semântica de erro. A regra é limitada a `syn-execution-assistance`; não declara
resolvidas as demais correções de contraste da #199.

## Registros sanitizados

- [Relatório Axe e índice das auditorias](issue-190-assistance-web/axe-summary.json).
- [Pronto — desktop claro](issue-190-assistance-web/ready-light-1440.png).
- [Pronto — mobile escuro](issue-190-assistance-web/ready-dark-390.png).
- [Insuficiente — mobile claro](issue-190-assistance-web/insufficient-light-390.png).
- [Indisponível — mobile escuro](issue-190-assistance-web/unavailable-dark-390.png).
- [Zoom real 250% — tema escuro](issue-190-assistance-web/zoom-250-dark.png).
- [Destino da referência](issue-190-assistance-web/reference-navigation.png).
- [Vídeo curto da navegação por teclado](issue-190-assistance-web/reference-navigation.webm).

As demais capturas e os JSONs completos do Axe ficam nos artefatos
`web/reports/e2e-assistance-{results,html}/`, publicados pela CI. Os arquivos
versionados contêm apenas a interface com dados sintéticos; não contêm token,
cookie, prompt ou resposta bruta do provider.

O zoom não é simulado por CSS: um perfil temporário do navegador usa zoom 250%;
o teste exige `devicePixelRatio=2.5`, largura efetiva até 576 px para janela de
1440 px e `getComputedStyle(document.documentElement).zoom === '1'`.

## Limites da validação

O provider controlado substitui somente a inferência. Sessão, autorização,
contexto, validação, persistência, rate limit e rotas usam implementação real.
Pronto, insuficiente e fallback após rejeição são respostas reais dessas rotas.
A indisponibilidade anterior à geração e o conteúdo longo são injetados no
transporte do navegador e identificados como tal nos testes. O Axe abrange o card;
a regressão da jornada existente continua cobrindo as demais telas.

Não houve teste de qualidade do modelo real ou implantação operacional: esses
resultados não são requisitos da interface #190. Não há novo endpoint, migration,
concessão de permissão nem uso da tela experimental `ai-quality` nesta entrega.
