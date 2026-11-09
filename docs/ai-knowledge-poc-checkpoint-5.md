# Checkpoint do bloco 5 — campanha reservada da PoC #183

09/11/2026, America/Manaus. Bloco 5 autorizado separadamente após o
[checkpoint 3–4](ai-knowledge-poc-checkpoint-3-4.md). **Bloco 5 concluído.**
O bloco 6, sua auditoria final e a recomendação da issue não estão autorizados.

## Protocolo executado

A [autorização do bloco 5](ai-knowledge-poc-block5.json) referencia o hash do
[congelamento](ai-knowledge-poc-final-config.json). O registro congelado permanece
inalterado, inclusive suas declarações históricas de execução ainda não autorizada.
A autorização nova habilita somente o bloco 5.

São 48 instâncias/24 grupos com variantes correlacionadas, nos dois modelos e nas
seeds 125, 126 e 127. Não há seleção da melhor seed. Ordem de casos e alternância de
modelos vêm da [matriz congelada](evidence/issue-183-final-matrix.json).

O recuperador selecionou dois candidatos em 35 casos, um em três casos e nenhum
em dez: 73 chamadas por combinação de modelo/seed, **438 chamadas classificadoras**,
abaixo do teto de 576. Todos os 48 casos continuam na avaliação, incluindo os dez
sem chamada. Foram calculados 56 textos novos de embeddings, reutilizando o cache
anterior por hash; não se repetem embeddings por seed.

Os componentes científicos dos blocos anteriores não foram editados: base,
corpus/gabaritos, projeção factual, busca, prompts, schemas, guardas, parâmetros,
políticas, rubrica e template condicional de redação. Cada pedido classificatório
precisa corresponder ao seu hash na matriz prévia. O executor só lê entradas;
o avaliador abre rótulos depois da conclusão de todos os pedidos.

Lotes têm até 32 chamadas e usam um só modelo. O ledger original mantém quotas,
contagem prévia de tentativas, tempo ativo e recursos. Respostas inválidas não
recebem reparo ou retry; transporte incerto bloqueia retomada para reconciliação.

## Comparadores e interpretação das métricas

| Braço | Conteúdo e função na comparação |
| --- | --- |
| B0 | Mesmos fatos e mensagem genérica, sem selecionar ficha ou verificação específica |
| B1 | BM25 focado, mesmos filtros objetivos, classificação lexical e verificação literal |
| B2 | Busca densa com documentos literais; candidatos não são confirmações de aplicabilidade |
| Controle lexical pareado | Mesmos candidatos densos recebidos pelo LLM, com classificação lexical |
| 4B/8B | Recuperação selecionada, uma ficha/chamada, interpretação, guardas e política congeladas |

Em cada item exibido, acerto exige estado, referências decisivas e lacunas corretos. Cobertura aceita ao menos uma ficha correta nos casos respondíveis;
completude exige o conjunto inteiro e nenhuma ficha extra. Próxima verificação
exige pelo menos uma correta e nenhuma orientação indevida na mesma ocorrência.
O texto/ID da verificação é anexado por código, não escolhido autonomamente pelo LLM.

Os contadores pooled somam numeradores/denominadores das três seeds; não fazem
média simples de precisões com quantidades de saídas diferentes. Slots caso/seed
não são casos independentes. Resultados por seed permanecem disponíveis.

Erros altos estruturados são sustentações contra referência não sustentada;
respostas inválidas, estados errados ou lacunas incorretas também reduzem os
resultados. Essa rubrica não demonstra que toda falha semântica seria contida.

## Resultados

As **438 chamadas terminaram**, todas com JSON estruturalmente válido e término
`stop`. Isso não significa correção semântica. As três seeds foram preservadas.

### Recuperação

32 dos 48 casos possuem ficha pertinente. O teto de duas fichas no reservado é
100% e os três braços focados atingiram Recall@2 de 100%. No desenho inicial,
BM25/denso/híbrido tiveram 53,13% / 35,94% / 60,94%, respectivamente.

| Recuperação focada | Recall@1 | Recall@2 | MRR |
| --- | ---: | ---: | ---: |
| BM25 | 87,50% | 100% | 0,9844 |
| Densa selecionada | 87,50% | 100% | 0,9844 |
| Híbrida | 90,63% | 100% | 1,0000 |

No subconjunto semântico, Recall@2 também foi 100% nos três. O híbrido ordenou o
primeiro resultado melhor em uma ocorrência respondível, mas não foi selecionado
após ver o teste. **Não houve ganho exclusivo da busca densa em Recall@2**. Os filtros
objetivos comuns explicam parte importante do salto; não atribuir esse controle ao LLM.
Seis dos 16 casos sem ficha ainda receberam candidatos, não orientações validadas.

### Orientações apresentadas

Baseline determinístico avaliado uma vez em 48 casos; modelos agregados em
144 slots caso/seed por modelo. Os percentuais são comparáveis; as contagens
brutas de três repetições não são comparadas como se fossem amostras independentes.

| Braço | Precisão exibida | Cobertura | Casos completos | Próximo passo pertinente |
| --- | ---: | ---: | ---: | ---: |
| B0, mensagem genérica | não definida (sem ficha) | 0/32 | 16/48 (33,33%) | 0/32 |
| B1, BM25 + regras | 36/45 (80,00%) | 31/32 (96,88%) | 38/48 (79,17%) | 27/32 (84,38%) |
| Controle lexical pareado | 36/45 (80,00%) | 31/32 (96,88%) | 38/48 (79,17%) | 27/32 (84,38%) |
| 4B, sustentadas e possíveis | 86/174 (49,43%) | 81/96 (84,38%) | 50/144 (34,72%) | 23/96 (23,96%) |
| 8B, somente sustentadas | 81/149 (54,36%) | 72/96 (75,00%) | 68/144 (47,22%) | 32/96 (33,33%) |

A completude de B0 nos 16 casos negativos resulta da ausência de fichas, não de
uma investigação inteligente. Sua cobertura específica permanece zero. B2 é
comparado como recuperação documental; não converter uma sugestão em confirmação.

| Modelo/seed | Precisão | Cobertura | Completude | Erros altos expostos |
| --- | ---: | ---: | ---: | ---: |
| 4B / 125 | 29/58 (50,00%) | 27/32 | 17/48 | 19 |
| 4B / 126 | 29/58 (50,00%) | 27/32 | 17/48 | 18 |
| 4B / 127 | 28/58 (48,28%) | 27/32 | 16/48 | 20 |
| 8B / 125 | 27/50 (54,00%) | 24/32 | 22/48 | 23 |
| 8B / 126 | 27/49 (55,10%) | 24/32 | 23/48 | 22 |
| 8B / 127 | 27/50 (54,00%) | 24/32 | 23/48 | 23 |

B1/controle pareado expuseram cinco erros altos em sua avaliação única; também não
atingiram todos os critérios e não estão homologados como procedimentos operacionais.

O 4B teve 116/219 estados corretos e 101/219 respostas completas. O 8B teve 113/219
estados corretos e 107/219 completas. Guardas bloquearam três dos 60 erros altos
brutos do 4B e 12 dos 80 do 8B; restaram **57 e 68 exposições**, contando as três
seeds. A existência de IDs e o formato válido continuaram insuficientes para
comprovar aplicabilidade. Em E07/K07 e E09/K07, por exemplo, os dois modelos
sustentaram pendência administrativa quando a referência era `not_applicable`.

No subconjunto semântico pré-marcado de 20 instâncias, o controle teve 14/20
completas. O 4B teve 32/60 e o 8B 35/60 slots completos: ganhos de **−16,67 e
−11,67 pontos percentuais**. As perdas globais de completude contra B1 foram
−44,44 e −31,94 pontos. Nenhum modelo atingiu o conjunto de metas congeladas.
Esses resultados da campanha não substituem a análise consolidada do bloco 6.

### Geração curta condicional

**Não executada: zero chamadas.** O modelo pré-selecionado para redação era o 4B;
o gate exigia precisão ≥90%, cobertura ≥75%, próximo passo ≥85% e zero erro alto
exposto em sua campanha completa. Apenas cobertura passou. Não trocar o modelo,
selecionar uma seed ou afrouxar o gate após o teste.

A decisão preserva os 24 casos pré-selecionados e 72 slots planejados. Não há
estimativa de fidelidade, acréscimo de conteúdo ou utilidade da prosa nesta campanha;
"não executado" não significa teste negativo de capacidade de redação.

### Tempo, recursos e orçamento

| Leitor, por ocorrência tentada | 4B | 8B |
| --- | ---: | ---: |
| Média | 3,34 s | 9,23 s |
| P50 | 3,02 s | 8,69 s |
| P95 | 5,92 s | 14,46 s |
| P95 quente | 4,47 s | 12,29 s |

114 slots com chamada por modelo; 106 quentes e oito com carga >0,5 s. Tempos somam
os pedidos por ficha e não diluem latência com 30 slots sem chamada. Embeddings
foram preparados em lote; não foi medido um fluxo interativo frio alternando
embedder e leitor. Desempenho não valida a qualidade das orientações.

- 16 lotes classificadores; **zero timeout, truncamento, parada de recurso ou retry**.
- RSS somado amostrado do runtime: pico de 5,25 GiB; GPU total: 2,78 GiB.
- Swap do host: linha de base de 1.919,50 MiB e pico de 2.173,25 MiB. Sem violação
  do limite de crescimento por lote. Métricas não isolam memória por modelo e podem
  perder picos; VRAM inclui desktop e RSS pode contar páginas compartilhadas.
- Bloco 5: **1.435,77 segundos ativos (23,93 min)**, incluindo carga e embeddings.
- Cumulativo: **716 chamadas generativas, 134 textos e 2.394,89 segundos ativos
  (39,91 min)**. Restam 284 chamadas até o teto rígido, 666 textos e 80,09 min ativos.
- Preparação, testes, revisão e espera de autorização não entram no contador ativo.
  Orçamento disponível não autoriza novos refinamentos ou repetições.
- Runtime vazio ao encerrar; nenhum serviço ou configuração operacional alterado.

### Evidências e verificações

[Exportação sintética completa](evidence/issue-183-block5.json): rankings,
requisições por hash, todas as respostas, scores por seed/estrato, erros, gate,
telemetria e ledger. Nenhum dado de `docs/files/` entra nos prompts ou na exportação.

**166 testes passaram**, incluindo 73 da PoC. Os testes novos verificam retomada,
um modelo por lote, transporte incerto, impossibilidade de abrir rótulos antes
da conclusão, pooling, gate e escape do HTML. **187 arquivos sintéticos validados.**
Ruff lint/formato, compilação e conferência de hashes aprovados. Aviso preexistente
de depreciação httpx/Starlette na regressão da API, sem alterar dependências.

O [comparador estático local](ai-knowledge-poc-comparison.html) contém todos os casos
e seeds, fatos/proveniência, orientações, lacunas, verificações literais, limites,
respostas brutas e bloqueios. Chromium headless conferiu as **144 combinações**, seis
painéis por seleção, toggle de avaliação e largura móvel de 390 px; zero erro de
página e zero requisição externa. Esse teste demonstra funcionamento do comparador,
não compreensão ou benefício de uso medidos com pessoas.


## Reprodução e apresentação

O executor, avaliador e renderer estão no commit local `5e6974f`. Dependem dos
componentes congelados; os novos arquivos acrescentam instrumentação, sem alterar
a decisão científica. A inferência exige autorização da fase, runtime/modelos
fixados e ledger compartilhado. Diretórios e planos não podem ser sobrescritos.

Comandos da campanha registrada (preparação já executada; não repetir em diretórios ocupados):

```bash
backend/.venv/bin/python scripts/run_ai_knowledge_final.py retrieval --budget-root .test-tmp/quality-knowledge-poc-20261109 --run-dir .test-tmp/quality-knowledge-poc-20261109/evaluation/retrieval --allow-inference
backend/.venv/bin/python scripts/run_ai_knowledge_final.py prepare --budget-root .test-tmp/quality-knowledge-poc-20261109 --run-dir .test-tmp/quality-knowledge-poc-20261109/evaluation/classification --retrieval-dir .test-tmp/quality-knowledge-poc-20261109/evaluation/retrieval
backend/.venv/bin/python scripts/run_ai_knowledge_final.py execute --budget-root .test-tmp/quality-knowledge-poc-20261109 --run-dir .test-tmp/quality-knowledge-poc-20261109/evaluation/classification --max-calls 32 --allow-inference
backend/.venv/bin/python scripts/evaluate_ai_knowledge_final.py --budget-root .test-tmp/quality-knowledge-poc-20261109 --run-dir .test-tmp/quality-knowledge-poc-20261109/evaluation/classification
backend/.venv/bin/python scripts/run_ai_knowledge_final.py generation --budget-root .test-tmp/quality-knowledge-poc-20261109 --run-dir .test-tmp/quality-knowledge-poc-20261109/evaluation/generation --classification-dir .test-tmp/quality-knowledge-poc-20261109/evaluation/classification
```

`execute` retoma apenas índices pendentes e para também na troca de modelo. Não
reescrever ledger, planos, marcadores ou respostas para repetir uma tentativa.
Nova reprodução é campanha identificada e autorizada, com outros artefatos e
orçamento explícito; os casos agora conhecidos não voltam a ser teste independente.

Para gerar uma cópia local do comparador a partir dos resultados privados completos:

```bash
backend/.venv/bin/python scripts/render_ai_knowledge_final.py --budget-root .test-tmp/quality-knowledge-poc-20261109 --run-dir .test-tmp/quality-knowledge-poc-20261109/evaluation/classification --output .test-tmp/quality-knowledge-poc-20261109/reports/comparison.html
```

Esse diretório já foi usado. Para outra renderização, use destino novo; o HTML
versionado inclui os próprios dados e abre diretamente no navegador, sem servidor.

## Limitações e próximo passo

Conhecimento e referências são fictícios e foram elaborados pelo mesmo assistente.
As 48 situações finais usam contexto enriquecido simulado, não prova de que o
contrato atual de ingestão disponibiliza tudo isso. Não houve homologação operacional,
participante humano, medição de produtividade ou atualização do agente integrado.

O bloco 6 ainda depende de autorização: auditoria final de contagens/integridade,
incerteza por grupos, análise consolidada de erros e decisão por capacidade. Este
checkpoint registra a campanha, sem encerrar a issue nem substituir esse relatório.
