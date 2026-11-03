# Issue #148 — checkpoint 2: executor comparativo

Data: 29/10/2026. Branch: `test/148-local-models-hardware`. Bloco anterior:
`8135285`. Evidência estruturada: [checkpoint-2.json](issue-148-checkpoint-2.json).

O responsável confirmou os gabaritos com “gabarito parece ok”. A decisão está
registrada nos dois corpora e no protocolo; apenas o hash das anotações mudou,
sem regeneração de CSV/XLSX ou alteração dos rótulos. O checkpoint 1 preserva o
estado pendente que existia na data de sua entrega.

## Entregas

- CLI de congelamento, execução, retomada e comparação das duas propostas.
- Configuração fechada por schema, versões/digests/quantização fixados, hashes
  de código, prompt, schemas e datasets; identificação de hardware e pacotes.
- Bloqueio da avaliação reservada até seleção explícita congelada e gold aprovado.
- Baseline e agentes usam o mesmo corpus/split; comparação recusa amostras ou
  ambientes diferentes. Três repetições e um warmup separados nas configurações.
- Diário grava a tentativa antes da chamada; interrupção fica como falha e não
  gera retry seletivo. Falhas, timeouts e JSON inválido permanecem contabilizados.
- Timeout por chamada limitado pelo prazo restante do ciclo; thinking e
  keep_alive explícitos, sem persistir raciocínio privado do modelo.
- Telemetria de carga, geração, término/truncamento, RSS e VRAM; falta de
  telemetria fica nula com motivo. Monitor verifica orçamento de recursos e
  conserva a referência de swap entre tentativas e retomadas.
- Resumo identifica separadamente métricas estruturais e igualdade textual
  conservadora. Fidelidade semântica e decisão continuam pendentes de revisão.
- Prompts opcionais nas PoCs existentes, mantendo os padrões históricos; timeout
  operacional agora distingue `LocalRuntimeTimeout` de falha genérica de contrato.

## Validações reais

| Verificação | Resultado |
| --- | --- |
| Testes novos do executor, com runtimes falsos e sem serviços externos | 33 aprovados |
| Suíte geral sem integração | 1366 aprovados, 672 não selecionados, 15 avisos Starlette |
| `ruff check backend scripts` | Aprovado |
| AJV estrito, incluindo configuração nova | 7 schemas compilados |
| Validador de dados sintéticos | 175 arquivos válidos |
| `security_release.py validate` | Aprovado |
| Links locais novos e `git diff --check` | Aprovados |
| Smoke baseline qualidade/desenvolvimento | 24 medidas + 1 warmup, sem falhas |
| Smoke baseline operacional/desenvolvimento | 12 medidas + 1 warmup, sem falhas |
| Congelamento Qwen3 4B com metadados reais do Ollama | Aprovado, sem inferência |

Os baselines foram executados com os comandos e configurações documentados em
[ai-reevaluation-protocol.md](../ai-reevaluation-protocol.md). Evidências brutas
locais usam o prefixo `/tmp/synergia-148-block2-final-`; o resumo sanitizado está
no JSON deste checkpoint. Hardware, latências e denominadores estão registrados.
Os números dos baselines não comprovam utilidade de IA.

## Limitações e próximo checkpoint

O sandbox restringiu leitura da GPU/processos e a suíte geral ficou parada nele;
a primeira execução foi interrompida. A suíte completa, os dois smokes finais e
a consulta de metadados passaram fora do sandbox. Isso é limitação de execução
do agente, não requisito de privilégios administrativos do produto.

RSS é observado no runtime dedicado e pode incluir daemon ocioso/páginas
compartilhadas. VRAM total inclui desktop; a atribuição do modelo depende também
de `/api/ps` durante a inferência. O monitor interrompe a sequência no próximo
checkpoint/chamada; não mata Ollama nem impõe teto de memória pelo SO.

Não houve download, carregamento ou geração de modelo, avaliação reservada,
integração PostgreSQL, mudança no produto, push ou PR. Os arquivos de
`docs/files/` permanecem ignorados. Nenhuma decisão sobre a viabilidade das
propostas foi antecipada.

Próximo bloco: probes de capacidade, comparação CPU/aceleração e calibração
somente nos casos de desenvolvimento, preservando todas as tentativas. O 8B
continua condicionado à verificação híbrida, pois esta GPU dispõe de 4 GiB.
