# Checkpoint dos blocos 3 e 4 — PoC #183

09/11/2026, America/Manaus. Continuação autorizada após o
[checkpoint 1–2](ai-knowledge-poc-checkpoint-1-2.md). **Blocos 3 e 4 concluídos;
blocos 5 e 6 aguardam nova autorização.** Nenhuma inferência no reservado, geração
curta ou integração ao agente foi executada.

## Resultado principal

**A busca melhorou; a interpretação com LLM não atingiu os critérios de viabilidade.**
Os refinamentos reduziram erros formais, mas a confirmação e a validação revelaram
muitos falsos positivos de aplicabilidade. Base documental, filtros objetivos e
schema não podem ser contabilizados como inteligência adicional do leitor.

A configuração foi congelada para permitir a campanha final sem ajustar o teste.
Congelamento significa estabilidade experimental, não aprovação para integração.
A evidência de desenvolvimento/seleção já é desfavorável ao leitor nesta arquitetura;
a campanha reservada poderá confirmar sua extensão, sem recomeçar o refinamento.

Artefatos:

- [Desenho dos refinamentos](ai-knowledge-poc-development.json).
- [Rubrica e critérios de seleção/geração](ai-knowledge-poc-rubric.json).
- [Resultados, respostas sintéticas, erros, recursos e orçamento](evidence/issue-183-blocks-3-4.json).
- [Configuração final congelada](ai-knowledge-poc-final-config.json).
- [Consultas, ordem e hashes dos possíveis pedidos finais](evidence/issue-183-final-matrix.json).

## Bloco 3 — Calibração e refinamentos

### Calibração de parâmetros

Oito pares caso/ficha predefinidos, dois perfis e duas seeds por modelo: 64 chamadas.
As fichas foram fornecidas diretamente, para separar leitura de recuperação. São
casos conhecidos, não estimativa independente de generalização.

| Modelo/perfil | JSON válido | Estado correto | Resposta completa | Erros altos brutos |
| --- | ---: | ---: | ---: | ---: |
| 4B / histórico | 16/16 | 14/16 | 8/16 | 0 |
| 4B / recomendado | 16/16 | 14/16 | 8/16 | 0 |
| 8B / histórico | 16/16 | 14/16 | 8/16 | 0 |
| 8B / recomendado | 16/16 | 14/16 | 8/16 | 0 |

Resposta completa exige estado, referências decisivas e lacunas consistentes.
Os modelos frequentemente listaram campos observados como ausentes. A cronologia,
os estados falsos e os requisitos de escopo também continuaram sujeitos a erro.

A qualidade empatou. O desempate usou a média de processamento de prompt + geração
informada pelo servidor, excluindo carga fria: 4B histórico 1,499 s versus 1,518 s;
8B recomendado 4,130 s versus 5,421 s. Foram selecionados **histórico no 4B** e
**recomendado no 8B**. A diferença do 4B é pequena; não sustenta superioridade geral.
Samplers herdados e versões são registrados. Modelos diferem em variante e tamanho;
a comparação não isola o efeito causal da quantidade de parâmetros.

### Ciclo 1 — Consulta focada e checklist

Hipótese registrada antes da rodada: a vista genérica dilui a nota e recupera fichas
contrárias ao escopo. O código passa a excluir contradições objetivas, prioriza
fichas estruturadas compatíveis e usa a vista da nota na busca textual. Esses
controles recebem crédito de código e ficam disponíveis ao comparador lexical.

32 casos, 21 respondíveis; nenhuma nova inferência de embeddings no desenvolvimento,
pois os 58 vetores anteriores foram reutilizados por hash.

| Recuperador | Recall@2 | MRR | Recall@1 |
| --- | ---: | ---: | ---: |
| BM25 inicial | 70,95% | 0,7077 | 43,81% |
| Denso inicial | 40,00% | 0,5040 | 22,38% |
| Híbrido inicial | 59,05% | 0,6230 | 31,90% |
| BM25 focado | 97,14% | 0,9524 | 79,52% |
| Denso focado | 97,14% | 1,0000 | 89,05% |
| Híbrido focado | 97,14% | 1,0000 | 89,05% |

O teto de duas fichas é 97,14%. O ganho comum em Recall@2 inclui mudanças objetivas
de seleção e não demonstra ganho exclusivo dos embeddings. Denso foi selecionado
pelo desempate em MRR, empatado com híbrido, evitando a fusão adicional. Quatro dos
11 casos negativos ainda receberam sugestões: candidato não significa orientação.

Na leitura, oito outros pares caso/ficha predefinidos × dois prompts × dois modelos:
32 chamadas. O checklist reforça escopo, nota pertinente, negação, evidências e
lacunas realmente desconhecidas. Resultado pareado:

| Modelo | Completa com mínimo | Completa com checklist | Estado correto em ambos |
| --- | ---: | ---: | ---: |
| 4B | 1/8 | 3/8 | 6/8 |
| 8B | 1/8 | 5/8 | 6/8 |

Decisão: manter checklist, sem atribuir a ele melhoria de estado inexistente.

### Ciclo 2 — Schema tipado das lacunas

O desenho inicial considerava exemplos contrastivos. Após revisar todos os erros
do ciclo 1, foi registrada **antes da nova inferência** uma substituição: restringir
`missing_fields` a campos efetivamente indisponíveis. Não houve uso da validação
ou do reservado nessa decisão. O desenho antigo e os hashes continuam na evidência.
Exemplos contrastivos e thinking não foram executados; não se afirma que falharam.

32 chamadas pareadas, mesmos oito pares/perfis: checklist versus `typed_checklist`.
A alteração é o domínio permitido no schema e sua representação no prompt; fatos,
estados possíveis, critérios, referências e guardas permanecem equivalentes.

| Modelo | Completa com checklist | Completa com schema tipado | Estado correto em ambos |
| --- | ---: | ---: | ---: |
| 4B | 3/8 | 6/8 | 6/8 |
| 8B | 5/8 | 6/8 | 6/8 |

Decisão: manter a variante tipada. É contenção mecânica por código, **não evidência
de melhora da interpretação semântica**. O 8B ainda cometeu dois erros altos brutos
nessa triagem; as condições objetivas os bloquearam.

### Ciclo 3 — Confirmação no desenvolvimento completo

32 instâncias, até duas fichas por ocorrência, 46 chamadas por modelo: 92 chamadas.
Os sete casos sem candidatos continuam nas métricas, sem serem inventadas chamadas
para eles. As duas variantes de apresentação foram medidas, sem novo ajuste.

Tabela com apresentação de sustentadas e possíveis, para comparação uniforme:

| Braço | Precisão exibida | Cobertura dos respondíveis | Casos inteiramente corretos | Próximo passo pertinente¹ | Erros altos expostos |
| --- | ---: | ---: | ---: | ---: | ---: |
| Controle lexical com mesmos candidatos | 25/27 (92,59%) | 21/21 | 29/32 | 20/21 | 2 |
| 4B | 18/35 (51,43%) | 16/21 | 13/32 | 5/21 | 13 |
| 8B | 18/35 (51,43%) | 17/21 | 13/32 | 6/21 | 16 |

¹ Exige ao menos uma verificação correta e nenhuma orientação indevida na mesma
ocorrência, incluindo omissões no denominador. O ID/texto da verificação é anexado
pelo código, não escolhido autonomamente pelo modelo.

A triagem de ficha indicada não cobria bem o risco de fichas secundárias. Na
confirmação, os modelos sustentaram repetidamente assuntos ausentes da ocorrência.
Exemplo D09: nota sobre ausência de justificativa no extrato; os dois modelos
sustentaram K07, de pendência administrativa/documental, citando IDs existentes.
IDs corretos e restrição confirmada não comprovavam essa hipótese. D23/K06 também
foi sustentada sem indício de etiqueta na nota de conflito documental.

As guardas bloqueiam condições objetivas e referências incompletas, mas não resolvem
essa interpretação textual. Não foram acrescentadas regras após ver esses erros.
A acurácia de estado bruto foi 26/46 no 4B e 25/46 no 8B, apesar de schema válido
em todas as chamadas. Não esconder erros atrás da taxa de JSON válido.

## Bloco 4 — Validação e congelamento

Uma única campanha de validação: 16 instâncias/8 grupos, dez respondíveis, 26
chamadas por modelo. Recuperador, perfis, prompts, schema e guardas foram fixados
antes da recuperação de validação. Só as duas políticas previstas e o modelo da
redação foram selecionados pelos resultados. Um lock impede preparar outra rodada
de validação na mesma campanha. Não houve retuning depois de ver esses rótulos.

Recall@2 foi 100% nos três recuperadores focados. BM25/híbrido tiveram MRR 1,0 e
denso 0,95; denso não teve ganho exclusivo e o algoritmo pré-selecionado foi mantido.
Três dos seis casos negativos ainda receberam candidatos. Foram embutidos 20 textos
novos; total cumulativo de 78.

Políticas selecionadas pela ordem predefinida: erros altos expostos, completude,
cobertura, precisão e latência. Elas não eliminam os erros altos identificados:

| Braço/política | Precisão exibida | Cobertura | Casos inteiramente corretos | Próximo passo¹ | Erros altos expostos |
| --- | ---: | ---: | ---: | ---: | ---: |
| Controle lexical, sustentadas/possíveis | 10/13 (76,92%) | 9/10 | 13/16 | 8/10 | 1 |
| 4B, sustentadas/possíveis | 7/15 (46,67%) | 6/10 | 7/16 | 3/10 | 7 |
| 8B, somente sustentadas | 7/19 (36,84%) | 7/10 | 4/16 | 0/10 | 12 |

A validade estrutural foi 26/26 em ambos, mas resposta bruta completa ficou em
10/26 no 4B e 8/26 no 8B. A política somente sustentadas não torna o 8B seguro:
os falsos positivos principais são justamente sustentadas indevidas.

No subconjunto semântico de validação, são apenas seis instâncias/três grupos,
três respondíveis. Completude: controle 3/6, 4B 4/6, 8B 3/6. O ganho isolado do 4B
é 16,67 pontos, mas acompanha perda global de 37,5 pontos e sete erros altos expostos.
Não atende ao conjunto de critérios. Desenvolvimento e validação também divergem;
esses números pequenos não demonstram benefício operacional nem são teste final.

O **4B** foi escolhido para eventual redação por sua melhor completude e menor
quantidade de erros altos na validação. Isso não comprova capacidade de redação,
não autoriza sua apresentação e não transforma uma configuração ruim em aprovada.

### O que ficou congelado

- Base/corpus/gabaritos originais por hash, sem correção de rótulos para ajustar resultado.
- Código do leitor, recuperação, guardas, templates, schemas, rubrica e orçamento.
- Modelos/digests, quantizações, runtime, samplers herdados, contexto 4096,
  saída até 512 tokens, seis threads, thinking desativado e timeout de 45 s.
- Denso focado, máximo duas fichas, um pedido por ficha; mesmos controles objetivos
  disponíveis ao comparador lexical; comparação BM25/denso/híbrido preservada.
- Perfis/políticas por modelo; seeds 125/126/127, ordem de casos embaralhada por
  seed registrada e ordem de modelos alternada entre seeds.
- Consultas exatas dos 48 insumos finais e hashes de todos os possíveis pedidos de
  leitura: dez fichas × dois modelos × três seeds por caso. São **possibilidades de
  serialização, não 2.880 inferências**; só até duas fichas/caso poderão ser executadas.
- 24 casos de redação definidos sem consultar saídas: três por estrato e variantes
  equilibradas. Template curto, procedimento literal fora da prosa e rubrica.

As entradas reservadas foram apenas serializadas, sem consulta aos rótulos para
escolher parâmetros e **sem inferência**. O manifesto de integridade confere bytes
dos gabaritos, mas não os entrega ao executor. O runner final ainda será construído
no bloco 5 sobre estes componentes congelados; instrumentação pode ser acrescentada,
sem alterar decisões/prompt/schema/rubrica ou ajustar pelo reservado.

A redação só roda se a classificação final do modelo escolhido atingir precisão
≥90%, cobertura ≥75%, próximo passo ≥85% e zero erro alto exposto. Esse gate avalia
a campanha completa; não escolhe a melhor seed. Sem seleção elegível, não há chamada
de prosa naquele caso e a omissão permanece na análise end-to-end. Pelo resultado
atual, não há fundamento para antecipar que o gate será atingido.

## Recursos, execução e orçamento

272 novas chamadas generativas: calibração 64, triagens 64, confirmação 92 e validação
52. Com os seis probes anteriores, total **278**, e **78 textos** de embeddings.
Nenhum timeout, truncamento ou erro de transporte; todas as tentativas concluídas
foram preservadas, sem retry semântico ou repetição ao retomar lotes.

Houve **duas paradas por crescimento de swap**, em lotes com troca sequencial de
modelos. Após cada parada: descarregamento confirmado, verificação de RAM e paginação,
registro da ocorrência e retomada somente dos índices pendentes. Havia mais de
10 GiB disponíveis e paginação estável após descarregar; isso não identifica qual
processo foi movido para swap. Nenhum serviço/configuração do computador foi alterado.
Lotes posteriores foram separados por modelo, com os mesmos limites de recurso.

Picos amostrados dos blocos: RSS somado do runtime 5,41 GiB, GPU total 2,77 GiB.
Swap do host passou de 1 MiB a pico de 2.049 MiB ao longo das rodadas. O limite de
crescimento é por lote; não se deve interpretar ausência de nova parada como ausência
de custo acumulado de paginação. RSS pode contar páginas compartilhadas; VRAM inclui
desktop; amostragem pode perder picos. Não são estimativas causais por modelo.

| Medida na validação | 4B | 8B |
| --- | ---: | ---: |
| Média por ocorrência tentada, leitor completo | 3,57 s | 9,21 s |
| P50 por ocorrência tentada | 2,93 s | 8,66 s |
| P95 por ocorrência tentada | 7,19 s | 16,01 s |
| P95 quente, sem ocorrência com carga >0,5 s | 4,20 s | 11,96 s |

Tempos somam os pedidos por ficha; 13 ocorrências tentadas por modelo, das quais
11 quentes no 4B e 12 no 8B. Não diluir latência com os três casos sem chamadas.
Embeddings/contexto foram preparados em lote; não foi medido o fluxo interativo
frio que alterna embedder/leitor. Os números não são SLA do RAG integrado.

Tempo ativo cumulativo: **959,13 s (15,99 min)**, incluindo carga e embeddings.
Restam **104,01 min ativos**, 722 chamadas até o teto rígido e 722 textos.
Elaboração, revisão, permissões e testes ficam fora do contador de inferência;
não são uma promessa de duração total da tarefa.

Os tetos da campanha final continuam 576 chamadas de classificação e 72 condicionais
de redação. A média observada por chamada sugere cerca de 31 minutos para o teto
classificador, mais carga/embeddings e eventual prosa; estimativa, não garantia.
As quotas não utilizadas em refinamento não autorizam um quarto ciclo automático.

## Verificações e continuidade

- **152 testes aprovados**, incluindo 59 da fundação/recuperação/runtime/leitor/
  runner/congelamento desta PoC e regressão da explicação/API existentes.
- **187 arquivos sintéticos validados** pelo validador do projeto.
- Ruff lint/formato, compilação, integridade do congelamento e revisão de diff.
- Um aviso preexistente de depreciação de httpx/Starlette na API; sem mudança de dependência.
- Dados reais continuam ignorados; app, banco, ingestão e agente integrado preservados.

As evidências preservam respostas sintéticas, parâmetros, hashes, versões anteriores
reconstruíveis e todos os erros. Antes da primeira pontuação, o cálculo de próximo
passo foi corrigido para exigir ausência de orientação indevida na ocorrência, em
vez de reutilizar cobertura. Nenhum rótulo, chamada ou limiar mudou nessa correção;
os hashes do avaliador utilizado acompanham cada score.

**Próximo checkpoint depende de autorização:** blocos 5 e 6, executar os 48 reservados
com três seeds nos dois modelos, avaliar baselines e eventual redação pelo gate,
produzir apresentação estática, auditoria e conclusão por capacidade. Não corrigir
falsos positivos usando resultados finais nem recomendar integração com esta
validação desfavorável.
