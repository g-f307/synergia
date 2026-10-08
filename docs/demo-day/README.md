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

A pasta `Kickoff/` permanece ignorada pelo Git porque contém o modelo, a classe,
fontes e imagens fornecidos externamente pela organização. Esses arquivos não
devem ser copiados de fontes públicas nem adicionados ao repositório.

Para obter os ativos autorizados, solicite ao **PO ou mentor responsável pela
equipe** o pacote oficial do kickoff usado no início do desafio. Extraia o
conteúdo na pasta `Kickoff/`, na raiz do repositório. A estrutura mínima esperada
inclui `Kickoff/synergiakickoff.cls`, `Kickoff/assets/marca/` e
`Kickoff/assets/fotos/`.

Na raiz do projeto, execute:

```bash
bash docs/demo-day/build-presentation.sh
```

O script valida a presença da classe e de todos os ativos usados pelo `.tex`
antes de iniciar o LuaLaTeX. Para usar um pacote autorizado armazenado em outro
diretório, informe o caminho explicitamente:

```bash
KICKOFF_DIR=/caminho/para/Kickoff \
  bash docs/demo-day/build-presentation.sh
```

Antes do commit, renderize e inspecione visualmente o PDF gerado em
`docs/demo-day/synergia-demo-day.pdf` para confirmar legibilidade, margens e
ausência de sobreposição.
