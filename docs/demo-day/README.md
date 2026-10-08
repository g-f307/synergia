# Pitch de integração com IA — issue #127

Esta pasta reúne os artefatos versionáveis do pitch de duas propostas de
integração com IA no SYNERGIA. Os experimentos anteriores permanecem como
aprendizado técnico, mas seus resultados não fazem parte da apresentação.
Dados de KPI, FTE ou ganho não confirmados aparecem como pendentes.

## Artefatos

- `synergia-demo-day.pdf`: apresentação reduzida, baseada no modelo do kickoff;
- `demo-day-synergia.tex`: fonte da apresentação;
- `roteiro-apresentacao.md`: fala cronometrada para um único apresentador;
- `fichas-propostas.md`: escopo, integração, limites e critérios das propostas;
- `revisao-entrega.md`: conferência de conteúdo, governança e decisões esperadas.

## Estado da entrega

- apresentação reposicionada como pitch de integração futura;
- duas propostas descritas com arquitetura, limites e critérios de avaliação;
- prioridade, usuários da validação, hardware e metas dependem de decisão com o
  cliente e não são declarados como aprovados neste repositório.

## Reprodução do PDF

A pasta `Kickoff/` permanece ignorada pelo Git e contém o modelo, a classe e os
ativos fornecidos pela organização. Na raiz do projeto:

```bash
cd Kickoff
lualatex -interaction=nonstopmode -halt-on-error \
  ../docs/demo-day/demo-day-synergia.tex
lualatex -interaction=nonstopmode -halt-on-error \
  ../docs/demo-day/demo-day-synergia.tex
```

O PDF gerado deve ser comparado visualmente com
`docs/demo-day/synergia-demo-day.pdf` antes de substituir o artefato entregue.
