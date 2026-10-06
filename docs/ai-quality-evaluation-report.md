# Avaliação da PoC de diagnóstico — #125

## Protocolo

Revisão humana do gold confirmada pelo usuário responsável em 05/10/2026,
após fiscalização do parecer técnico. Nenhum rótulo foi alterado.
O registro no manifesto mudou exclusivamente para refletir a aprovação,
antes da avaliação reservada. A conferência dos arquivos reais foi executada
separadamente pelo adaptador e seus testes, sem atribuí-la ao revisor humano.

Corpus inteiramente fictício: 16 cenários, cada um em CSV e XLSX. Os quatro
cenários de desenvolvimento permitem ajustes. Os doze reservados não entram no
prompt como exemplos e não orientam ajustes posteriores à medição final.
Pares de formatos são variantes do mesmo cenário, não 24 sujeitos independentes.

Arquivos reais confirmam as ressalvas do parecer: referência divergente em E05,
coluna ausente em E06, referência indisponível em E09, exclusão de instrução livre
em E10, reconhecimento de #REF! nos dois formatos em E11 e falha de leitura em E12.
Esses casos verificam a implementação determinística, não são exemplos do prompt.

O modelo é `qwen2.5:3b-instruct-q4_K_M` (Ollama 0.35.1), digest
`357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`.
Licença Qwen Research, CPU Intel Core i5-1335U, x86_64, Linux, aproximadamente
7,4 GiB RAM e 4 GiB swap. Não houve GPU, nuvem ou dados reais do cliente.

Configuração final: temperatura 0, seed 125, contexto 4096, limite de geração
2048, seis threads, uma requisição por vez e timeout 300 s.
Prompt v2.1, schemas v2 e código identificados em `frozen.json`.
O primeiro teste com 120 s falhou por timeout; essa falha histórica não foi
apagada da análise. O limite de 300 s foi escolhido em desenvolvimento.

## Metodologia das métricas

- Leitura: arquivos decodificados / arquivos tentados. O corpus inclui arquivos
  deliberadamente ilegíveis, portanto menos de 100% não implica defeito do leitor.
- Layout: arquivos lidos sem erro estrutural / arquivos tentados.
- Linhas válidas: linhas não vazias sem erro bloqueante e fora de abas com layout
  inválido / linhas lidas. Advertências não significam rejeição de linha.
- Classificação exata: conjuntos de pares (código, categoria) iguais ao gold /
  todas as tentativas. Respostas sem schema válido nunca recebem acerto,
  inclusive quando o caso esperado não tem ocorrências.
- Precisão, revocação e F1 micro: calculadas sobre pares (código, categoria).
  Categoria errada contribui com FP e FN. Há matriz de confusão, omissões e
  ocorrências espúrias. Casos sem achados também entram na acurácia por caso.
- Validade JSON/schema e aceitação pelo validador são métricas separadas.
  É possível classificar corretamente e ainda citar evidência inexistente.
- Acerto estrutural do caso exige contrato aceito, classificação exata e estado
  esperado. Não significa aprovação integral do texto livre.
- Referência estruturada: ID existente associado ao código correto / referências
  citadas. Cobertura de evidências: pares (código, ID) cobertos / pares esperados.
  As posições vinculadas aos IDs foram verificadas contra o gold na ingestão.
  Essas métricas **não** validam automaticamente números/posições escritos em prosa.
- Abstenção: igualdade de completed/insufficient_evidence com o gold, por tentativa.
- Consistência semântica válida: arquivos com três respostas aceitas e projeções
  estruturais idênticas / arquivos com três repetições. Três erros iguais não
  são considerados consistência válida. Não exige redação textual idêntica.
- Tempo: média e P95 nearest-rank, incluindo tentativas recusadas e timeout.
  O tempo de ingestão fica registrado separadamente; carga/cache do modelo podem
  influenciar a latência. Execução local interativa não é benchmark isolado.
- Memória: pico RSS amostrado a cada 0,5 s, soma de Ollama e llama-server; pode
  contar páginas compartilhadas duas vezes e perder picos entre amostras.
  Alocações Python são reportadas separadamente, incluindo instrumentação.

Baseline e agente recebem o mesmo contexto determinístico, incluindo projeção
restrita dos registros normalizados. Nenhuma resposta é corrigida ou substituída
silenciosamente por regras. O baseline não lê o gold.
Classificações estruturais de respostas rejeitadas podem ser pontuadas, sem
promovê-las a respostas aceitas. Texto livre rejeitado não é persistido.

Valores sem denominador são `null`, não um 100% fictício. Tentativas falhas não
são descartadas. O relatório completo permite comparar métricas brutas com
aceitação real, evitando interpretar F1 alto como segurança ou utilidade comprovada.

## Evidências e reprodução

Comandos em [Roteiro da demonstração](ai-quality-demo.md).
Execuções finais usam os diretórios:

- `/tmp/synergia-quality-final-v2-development`;
- `/tmp/synergia-quality-final-v2-evaluation`.

`frozen.json` contém hashes/configuração; `records.json` reúne todas as
tentativas e escores; `summary.json` reúne agregados. Saídas aceitas estão em
`attempts/<UUID>/output.json`; cada tentativa tem seu `attempt.json`.
O nome do diretório não é uma aprovação de qualidade.

A execução anterior, interrompida durante desenvolvimento para acrescentar a
projeção de registros normalizados, fica fora da rodada final. Não havia começado
a avaliação reservada. Não misturar seus resultados com os da versão final.

A rodada reservada também sofreu interrupção da sessão, com 39 das 72 inferências
concluídas. Foi retomada com `--resume`, sem alterar os componentes congelados e
sem repetir resultados concluídos, inclusive negativos. A inferência interrompida
antes de gerar um registro não é um resultado concluído. O reinício do runtime
introduz uma nova carga/cache frio; a latência deve ser interpretada com essa
limitação, não como benchmark contínuo isolado.

## Desenvolvimento final

Na configuração congelada, D01–D04 foram executados uma vez em cada formato:
o baseline acertou 8/8 casos; o agente produziu 8/8 respostas com schema válido,
mas apenas 1/8 foi aceita e estruturalmente correta. Houve duas rejeições por
evidência sem fundamento, três por pergunta pendente em `completed` e duas por
certeza incompatível com a necessidade de abstenção. F1 micro: 85,71%; latência
média: 51,929 s; P95: 56,831 s. Consistência não é estimada com uma repetição.

Esses resultados são separados da avaliação reservada. Não se escolheu somente
o exemplo bem-sucedido nem se substituiu uma saída do modelo pelo baseline.

## Resultados

Rodada concluída em **05/10/2026**: 24 arquivos reservados, três repetições por
arquivo e por modo, totalizando **72 tentativas do baseline + 72 do agente**.
Não houve timeout nesta rodada final. As falhas semânticas não foram omitidas.

### Ingestão compartilhada

| Métrica | Baseline e agente |
|---|---:|
| Arquivos lidos | 22/24 — 91,67% |
| Layout aderente | 20/24 — 83,33% |
| Linhas válidas | 12/26 — 46,15% |

Os dois arquivos E12 são propositalmente ilegíveis e os dois E06 têm coluna
ausente. O adaptador identificou os códigos e posições esperados nos 24 arquivos.
Essas taxas descrevem o corpus, não falhas inesperadas de ingestão.

### Comparação final

| Métrica | Baseline | Agente |
|---|---:|---:|
| JSON aprovado pelo schema | 72/72 — 100% | 72/72 — 100% |
| Aceitação pelo validador completo | 72/72 — 100% | 32/72 — 44,44% |
| Classificação exata por tentativa | 72/72 — 100% | 43/72 — 59,72% |
| Caso estruturalmente correto | 72/72 — 100% | 22/72 — 30,56% |
| Precisão micro | 100% | 63,54% |
| Revocação micro | 100% | 72,62% |
| F1 micro | 100% | 67,78% |
| TP / FP / FN | 84 / 0 / 0 | 61 / 35 / 23 |
| Estado/abstenção correto | 72/72 — 100% | 62/72 — 86,11% |
| Referências estruturadas corretas | 84/84 — 100% | 77/96 — 80,21% |
| Cobertura das evidências esperadas | 84/84 — 100% | 77/84 — 91,67% |
| Consistência estrutural válida | 24/24 — 100% | 7/24 — 29,17% |
| Latência média | 0,043 s | 55,865 s |
| Latência P95 | 0,069 s | 93,722 s |
| Pico de alocações Python | 56,77 KiB | 164,29 KiB |
| Pico RSS amostrado do runtime/modelo | Não se aplica | 2,165 GiB |

O baseline não usa o processo do modelo. A métrica Python não é RSS total do
baseline: inclui somente alocações rastreadas, não todas as bibliotecas nativas.
Sete arquivos com respostas consistentemente aceitas não significam sete
arquivos consistentemente corretos; a classificação é medida separadamente.

### Resultados por cenário

Cada formato tem três repetições. Colunas de classificação/acerto consideram as
seis tentativas do cenário. O baseline acertou 6/6 em cada uma das linhas.

| Cenário | Aceitas CSV | Aceitas XLSX | Classificação exata | Caso correto |
|---|---:|---:|---:|---:|
| E01 — quantidade zero, válida | 0/3 | 0/3 | 0/6 | 0/6 |
| E02 — quantidade fracionária | 2/3 | 2/3 | 6/6 | 4/6 |
| E03 — data inválida | 3/3 | 2/3 | 6/6 | 5/6 |
| E04 — duplicidade de linha/serial | 3/3 | 3/3 | 0/6 | 0/6 |
| E05 — referência divergente | 0/3 | 2/3 | 6/6 | 2/6 |
| E06 — coluna ausente | 3/3 | 3/3 | 6/6 | 6/6 |
| E07 — combinação de erros | 3/3 | 3/3 | 5/6 | 5/6 |
| E08 — estado/OQC desconhecidos | 0/3 | 0/3 | 6/6 | 0/6 |
| E09 — referência indisponível | 0/3 | 0/3 | 0/6 | 0/6 |
| E10 — instrução em célula excluída | 0/3 | 0/3 | 0/6 | 0/6 |
| E11 — referência quebrada | 3/3 | 0/3 | 2/6 | 0/6 |
| E12 — arquivo ilegível | 0/3 | 0/3 | 6/6 | 0/6 |

### Falhas observadas

- **19 `ungrounded_evidence`:** E01 (6), E09 (6), E10 (6) e E11 (1).
  Em E01/E10 não havia ocorrência a diagnosticar, mas o modelo criou achados.
  E10 verifica a exclusão da instrução do contexto; sua falha não comprova que
  o modelo seguiu uma instrução que não recebeu.
- **15 `unexpected_open_question`:** E02 (2), E03 (1), E05 (4), E11 (2) e E12 (6).
  O estado `completed` veio acompanhado de pergunta pendente. O contrato final
  rejeita essa contradição em vez de remover a pergunta automaticamente.
- **6 `unsupported_certainty`:** todas as tentativas E08. Reconhecer a categoria
  `unknown` não foi suficiente para respeitar a abstenção obrigatória.

Essas são as 40 rejeições do validador. Há ainda dez respostas aceitas com
classificação incorreta (E04: 6; E07: 1; E11: 3), explicando por que 32 aceitas
resultam em apenas 22 casos corretos. A matriz completa fica em `summary.json`.

### Identidade das evidências

SHA-256 dos artefatos finais em `/tmp/synergia-quality-final-v2-evaluation`:

```text
frozen.json  6276cae0777c42a2d01dea243c0194caaa9ccdd88d92332d9a37f3762cfa7a84
records.json d4be5a3510dab5d7c44da4e3556c238e95fb2539d15cca85680e857d851b7c3f
summary.json 865cbf09be5cd2d7b8528bf6893a64fdffe18ca56ce7daef85796aba96e77ca5
```

O congelamento inclui o prompt
`a6ff73eb3d092367df39372ad92807baa2db3924208b9ed75ed65bd8b9f128e1`,
o avaliador `8adca3e4f2cffe6ed17c3bb02cdd48e100af659b77b5d0db5a1ac4dce7c35c93`
e o manifesto `63044be54da253ad5f40aebe7524ace3d43824c3ade9854bbd262de410873ddf`.
Os demais hashes estão em `frozen.json`. Os artefatos brutos não foram adicionados
ao repositório; `/tmp` é efêmero. O corpus, o procedimento e este relatório
sanitizado preservam a reprodução e a conclusão da rodada.

## Interpretação e limites da decisão

### Análise qualitativa de respostas aceitas

Amostragem técnica, não uma taxa de fidelidade factual calculada sobre todo o
corpus. Foram inspecionadas as primeiras respostas aceitas em CSV de E02, E04 e
E07, inclusive exemplos que o contrato aceita mas o gabarito reprova:

- **E02:** identificou quantidade inválida em B2, com categoria `format` e
  recomendação de conferir a célula. A causa apenas reformula a incompatibilidade
  do valor; não demonstrou interpretação causal superior às regras fixas.
- **E04:** classificou duplicidade de linha e serial como `layout`, em vez de
  `consistency`. IDs corretos e JSON válido não impediram a classificação errada.
  A causa atribui a duplicação à leitura, embora o contexto não prove quando ela
  ocorreu. O rótulo `hypothesis` não torna esse texto uma causa confirmada.
- **E07:** na primeira resposta CSV aceita, confundiu campo obrigatório vazio
  com `layout`, apesar de acertar os outros dois problemas. A orientação amplia
  a conferência para todas as linhas, mas a evidência apresentada é da linha 2.
  Isso acrescenta trabalho sem demonstrar benefício frente ao baseline.

A confusão entre estrutura e conteúdo é uma causa provável dos erros de
classificação; a tendência a reformular o próprio achado limita a utilidade das
hipóteses. São interpretações da revisão técnica, não fatos sobre o treinamento
do modelo. Nenhum ajuste foi feito com base nesses casos reservados.

### Limites

As metas de referência permanecem as do
[plano de avaliação](ai-poc-evaluation-plan.md): schema 100%, F1 pelo menos 95%,
referências corretas 100% e consistência pelo menos 95%. Fidelidade factual de
99% e cobertura de fatos de 95% não podem ser declaradas apenas com IDs válidos:
exigem análise de todas as afirmações em texto livre. A medição estrutural desta
rodada não substitui essa avaliação. Uso correto de ferramentas não se aplica:
este agente não dispõe de ferramentas ou ações operacionais.

O corpus cobre uma fonte (N-FP), com poucos cenários sintéticos e formatos
pareados. Não estima desempenho em planilhas reais ou em todas as fontes do
produto. O baseline recebe códigos de validação determinísticos: seu acerto de
classificação mede o mapeamento desses códigos, não descoberta independente de
anomalias. O modelo precisa justificar benefício adicional na interpretação,
sem degradar esses resultados.

A projeção restrita reduz exposição de dados e instruções arbitrárias, mas
também limita a especificidade de causas e recomendações. Confiança qualitativa
não é probabilidade calibrada. Hipóteses, ainda que aceitas pelo contrato,
continuam sujeitas a revisão humana. Não houve alteração automática de dados,
regra OQC, estado operacional ou integração ao produto.

## Decisão final e atendimento da issue

**Não promover esta configuração do agente.** A PoC implementada e avaliada
cumpre o propósito da #125 de medir e documentar o resultado, inclusive negativo;
não demonstrou melhora confiável de interpretação frente ao baseline.
O schema atingiu 100%, mas o F1 ficou **27,22 pontos percentuais** abaixo da meta
de 95%; referências corretas ficaram **19,79 pontos** abaixo de 100%; consistência
ficou **65,83 pontos** abaixo de 95%. Fidelidade factual global não foi homologada.
Não existe meta numérica de latência/memória fixada para este hardware no plano.

Os bloqueios semânticos impediram a emissão de 40 respostas, mas dez diagnósticos
aceitos mecanicamente ainda erraram a classificação. Portanto, esses controles
reduzem riscos e preservam rastreabilidade; não tornam o modelo apto a recomendar
ações autônomas. A recomendação é manter as regras determinísticas como referência
e exigir novo experimento versionado antes de considerar qualquer promoção.
Uma futura iteração deve ajustar apenas o conjunto de desenvolvimento e usar
avaliação reservada nova; não retunar esta rodada para elevar seus números.

Entregas realizadas:

- consumo de registros normalizados restritos e validações reais, sem persistência;
- saída consultiva com classificação, explicação, hipótese, ação de conferência,
  confiança e revisão humana obrigatória;
- corpus fictício revisado, separado em desenvolvimento/avaliação, com CSV/XLSX;
- baseline independente do gold, comparação automatizada e execuções repetidas;
- métricas, falhas, análise qualitativa, limitações e decisão documentadas;
- prompt, schemas, dataset e instruções preparados para versionamento;
- [roteiro reproduzível](ai-quality-demo.md), sem alegar vídeo já gravado.

Validação local final: **516 testes não integrados aprovados**, 592 testes
desselecionados; Ruff aprovado; seis schemas aprovados no AJV strict; manifestos
sintéticos íntegros; `git diff --check` aprovado. Não houve execução de banco,
alteração do produto ou aprovação remota da CI nesta rodada local. Commit, push,
PR e encerramento remoto da issue permanecem etapas do fluxo de entrega.
