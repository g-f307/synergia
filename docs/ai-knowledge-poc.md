# PoC de orientação investigativa com conhecimento documentado — #183

Implementação isolada do [plano e contexto aprovados](poc-contexto-e-plano.md).
O responsável autorizou os blocos 1 e 2 em 09/11/2026; continuar no bloco 3 exige
outro aceite. A integração do agente ao produto não faz parte desta issue.

## Insumos e contratos

- [Protocolo executável](ai-knowledge-poc-protocol.json): modelos, parâmetros,
  orçamento, metas e fronteira entre preparação/probes e avaliação final.
- [Fichas legíveis](ai-knowledge-poc-cards.md): 12 fichas fictícias, dez vigentes e
  duas arquivadas; fonte JSON em `data/synthetic/ai-knowledge-v1/knowledge.json`.
- [Corpus e suas limitações](../data/synthetic/ai-knowledge-v1/README.md): 96
  instâncias em 48 grupos de duas variantes, sem dividir grupos entre os conjuntos.
- `scripts/ai_knowledge.py`: entrada tipada, projeção, relações literais e temporais,
  schema de saída e montagem do prompt sem gabarito.

Os contratos de estado distinguem `observed`, `confirmed_absent`, `unknown` e
`not_exposed`. Falso é um valor observado, não um sinônimo de desconhecimento.
Datas devem ter fuso e são comparadas como instantes. Igualdade de lote é literal.
O modelo recebe apenas os campos pertinentes a uma ficha, com IDs e proveniência.

O leitor inicial produz `status`, `evidence_ids` e `missing_fields`. Esses campos
não autorizam uma ação. A escolha trivial de uma única verificação por estado
pertence ao código; explicar a verificação será uma etapa separada, se justificada.

Os quatro estados da explicação são `supported`, `possible`, `rejected` e
`not_applicable`. Sustentação significa compatibilidade com os indícios e a ficha,
sem provar uma causa operacional. ID válido não comprova pertinência da citação.

## Estrutura de dados e independência da avaliação

Desenvolvimento: 32 instâncias/16 grupos; validação: 16/8; reservado: 48/24.
Há oito estratos equilibrados em cada split. O subconjunto semântico final tem
20 instâncias, incluindo casos negativos; sua composição precede inferências.

Notas semânticas e gabaritos foram escritos pelo assistente. Condições objetivas
usam relações verificáveis; não houve homologação de procedimentos ou avaliação
cega independente. A amostra é de desafio, não distribuição operacional.

O loader de inferência lê somente `<split>.json`. Rótulos, estratos, fichas
esperadas e verificações corretas ficam em `<split>-gold.json`. O avaliador lê o
gabarito depois de produzir todos os rankings ou respostas. A conferência de
integridade pode examinar estrutura/contagens de todos os splits, sem executá-los
ou usá-los para ajustar parâmetros.

Os exemplos positivos/negativos das fichas são de desenvolvimento e ficam fora
do prompt inicial. Usá-los depois exige uma variante identificada. Não recalcular
o gabarito para concordar com uma inferência nem reclassificar casos conhecidos
como novos reservados.

## Disponibilidade dos fatos

Todas as identidades e notas são sintéticas. `field-origins.json` identifica se
um campo existe no contrato atual, somente no workbook ou apenas foi acrescentado
à simulação. Nenhuma linha/texto real foi copiado para o corpus.

D19/D20 simulam uma projeção limitada ao contrato atual: flags não ingeridas
ficam não expostas. As demais 94 instâncias são enriquecidas. A campanha final,
portanto, testa a hipótese com contexto simulado e não demonstra que a ingestão
atual já entrega tudo que uma integração exigiria. Esse limite é deliberadamente
visível, sem ampliar o adaptador dentro desta PoC.

## Recuperação inicial

`scripts/ai_knowledge_retrieval.py` calcula BM25 em português sem eliminar negações,
similaridade cosseno de embeddings e fusão de rankings por RRF (constante 60).
O índice contém somente fichas vigentes; excluir versões antigas é um controle
do código, não um acerto creditado ao modelo.

Cada ocorrência produz um resumo de sinais e, se disponível, uma vista da nota.
Não há pergunta escrita pelo usuário. A versão inicial dá peso igual às vistas
na fusão e compara busca lexical, densa e híbrida sem escolher um vencedor após
consultar o reservado. Embeddings usam `qwen3-embedding:0.6b` Q8_0 e instrução de
consulta registrada no protocolo. Documentos não recebem essa instrução.

Rankings são candidatos, não decisões de aplicabilidade. Nesta etapa não há limiar
de “nenhuma ficha”. Casos sem documentação pertinente continuam no relatório, com
a quantidade de sugestões indevidas visível. Calibrar abstenção é trabalho futuro.

Reportar Recall@1/2/3/5, precisão, MRR e resultados do subconjunto semântico.
Alguns casos exigem mais de duas fichas; calcular também o teto que o próprio
limite de duas fichas impõe, antes de atribuir a perda ao recuperador/modelo.

## Probes e orçamento

`scripts/run_ai_knowledge_infrastructure.py` implementa somente os dois modos do
bloco 2: recuperação no desenvolvimento e seis probes (D03/K02, D05/K05, D15/K02
em cada modelo). Não implementa calibração nem execução do reservado.

As fichas dos probes são fornecidas manualmente. Eles medem carregamento, contexto,
schema, latência e alocação; não estimam a qualidade de uma arquitetura RAG completa.
O primeiro pedido de cada modelo é frio; os dois seguintes são observações quentes
de tarefas diferentes, insuficientes para estimar um P95 produtivo.

`scripts/ai_knowledge_runtime.py` aceita somente localhost fixado, sem proxy ou
redirecionamento, verifica digests e registra parâmetros e hashes dos templates.
Um ledger compartilhado entre diretórios cobra tentativas antes do envio. Ele
contabiliza textos de embeddings, chamadas generativas e tempo ativo com carga.
Cache reutiliza somente vetores identificados por hash de texto/modelo/contexto.

Timeout/falha de transporte preserva a tentativa e o tempo reservado, bloqueando
novas inferências até reconciliação explícita. Isso evita presumir que o cancelamento
HTTP encerrou a execução no servidor. Nenhum retry ou fallback encobre uma falha.
O lock impede dois runners desta PoC; não impede outro cliente externo de usar o
mesmo Ollama. A dedicação do runtime continua sendo uma condição do ensaio.

O orçamento aprovado é 1000 chamadas generativas no máximo, 800 textos para
embeddings e 7200 segundos ativos cumulativos. O modo probe tem teto próprio de
24 chamadas. Tempo editorial/testes fica separado. Lotes param conforme protocolo,
com margem de disco de 4 GiB, RAM disponível de 2 GiB e reserva de VRAM de 128 MiB.
Swap crescendo mais de 512 MiB interrompe o lote. Essas são guardas experimentais.

## Comandos

A partir da raiz, com o Python local do backend:

```bash
backend/.venv/bin/python scripts/prepare_ai_knowledge.py verify
backend/.venv/bin/python -m pytest -c backend/pytest.ini backend/tests/test_ai_knowledge_foundation.py backend/tests/test_ai_knowledge_retrieval.py backend/tests/test_ai_knowledge_runtime.py -q
```

Inferências exigem Ollama local, pesos/pins do protocolo e autorização da etapa.
O embedder só precisa ser obtido uma vez; download não faz parte do runner.
Cada execução usa um subdiretório novo, recusando sobrescrever os anteriores:

```bash
backend/.venv/bin/python scripts/run_ai_knowledge_infrastructure.py retrieval --budget-root .test-tmp/quality-knowledge-poc-20261109 --output-dir .test-tmp/quality-knowledge-poc-20261109/retrieval/initial --allow-inference
backend/.venv/bin/python scripts/run_ai_knowledge_infrastructure.py probe --budget-root .test-tmp/quality-knowledge-poc-20261109 --output-dir .test-tmp/quality-knowledge-poc-20261109/runs/infrastructure --allow-inference
```

Esses diretórios da primeira execução já estarão ocupados depois do checkpoint.
Reprodução usa novos nomes, conserva o ledger da campanha e conta o custo adicional.
Nova campanha independente tem novo ledger e não pode apagar/substituir a anterior.

Hashes de código, protocolo, manifestos e requisições são gravados antes da primeira
inferência de cada rodada. Resultados brutos, cache e pesos não entram no Git.
Evidências versionadas devem ser sanitizadas e suficientes para conferir os números.

## Continuidade

O resultado dos dois primeiros blocos está no
[checkpoint 1–2](ai-knowledge-poc-checkpoint-1-2.md).

O próximo trabalho, após aprovação, é o bloco 3: selecionar hipóteses de refinamento
com base nas falhas, sem abrir o reservado. O runtime/avaliador final, apresentação
estática e decisão da PoC serão construídos nos blocos seguintes. A existência de
um probe válido não antecipa essas entregas nem comprova benefício operacional.
