# Relatório final — orientação investigativa com RAG local — #183

10/11/2026, America/Manaus. Seis blocos concluídos após autorizações por etapa.
Base e situações fictícias. Resultado técnico do recorte simulado, sem homologação
operacional ou avaliação de utilidade com pessoas.

## Conclusão executiva

**Não integrar a configuração avaliada ao agente de qualidade.** A busca recuperou
as fichas pertinentes, mas os leitores 4B/8B acrescentaram falsos positivos e reduziram
a correção das orientações frente ao mesmo conhecimento com BM25/regras simples.
As metas de qualidade não foram atingidas, mesmo com schema válido e execução local
viável. Não houve necessidade de exigir 99% de confiabilidade para chegar a essa decisão.

Isso encerra esta investigação, sem provar que todo RAG ou todo modelo local seja
inútil. Preservar os artefatos experimentais e o agente existente; uma reformulação
do produto ou outro ciclo exige hipótese, escopo e autorização próprios. A necessidade
de uma IA útil continua sendo um objetivo do projeto, ainda não resolvido por esta PoC.

| Capacidade | Evidência | Decisão |
| --- | --- | --- |
| Conhecimento documentado | B1 exibiu 36/45 orientações corretas e cobriu 31/32 casos respondíveis, contra nenhuma orientação específica de B0 | Estrutura de documentação reaproveitável; benefício operacional não medido e regras ainda falham |
| Recuperação | BM25, denso e híbrido focados: Recall@2 de 100%; híbrido ordenou um primeiro resultado melhor | Busca funciona no corpus; ganho exclusivo dos embeddings não demonstrado na meta principal |
| Interpretação 4B | Precisão 49,43%, 57 erros altos expostos em três seeds | Não aprovada para integração |
| Interpretação 8B | Precisão 54,36%, 68 erros altos expostos em três seeds | Não aprovada para integração |
| Redação curta | Gate de seleção falhou; nenhuma chamada de prosa | Não avaliada; não concluir incapacidade de redação |
| Execução local | Campanha final sem falhas de execução; P95 quente do leitor 4,47/12,29 s | Tecnicamente executável, sem demonstrar SLA interativo do produto |

## Contexto, desenho e fronteira da entrega

O [contexto e plano](poc-contexto-e-plano.md) partem da PoC #179, que produziu
explicações iguais ao baseline, e das investigações com modelos locais. A hipótese
nova foi usar conhecimento documentado para relacionar indícios, limites e próximas
verificações, sem exigir que o usuário formule uma pergunta.

A base contém dez fichas vigentes e duas arquivadas. São 96 instâncias em 48 grupos
A/B: desenvolvimento 32/16 grupos, validação 16/8, reservado 48/24. Grupos relacionados
não atravessam splits. O reservado inclui 20 instâncias semânticas em dez grupos,
11 das quais respondíveis, e oito estratos de desafio equilibrados.

Modelos fixados: Qwen3 4B Instruct-2507 e Qwen3 8B, ambos Q4_K_M, com digests/runtime
registrados no [congelamento](ai-knowledge-poc-final-config.json). Embeddings locais
Qwen3-Embedding 0.6B Q8_0; índice em arquivos/memória, sem banco vetorial dedicado.
Uma ficha por chamada, no máximo duas por ocorrência. Pensamento desativado.

Foram comparados fatos com mensagem genérica (B0), BM25/regras (B1), recuperação
densa documental (B2), controle lexical com os mesmos candidatos densos, leitores
4B/8B, fichas fornecidas diretamente no desenvolvimento (R*) e redação condicional.
Os mesmos fatos e filtros objetivos estavam disponíveis aos comparadores.

Os perfis e políticas diferem: 4B histórico/temperatura zero, com sustentadas e
possíveis; 8B recomendado/temperatura 0,7, somente sustentadas. Também diferem as
variantes dos modelos. Portanto os números comparam configurações completas;
não isolam o efeito causal da quantidade de parâmetros.

O agente integrado atual trabalha sobre grupos de ocorrências de validação/importação,
como campos ausentes e registros duplicados (`backend/app/ai_quality_core.py`).
A nova PoC trata investigação de retenções/lotes. **Não é uma substituição direta do
modelo nesse contrato existente.** Todas as 48 entradas finais usam contexto enriquecido
simulado; a PoC não acrescentou esses fatos à ingestão ou à API.

A matriz de origens identifica conceitos futuros, não um mapeamento operacional
completo. Por exemplo, `ship_block_flag` já existe na normalização/regras genéricas,
o que não garante que a observação, o motivo e a sequência de eventos desta PoC
estejam disponíveis no fluxo do agente. Uma eventual integração precisaria mapear
fontes, autoridade, vínculo de lote, datas, permissões e estados desconhecidos.

## Evolução e refinamentos preservados

| Etapa | Resultado e decisão |
| --- | --- |
| Blocos 1/2 | Corpus/base/protocolo e infraestrutura; seis probes com estado esperado. Denso inicial Recall@2 40% no desenvolvimento; não foi aprovado como recuperação suficiente |
| Calibração | 64 chamadas, oito pares de ficha indicada e duas seeds por perfil/modelo. Qualidade empatada; perfis escolhidos por desempate de tempo, sem prova causal de superioridade |
| Ciclo 1 | Consulta focada e filtros objetivos elevaram Recall@2 a 97,14%, no teto de duas fichas. Checklist aumentou respostas completas: 1→3/8 no 4B e 1→5/8 no 8B |
| Ciclo 2 | Substituição registrada antes da rodada: schema restringe lacunas a campos indisponíveis, em vez dos exemplos contrastivos inicialmente previstos. Completa 6/8 em ambos, estados ainda 6/8; ganho de código, não inteligência adicional |
| Ciclo 3 | Confirmação nos 32 casos/92 chamadas. Precisão exibida de 51,43% em ambos; fichas secundárias expuseram risco ausente da triagem de ficha indicada |
| Validação | 16 casos/52 chamadas. Precisão selecionada 46,67% no 4B e 36,84% no 8B; congelamento preservou resultado desfavorável, sem quarto ciclo |
| Reservado | 48 casos, três seeds/modelo, 438 chamadas; nenhuma troca de configuração, reparo ou escolha de melhor seed |

R* e a triagem de fichas indicadas eram controles diagnósticos conhecidos. Não foram
apresentados como amostra independente nem como prova de generalização. Thinking,
exemplos contrastivos, modelos maiores, fine-tuning e outras arquiteturas não foram
avaliados; sua ausência impede afirmar que as possibilidades foram esgotadas.

Os controles estruturados, filtro de fichas arquivadas, schema e anexação literal de
verificações pertencem ao código. O salto conjunto da recuperação não permite atribuir
separadamente todo o ganho à vista da nota, aos filtros ou ao embedder. Os resultados
anteriores não foram substituídos pelos números melhores.

## Resultado final e metas congeladas

| Medida | Meta | B1 | 4B | 8B |
| --- | ---: | ---: | ---: | ---: |
| Precisão exibida | ≥90% | 36/45 = 80,00% | 86/174 = 49,43% | 81/149 = 54,36% |
| Cobertura respondível | ≥75% | 31/32 = 96,88% | 81/96 = 84,38% | 72/96 = 75,00% |
| Próxima verificação pertinente¹ | ≥85% | 27/32 = 84,38% | 23/96 = 23,96% | 32/96 = 33,33% |
| Completude do caso | diagnóstico | 38/48 = 79,17% | 50/144 = 34,72% | 68/144 = 47,22% |
| Ganho semântico sobre B1² | ≥10 pp | referência: 14/20 | −16,67 pp | −11,67 pp |
| Variação global de completude | ≥−5 pp | referência | −44,44 pp | −31,94 pp |
| Erros altos expostos | zero | 5 em uma avaliação | 57 nas três seeds | 68 nas três seeds |
| P95 quente do leitor | ≤30 s | sem LLM | 4,47 s | 12,29 s |

¹ Ao menos uma verificação correta e nenhuma orientação indevida na ocorrência;
texto/ID anexado por código, não seleção autônoma de procedimento pelo modelo.
² Completude no subconjunto semântico, conforme operacionalização congelada.

B1 é determinístico, avaliado uma vez; os modelos somam três seeds. Comparar as
frações e os resultados por seed, não as contagens brutas como se tivessem a mesma
quantidade de observações independentes. O controle lexical pareado teve os mesmos
resultados de B1. B2 é recuperação de candidatos, não confirmação de aplicabilidade.

B0 não exibe fichas, tem cobertura específica zero e precisão indefinida. Seus 16/48
casos completos são controles negativos sem orientação, não investigação inteligente.
Abster-se em todos os casos não foi promovido a sucesso.

A busca focada teve Recall@2 de 100% nos três braços, inclusive no subconjunto
semântico. Recall@1 foi 87,50% em BM25/denso e 90,63% no híbrido; MRR 0,9844/1,0.
O ganho híbrido no primeiro resultado é um indício pequeno, de uma ocorrência,
sem selecionar esse braço depois do teste e sem comprovar benefício para o usuário.

Todas as 438 saídas tinham schema válido. Mesmo assim, estados corretos foram
116/219 no 4B e 113/219 no 8B; respostas completas, 101/219 e 107/219.
**Validade estrutural não comprova interpretação factual.**

## Completude por estrato

B1 possui seis casos por estrato; leitores somam 18 slots de seis casos/três seeds.
Completude exige todas as fichas pertinentes, com estado/referências corretos, e
nenhuma orientação extra. São contagens de tarefas, não notas de fluência.

| Estrato | B1 | 4B | 8B |
| --- | ---: | ---: | ---: |
| Cronologia | 6/6 | 0/18 | 0/18 |
| Fatos claros | 4/6 | 3/18 | 3/18 |
| Conflitos/multificha | 4/6 | 5/18 | 8/18 |
| Distratores | 4/6 | 3/18 | 9/18 |
| Flags independentes | 5/6 | 6/18 | 12/18 |
| Sem ficha | 6/6 | 18/18 | 18/18 |
| Linguagem semântica | 3/6 | 6/18 | 6/18 |
| Desconhecimento | 6/6 | 9/18 | 12/18 |

Zero de completude em cronologia não significa zero de acertos temporais: a
inclusão de uma ficha secundária indevida também reprova o conjunto inteiro.
O catálogo permite separar essas falhas dos erros de datas.

O estrato “linguagem semântica” tem seis instâncias. Ele não é sinônimo do subconjunto
semântico pré-marcado de 20, que também inclui conflitos e distrações. A tabela e
a diferença principal usam esses recortes explicitamente, sem escolher o melhor.
A ficha vizinha K09, sobre carregamento, não tem caso final em escopo; sua capacidade
não pode ser generalizada a partir do reservado desta rodada.

## Incerteza sem inflar a amostra

A auditoria usa 10.000 reamostragens pareadas por `group_id`, seed de análise 183006,
intervalos percentis 2,5–97,5%. Cada seleção retém as duas variantes, todas as seeds
e todos os itens; grupos sorteados mais de uma vez mantêm multiplicidade. A unidade
é o grupo, como exige a estrutura correlacionada, em vez de sortear registros
isolados. [Referência primária sobre reamostragem de painéis](https://www.stata.com/support/faqs/statistics/bootstrap-with-panel-data/).

O desenho estatístico foi registrado na auditoria **depois de os resultados da campanha
serem conhecidos**; não é nova pré-inscrição. Não houve seleção de parâmetros por
intervalo. O baseline é repetido apenas para alinhar o peso de cada caso/seed na
comparação pareada; isso não cria observações novas.

| Métrica | B1: ponto [faixa 95%] | 4B: ponto [faixa 95%] | 8B: ponto [faixa 95%] |
| --- | --- | --- | --- |
| Precisão | 80,00 [68,18; 90,70]% | 49,43 [40,40; 57,58]% | 54,36 [41,80; 66,91]% |
| Completude | 79,17 [64,58; 91,67]% | 34,72 [20,14; 50,00]% | 47,22 [30,56; 63,89]% |

Diferença pareada de completude contra B1: 4B −44,44 pp [−62,50; −25,69];
8B −31,94 pp [−52,08; −12,50]. A perda global permanece no corpus reamostrado.

No subconjunto de dez grupos semânticos, a diferença é mais incerta: 4B −16,67 pp
[−40,00; +3,33]; 8B −11,67 pp [−40,00; +15,00]. Não afirmar inferioridade universal
na linguagem natural nem evidência positiva robusta. A seleção continua falhando
nas outras metas, especialmente precisão e exposição de erros altos.

Como diagnóstico binário adicional, grupo inteiramente correto nas duas variantes e
em todas as seeds: B1 16/24, 4B 4/24 e 8B 7/24. Wilson 95%: [46,71; 82,03]%,
[6,68; 35,85]% e [14,91; 49,17]%, respectivamente. Esse diagnóstico mais estrito
não substitui a meta original. [Formulação do intervalo de Wilson — NIST](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).

As faixas descrevem sensibilidade do conjunto fictício sob a hipótese de grupos
reamostrados; não estimam prevalência operacional. Grupos foram construídos, não
amostrados aleatoriamente do uso real. Bootstrap degenerado em uma métrica perfeita
observada não comprova risco zero em casos desconhecidos. Não há avaliação humana
independente nem cobertura universal demonstrada por esses intervalos.

## Erros, guardas e errata documental

O [catálogo de auditoria](evidence/issue-183-audit.json) contém os 230 erros de
resposta completa dos leitores e os dez do controle B1, com caso, seed, ficha,
referência, saída, fatos citados e motivo de bloqueio. Inclui também os desfechos
de todos os casos, preservando omissões e controles negativos. Todos os resultados
brutos e erros das etapas anteriores permanecem nas respectivas evidências.

| Família principal de erro bruto | 4B | 8B |
| --- | ---: | ---: |
| Sustentou ficha fora do assunto/escopo (`not_applicable`) | 53 | 64 |
| Sustentou apesar de contradição (`rejected`) | 3 | 1 |
| Sustentou informação apenas possível | 4 | 15 |
| Outros estados incorretos | 43 | 26 |
| Estado correto, sem referência decisiva suficiente | 15 | 6 |

As famílias são uma classificação primária; flags detalhadas permanecem disponíveis.
Os 60/80 erros altos brutos foram reduzidos a 57/68 exposições. Guardas bloquearam
apenas três/doze, respectivamente. Citar um ID existente com `note` e `any_hold`
não prova que a nota contém a pendência daquela ficha.

Exemplos verificáveis na seed 125:

- E07/K07: nota sobre resultado de ensaio ainda não lançado; ambos sustentam pendência
  administrativa, sem esse indício. K05 era pertinente; a ficha secundária K07 não era.
- E09/K07: nota sobre marcação física apagada; sustentar pendência administrativa
  novamente troca o assunto da evidência. A ficha pertinente era K06.
- O próprio B1 sustenta K07 em E05/E06 por mencionar cadastro, sem pendência;
  em E30, por “cadastro resumido”. Também erra negações/conclusões em E10 e E12.
  Superar o LLM não torna suas regras prontas para uso operacional.

O comportamento é compatível com confundir a hipótese descrita na documentação
com o evento observado e com não preservar negações/indícios. É descrição de saídas,
**não demonstração de um mecanismo interno do modelo**. Prompt, schema, base,
recorte e pesos não foram isolados em todas as combinações. A triagem de ficha indicada
não representou bem o risco de fichas secundárias; a confirmação completa o revelou.

### Errata identificada no bloco 6 — K03

A ficha coloca `long_hold=false` na descrição de `rejected`, dizendo que está fora
do escopo, e também em `not_applicable`. O gabarito congelado escolhe `not_applicable`.
Isso torna indevida uma conclusão forte de falha do leitor somente por responder
`rejected` nesse ponto.

Oito chamadas de calibração D18/K03 foram afetadas: dois modelos × dois perfis ×
duas seeds. Sensibilidade tratando os dois negativos como equivalentes: estado
correto passa de 14/16 a 16/16 em cada perfil/modelo; completa bruta, de 8/16 a
10/16. O empate de qualidade dos perfis permanece. Guardas e scores originais foram
preservados; não se trata de novo gabarito ou medição limpa corrigida.

**Zero chamada final contém K03 com `long_hold=false`.** A ambiguidade não altera
precisão/cobertura das orientações finais e não explica as 57/68 exposições. A base
não foi reescrita para anunciar um resultado melhor. Antes de reutilizá-la em outro
experimento, a ambiguidade precisaria de revisão versionada e de novos casos de teste.

## Integridade, execução e limites

A [auditoria reproduzível](../scripts/audit_ai_knowledge.py) não chama modelos nem
altera fontes congeladas. Conferiu:

- Corpus, concordância de 576 rótulos estruturados com as regras codificadas,
  splits e ausência de grupos cruzados.
- 56 comparações de hashes históricos, reconstruídos inclusive após squash sem
  depender dos objetos Git intermediários; 278 pedidos históricos e 438 finais.
- Todos os 734 registros brutos locais e os 438 hashes da conclusão final.
- Cache dos 134 textos comparado às respostas originais de embeddings; rankings
  dos 48 casos recalculados, com os mesmos candidatos enviados aos leitores.
- Recontagem inteira de casos/itens/verificações e pooling, por implementação
  separada do agregador original. Os predicados do leitor foram recalculados com o
  código congelado; isso é consistência, não julgamento semântico independente.
- Ledger único sem duplicidade; prefixo anterior preservado; 716 chamadas,
  134 textos e 2.394,89 s ativos (39,91 min), incluindo carga e embeddings.

No reservado houve zero timeout, truncamento, retry ou parada de recursos. No
desenvolvimento, duas paradas por swap foram preservadas e reconciliadas antes de
retomar apenas pendentes. Picos RSS/VRAM são amostrados, do runtime/GPU total,
sem atribuição causal por modelo. O 8B usa CPU/GPU conjuntamente.

O P95 quente mede leitor com contexto/embeddings preparados, não troca fria
interativa entre embedder e LLM nem jornada autenticada no sistema. Não houve
medição de tempo economizado, compreensão humana, produtividade ou qualidade em
operação. As metas não são SLA.

Congelamento e fingerprints são verificáveis. Não constituem prova externa de
cegamento: o mesmo assistente escreveu fichas, gabaritos e avaliação, e o corpus
está no repositório. Dados oficiais validados não eram pré-requisito desta PoC;
seu uso fictício foi autorizado e sua validade é limitada ao experimento.

A [comparação sem identificação](ai-knowledge-poc-comparison-blind.html) oculta os
nomes, as políticas, notas de avaliação e respostas brutas, e embaralha seis famílias
de painéis por caso com seed 183007. Mantém o pareamento entre seeds; o
[mapeamento separado](ai-knowledge-poc-comparison-blind.mapping.json) permite conferir
as identidades. Avaliação humana é opcional e **não foi realizada**; diferenças
funcionais intrínsecas ainda podem permitir inferir a origem de uma apresentação.
O [comparador original](ai-knowledge-poc-comparison.html) permanece inalterado.

## Recomendação e encerramento

Encerrar **esta configuração de orientador com RAG como não aprovada para integração**.
A estrutura de conhecimento e a instrumentação são reaproveitáveis, mas não converter
o resultado do controle em argumento para adicionar uma camada de LLM decorativa.
A geração não foi testada porque a seleção não merecia apresentação ampliada.

Não há fundamento nesta campanha para ampliar hardware, instalar LLM maior ou
iniciar uma pipeline operacional como solução automática. Há limites de dados,
documentação e interpretação; o funcionamento técnico não resolve o objetivo de
valor ao usuário. Também não há fundamento para descartar toda aplicação de IA.

Se o projeto decidir investigar outra hipótese, ela deve demonstrar contribuição
adicional sobre o controle com dados que possam existir no fluxo escolhido. O risco
principal a testar é aceitar uma ficha irrelevante como sustentada. Contrastes explícitos
entre ficha pertinente/impertinente e o pequeno indício de ordenação híbrida são
perguntas delimitadas possíveis, não melhorias comprovadas. Nenhum novo ciclo ou
implementação está autorizado por este encerramento; os reservados atuais passam
a ser casos conhecidos.

A investigação técnica da #183 está concluída, com resultado negativo para a arquitetura
avaliada e geração inconclusiva. Publicação da branch, PR, CI remota e merge continuam
como etapas de versionamento. Não fechar a issue manualmente como se a integração
houvesse sido aprovada.

## Verificação, reprodução e composição da branch

Resultados locais desta entrega:

- 176 testes de backend/PoC/auditoria aprovados, incluindo 83 da PoC.
- 11 testes ChromeHeadless do componente Agente de qualidade aprovados.
- Comparador sem identificação: 144 combinações, seis painéis, controle móvel
  de 390 px, zero erro de página e zero requisição externa observada.
- Build Angular aprovado; avisos de orçamento CSS em componentes fora desta alteração.
- 187 ativos sintéticos validados; Ruff lint/formato, compilação e diff conferidos.
- Aviso de depreciação httpx/Starlette na regressão existente; sem alteração de dependência.
- Nenhuma inferência nova no bloco 6. Ledger e arquivos congelados preservados;
  runtime vazio; dados reais continuam ignorados e fora das evidências.

O commit `4ed8f9b` consolida, por autorização explícita, alterações locais anteriores
de apresentação/nome do agente e documentação. Foi preservado como um único commit
e será publicado junto à issue. A partir dele, os blocos da #183 não modificam
`backend/app`, `web/src`, `web/e2e` ou migrations. A diferença total da branch ainda
inclui aquelas mudanças anteriores; não confundir isso com integração desta PoC.

Os checkpoints [1–2](ai-knowledge-poc-checkpoint-1-2.md),
[3–4](ai-knowledge-poc-checkpoint-3-4.md) e [5](ai-knowledge-poc-checkpoint-5.md),
a [rubrica](ai-knowledge-poc-rubric.json), o
[desenho da auditoria](ai-knowledge-poc-audit-design.json) e as evidências
[1–2](evidence/issue-183-blocks-1-2.json), [3–4](evidence/issue-183-blocks-3-4.json),
[5](evidence/issue-183-block5.json) e [6](evidence/issue-183-audit.json) permitem
conferir a evolução. A evidência antiga de cada checkpoint continua histórica;
seus campos de autorização/pendência não foram retroativamente reescritos.

Recalcular a auditoria sem Ollama e sem sobrescrever evidências:

```bash
backend/.venv/bin/python scripts/audit_ai_knowledge.py --output /tmp/synergia-183-audit.json
backend/.venv/bin/python -m pytest -c backend/pytest.ini backend/tests/test_ai_knowledge_audit.py -q
```

Use destino novo se esse arquivo já existir. Sem a pasta privada da campanha, o
script verifica a evidência pública e marca a ausência dos arquivos brutos locais;
não afirma tê-los conferido. As faixas e contagens públicas são reproduzíveis.
O encerramento não exige credenciais, serviços externos ou validação por especialista.
A regressão seleciona as áreas afetadas; a suíte inteira de frontend e o E2E com a
aplicação autenticada não foram repetidos. A CI remota ainda não executou nesta entrega.

### Texto sugerido para o PR

Título: `test(ai): avaliar orientação investigativa com RAG local`

```markdown
## Issue relacionada

Closes #183

## O que foi feito

- PoC isolada com base/corpus fictícios, recuperação lexical/densa/híbrida e leitores locais 4B/8B.
- Calibração, três ciclos, validação e campanha reservada de 48 casos/três seeds, com 438 chamadas e protocolo congelado.
- Auditoria, incerteza por grupos, errata K03, comparadores locais e relatório por capacidade.
- Resultado desfavorável à integração dos leitores; redação não executada pelo gate. Agente operacional preservado.
- Inclui o commit único de apresentação/documentação local anterior, autorizado para acompanhar esta issue.

## Como validar

Consultar docs/ai-knowledge-poc-final-report.md, executar a auditoria offline em destino novo e os testes documentados. Abrir os comparadores HTML localmente.

## Evidências

176 testes backend/PoC, 11 testes do componente, comparador em 144 combinações, build Angular e validação de 187 ativos sintéticos. Precisão final: 4B 49,43%, 8B 54,36%, B1 80%. Sem inferência na auditoria, sem integração da nova PoC e sem dados reais versionados.

## Checklist

- [x] Escopo e autorizações preservados; alterações anteriores em commit único.
- [x] Testes, documentação, evidências e análise de resultados desfavoráveis.
- [x] Dados reais, credenciais, pesos e caches fora do Git.
- [ ] CI remota aprovada — aguardar publicação e execução.
```
