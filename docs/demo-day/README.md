# Demo Day de IA — entrega da issue #127

Esta pasta reúne os artefatos versionáveis da apresentação e dos dois vídeos das
PoCs locais do SYNERGIA. O conteúdo usa somente resultados medidos nos PRs #130
e #131. Dados de KPI, FTE ou ganho não confirmados aparecem como pendentes.

## Artefatos

- `synergia-demo-day.pdf`: apresentação reduzida, baseada no modelo do kickoff;
- `demo-day-synergia.tex`: fonte da apresentação;
- `roteiro-apresentacao.md`: fala cronometrada para um único apresentador;
- `roteiro-videos.md`: roteiro obrigatório e checklist para cada PoC;
- `revisao-entrega.md`: conferência de privacidade, legibilidade e links.

## Estado da entrega

- apresentação técnica preparada com os resultados disponíveis em 06/10/2026;
- duas PoCs implementadas e avaliadas com dados sintéticos;
- gravação, hospedagem e confirmação de acesso aos vídeos dependem de ação
  externa e não são declaradas como concluídas neste repositório.

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

