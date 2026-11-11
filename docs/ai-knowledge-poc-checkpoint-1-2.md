# Checkpoint dos blocos 1 e 2 — PoC #183

09/11/2026, America/Manaus. Dados e conhecimento fictícios. Probes e recuperação
somente no desenvolvimento. A continuação no bloco 3 depende de autorização.

## Resultado

**A infraestrutura executa os modelos, mas a recuperação inicial ainda perde
conhecimento pertinente.** Os probes não comprovam qualidade geral do leitor nem
benefício operacional. Não houve calibração, inferência de validação/reservado,
atualização do agente ou alteração do banco/ingestão.

Os [dados sanitizados](evidence/issue-183-blocks-1-2.json) permitem conferir números,
pins, hashes e limitações. O [guia](ai-knowledge-poc.md) contém os comandos.

## Bloco 1 — Entregue

- 12 fichas com indícios, critérios, lacunas, verificações, exemplos e limites:
  dez vigentes e duas arquivadas. [Fichas legíveis](ai-knowledge-poc-cards.md).
- 96 instâncias em 48 grupos de duas variantes, mantidas no mesmo split:
  desenvolvimento 32/16 grupos; validação 16/8; reservado 48/24.
- Oito estratos equilibrados: fatos claros, linguagem semântica, desconhecimento,
  cronologia, flags, conflitos/múltiplas explicações, distrações e ausência de ficha.
- Gabarito separado da entrada e 20 instâncias finais marcadas para a comparação
  semântica. O mesmo assistente elaborou base e rótulos; não é avaliação independente.
- Manifesto de hashes, projeção factual, contratos de estado e testes offline.

Exemplos concretos de desenvolvimento:

| Caso | Entrada | Referência editorial |
| --- | --- | --- |
| D05 | “O laboratório separou outra amostra; o parecer da nova medição ainda não voltou.”, com restrição confirmada | K05 compatível; procurar o registro da confirmação no mesmo lote |
| D06 | “Não há outra medição pendente; o laboratório encerrou a confirmação.” | K05 contradita, sem reabrir a hipótese por menção isolada a medição |
| D09 | Restrição confirmada e motivo `confirmed_absent` | K04 compatível com ausência no recorte, sem explicar sua causa |
| D10 | Restrição confirmada e motivo `not_exposed` | K04 possível; não dizer que o motivo está vazio |
| D15 | Aprovação e retenção no mesmo instante, com fuso | Não afirmar que a retenção foi posterior; aprovação também não prova encerramento |

Os exemplos das fichas ficam fora do prompt inicial; seu uso posterior exigirá
uma ablação identificada. Nenhum caso final foi usado como exemplo para inferência.

### Limite da disponibilidade de dados

D19/D20 representam o contrato atual com campos não ingeridos explicitamente não
expostos. As outras 94 instâncias usam enriquecimento sintético. Isso permite testar
a hipótese documental, mas sucesso no reservado não provará prontidão da ingestão
ou existência desse contexto em produção.

O material editorial teve correções de consistência antes da primeira inferência,
registradas no manifesto. Depois do congelamento desta rodada, os bytes dos insumos
e dos executores foram preservados e seus hashes conferidos.

## Bloco 2 — Recuperação inicial

32 instâncias de desenvolvimento: 21 com alguma ficha pertinente e 11 sem ficha
aplicável. O subconjunto semântico tem 14 instâncias, sete respondíveis. Há variantes
correlacionadas e esses tamanhos não são amostra da população operacional.

| Braço | Recall@2 nos respondíveis | Precisão@2 em todos os casos | MRR nos respondíveis |
| --- | ---: | ---: | ---: |
| BM25 | 70,95% | 28,13% | 0,7077 |
| Embeddings | 40,00% | 17,19% | 0,5040 |
| Híbrido | 59,05% | 25,00% | 0,6230 |

O Recall@2 semântico foi 42,86% no BM25, 14,29% no denso e 21,43% no híbrido.
Nenhum braço atingiu a meta exploratória de 90% nesta versão inicial.

A arquitetura de duas fichas tem teto médio de Recall@2 de 97,14% nesses casos.
Portanto parte da perda é estrutural, mas o limite de duas fichas não explica
a maior parte dos erros observados. Não foi aumentado para melhorar a tabela.

Todos os 11 casos sem ficha receberam candidatos: ainda não há limiar de abstenção.
Isso é explicitamente uma busca de candidatos, não orientação validada. A pertinência
terá que ser decidida/verificada na etapa seguinte; não contabilizar sugestões
indevidas como sucesso nem esconder esses casos no cálculo de precisão.

### Diagnóstico para a próxima hipótese

Uma inspeção posterior, sem nova inferência, examinou as vistas individuais de
D05, D07, D21 e D23. Na vista da nota, o denso colocou K05, K06, K06 e K07 no topo;
em D21, K05 também veio em segundo. Esses IDs correspondiam aos indícios textuais.
Na vista dos sinais, os quatro casos apresentaram K02/K08/K01 no topo, mesmo sem
a combinação factual necessária àquela interpretação.

Esse contraste sustenta investigar **ruído da vista genérica e sua fusão com a nota**,
em vez de concluir incapacidade geral do embedder. É análise post-hoc de quatro
falhas conhecidas, não um novo braço aprovado ou uma melhoria validada. Não houve
ajuste de peso, prompt, índice, limiar ou escolha de vencedor após esse diagnóstico.

## Bloco 2 — Probes de infraestrutura

Fichas fornecidas manualmente, três casos por modelo. Os seis probes retornaram
schema válido e o estado esperado: sustentado em D03/K02 e D05/K05, contradito em
D15/K02. Não houve timeout ou truncamento. Isso não é taxa de respostas completas,
avaliação de verificações humanas ou generalização para o corpus inteiro.

| Modelo | Primeira chamada fria | Duas chamadas quentes | Tokens de entrada |
| --- | ---: | ---: | ---: |
| 4B Instruct-2507 Q4_K_M | 7,29 s | 1,99 e 2,08 s | 1.187–1.335 |
| 8B Q4_K_M | 13,81 s | 6,64 e 6,16 s | 1.195–1.343 |

Contexto 4096, até 512 tokens de saída, seis threads, temperatura zero e seed 125.
Os outros samplers herdaram os parâmetros dos modelos fixados, registrados no
snapshot. Os modelos diferem em variante e tamanho; não é comparação causal de
número de parâmetros. As saídas usaram 44–62 tokens, com folga no contexto.

Os dois modelos ficaram descarregados ao final. O 8B continua usando CPU/GPU em
conjunto; a GPU de 4 GiB não significa residência integral ou capacidade concorrente.

### Recursos e orçamento observado

- Modelo adicional instalado: `qwen3-embedding:0.6b`, Q8_0, 639.150.858 bytes;
  digest fixado no protocolo. Não houve instalação de PyTorch ou serviço vetorial.
- 58 textos únicos de embedding, em oito requisições, com cache por hash.
- Seis chamadas generativas; zero chamadas de calibração ou reservado.
- Tempo ativo contabilizado: **51,83 segundos**, incluindo carga dos modelos;
  elaboração e testes não estão nesse número.
- Recuperação: pico amostrado de RSS somado do runtime de 0,94 GiB e de GPU total
  de 1,30 GiB; nenhum limite de recurso atingido.
- Probes: pico amostrado de RSS somado de 5,21 GiB e de GPU total de 2,71 GiB;
  swap observado passou de zero para 1 MiB, abaixo do limite de crescimento.

RSS pode contar páginas compartilhadas e VRAM inclui desktop. Picos pertencem à
rodada, não são medição causal de memória por modelo. Amostragem pode perder picos.

Restam 994 chamadas até o teto rígido, 742 textos e aproximadamente 119,14 minutos
ativos. A quota restante de probes é 18; isso não autoriza consumi-la sem necessidade.

Com as duas observações quentes por modelo e distribuição equilibrada, as 896
chamadas estruturadas máximas das fases de calibração/refinamento/validação/final
projetam aproximadamente **63 minutos**. É estimativa preliminar: não inclui novos
probes, custos de alternância, thinking ou redação mais longa, e não mede a latência
interativa completa do RAG. O teto continua sendo fiscalizado pelo ledger; novas
medições devem atualizar a previsão antes de congelar a campanha final.

## Verificações e continuidade

Os testes automatizados cobrem contratos, desconhecimento, ordem temporal, origem,
ausência de gold no prompt, separação de grupos, hashes, métricas, abstenção,
preservação de falhas, lock, orçamento cumulativo e retomada sem retry implícito.
São offline e não dependem de credenciais ou Ollama.

Resultados efetivamente obtidos na revisão final:

- **131 testes aprovados**, incluindo 38 da nova PoC e 15 do validador de ativos;
  os restantes cobrem fundação, explicação e API existentes. A regressão HTTP
  executou fora do sandbox após a tentativa interna ficar bloqueada e ser interrompida.
- **187 arquivos sintéticos** conferidos pelo validador existente, que agora
  reconhece o novo manifesto em vez de encaminhá-lo ao contrato antigo de fixtures.
- Ruff lint e formato aprovados para os dez arquivos Python envolvidos; compilação
  Python e `git diff --check` aprovados.
- Os hashes de código/insumos das duas rodadas conferem com os snapshots registrados.
- Um aviso de depreciação de `httpx`/Starlette apareceu na regressão existente;
  não foi alterada dependência fora do escopo.

```bash
backend/.venv/bin/python -m pytest -c backend/pytest.ini backend/tests/test_ai_knowledge_foundation.py backend/tests/test_ai_knowledge_retrieval.py backend/tests/test_ai_knowledge_runtime.py backend/tests/test_ai_poc_foundation.py backend/tests/test_ai_quality_explanation.py backend/tests/test_ai_quality_api.py backend/tests/test_project_assets.py -q
backend/.venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); from validate_project_assets import validate_synthetic_data; validate_synthetic_data()"
```

A conclusão desta etapa é: **insumos preparados e execução local tecnicamente viável;
recuperação inicial ainda inadequada e com uma hipótese concreta de melhoria**.
O próximo bloco poderá testar essa hipótese e a interpretação, após aprovação,
preservando os resultados desta primeira rodada e sem usar o reservado para tuning.
