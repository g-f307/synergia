# Avaliação da PoC operacional — #126 / PR #131

## Protocolo e alcance

A rodada usa os quatro casos sintéticos OP-01–OP-04 e seus gabaritos de resposta
originais. Nenhum dado real é utilizado. O protocolo v3 acrescenta seleção de
ferramentas e explicita a distinção entre contrato JSON e contrato comercial.
É uma nova iteração exploratória sobre casos já conhecidos, não uma nova
avaliação cega. Não se alteram prompt, código ou rótulos durante a medição.
O baseline roda uma vez por caso; o agente, três vezes.
A consistência do baseline é indisponível, pois não há repetição.

O avaliador congela hashes de casos, gabaritos, manifesto, prompt, schemas e
implementações. Registra modelo, parâmetros e, com `--runtime-metadata`, versão
do Ollama e digest do modelo. Cada tentativa é salva imediatamente, inclusive
falhas. Um arquivo de saída existente não é sobrescrito: uma rodada nova exige
outro caminho. Não há fallback oculto nem repetição seletiva até obter sucesso.

## Métricas de qualidade

- Precisão, revocação e F1 comparam somente os achados: ID, severidade, evidências
  e afirmação devem coincidir com o gabarito. São métricas de **correspondência
  estrita**, não uma estimativa automática de fidelidade semântica.
- `finding_field_accuracy` inclui achados ausentes e espúrios no denominador.
- `summary_exact_match` e `next_steps_exact_match` verificam separadamente o
  resumo executivo e os encaminhamentos.
- `field_accuracy` combina os campos dos achados com resumo, encaminhamentos,
  estado e perguntas. `case_exact_match` exige correspondência em todos eles.
  Assim, F1 de achados alto não aprova um resumo falso ou encaminhamento indevido.
- Paráfrases válidas também podem perder pontos na comparação textual estrita.
  Por isso a análise qualitativa abaixo é separada: não chamar toda divergência
  textual de alucinação. A revisão verifica contradição do estado, omissão de
  pendências, aprovação sem evidência e recomendação de ação não autorizada.
- Validade no schema e aceitação pelo contrato são separadas. Uma resposta pode
  ter schema válido e ser rejeitada por evidência inexistente ou falta de abstenção.
- Consistência é a proporção de casos repetidos em que **todas** as respostas são
  aceitas e os hashes de JSON canônico são iguais. Falhas tornam o caso
  inconsistente. Diferenças de texto/listas contam como divergência, mesmo com
  notas iguais; ordem das chaves não conta. Sem duas tentativas, retorna `null`.
  Não é uma medida de correção factual nem equivalência semântica.

## Telemetria e consultas

- Latência inclui inferência e validação; P95 usa nearest-rank.
- Tokens/segundo usa tokens recebidos divididos pelo tempo total da tentativa:
  inclui carga e processamento do prompt, não é velocidade pura de decodificação.
- Tokens e memória conhecidos são preservados se o JSON ou contrato for rejeitado.
  Quando não há contagem recebida, o campo fica `null`, nunca zero inventado.
- `python_peak_memory_bytes` mede apenas alocações rastreadas pelo cliente Python.
- `model_process_rss_peak_bytes` é a soma RSS de Ollama e llama-server,
  amostrada a cada 0,5 s em Linux. Exige runtime dedicado; pode contar páginas
  compartilhadas duas vezes e perder picos entre amostras. Não é VRAM.
- O registro real das consultas inclui nome, argumentos autorizados, resultado,
  quantidade de itens e hash do retorno; negativas não preservam argumentos
  potencialmente sensíveis.
- Na versão v3, o modelo escolhe nome e argumentos de cada consulta por um
  envelope JSON. O programa executa somente consultas permitidas e devolve seus
  resultados ao modelo. Não existe mais pré-carregamento das quatro consultas.
- O limite é de seis tentativas de ferramenta (negadas também contam) e sete
  chamadas ao modelo, permitindo uma resposta final após a sexta consulta.
  Uma sétima solicitação de ferramenta é registrada, mas não executada.
  Nenhuma nova inferência começa após 600 s; uma chamada já iniciada ainda está
  sujeita ao timeout de 300 s. O modelo não pode elevar esses limites.
- `controlled_query_success_rate` mede aceitação pelo registro de consultas;
  **não** mede escolha correta. Uma consulta permitida pode ser desnecessária.
- `agent_tool_choice_accuracy` compara chamadas reais com o gabarito de consultas
  do manifesto 2.1.0: corretas / (tentadas + necessárias ausentes).
  Precisão = corretas/tentadas; recall = necessárias cobertas/necessárias.
  Uma consulta correta precisa ser necessária, bem-sucedida, recuperar todas
  as evidências esperadas daquela ferramenta e não duplicar uma já coberta.
  Negativas, filtros que omitem evidências, duplicatas e consultas desnecessárias
  reduzem a pontuação. Nenhuma chamada quando consultas são necessárias dá zero.
  O baseline não escolhe ferramentas: sua métrica é `null`.
- O gabarito exige `get_execution` em todos os casos; OP-02 também exige
  pendências, classificações e eventos; OP-03 também exige pendências e eventos.
  OP-01/04 têm coleções vazias, confirmadas pelas contagens da execução, dispensando
  consultas adicionais. Esses requisitos foram definidos antes da nova medição
  e nunca são enviados ao modelo. Os rótulos de resposta antigos foram preservados.
- Saída rejeitada não é persistida em texto livre. Apenas hash da resposta,
  causa controlada, validade de schema e telemetria ficam registrados.

## Reprodução

Usar o runtime/modelo local já instalado; os scripts não fazem download.
Iniciar Ollama em loopback, com nuvem desativada e apenas um modelo/requisição:

```bash
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 \
OLLAMA_CONTEXT_LENGTH=4096 OLLAMA_NUM_PARALLEL=1 \
OLLAMA_MAX_LOADED_MODELS=1 ollama serve
```

Em outro terminal, na raiz, com dependências instaladas:

```bash
backend/.venv/bin/python scripts/evaluate_ai_operational.py \
  --mode both --repetitions 3 --runtime-metadata \
  --output /tmp/synergia-operational-tool-loop-restarted-20261006.json
```

Usar outro caminho se esse relatório já existir. Configuração: temperatura 0,
seed 126, contexto 4096, até 2048 tokens, seis threads e timeout de 300 s.
As saídas aceitas constam no relatório para auditoria qualitativa.
O CLI individual cria um diretório UUID por rodada e preserva tentativas falhas.

## Histórico: resultado real com contexto pré-carregado (v2)

Rodada concluída em **06/10/2026**, sem interrupção: quatro tentativas do baseline
e 12 inferências reais do agente. Modelo `qwen2.5:3b-instruct-q4_K_M`, Ollama
0.35.1, digest
`357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`.
Linux, Intel Core i5-1335U, CPU, sem GPU ou nuvem. Modelo já instalado;
nenhum download foi realizado. A licença Qwen Research não é autorização de
implantação produtiva.

Os números desta seção são históricos da versão anterior. Ela não media escolha
de ferramentas pelo agente. A rodada v3, descrita ao fim, mede o novo ciclo;
não misturar as duas rodadas nem atribuir retroativamente tool calling à v2.

| Métrica | Baseline | Agente |
|---|---:|---:|
| Tentativas | 4 | 12 |
| Schema válido / contrato aceito | 100% / 100% | 100% / 100% |
| Precisão / revocação / F1 dos achados, média por tentativa | 75% / 75% / 75% | 50% / 50% / 50% |
| Exatidão dos campos dos achados | 91,67% | 50% |
| Correspondência exata do resumo | 0% | 0% |
| Correspondência exata dos encaminhamentos | 100% | 0% |
| Estado do diagnóstico correto | 100% | 25% |
| Exatidão combinada dos campos | 64,29% | 6,25% |
| Caso inteiro com correspondência exata | 0% | 0% |
| Consistência de conteúdo válido | Não medida (1 repetição) | 0/4 casos — 0% |
| Latência média / P95 | 0,0042 s / 0,0098 s | 42,775 s / 80,746 s |
| Tokens/s médios, tempo total da tentativa | Não se aplica | 4,764 |
| Pico de alocações Python | 13,08 KiB | 117,57 KiB |
| Pico RSS amostrado do runtime/modelo | Não se aplica | 2,232 GiB |
| Consultas controladas bem-sucedidas | Não se aplica | 48/48 — 100% |
| Acerto de escolha de ferramentas pelo modelo | Não se aplica | Não se aplica |

O F1 é uma média por tentativa, não micro-F1. Casos sem achados esperados e sem
achados emitidos recebem 1 nessa métrica; isso explica parte dos 50% do agente,
sem significar resumo correto. O zero de correspondência textual do baseline
também não significa que todos os seus resumos são falsos: ele inclui a contagem
de pendências, enquanto o gabarito usa outra redação.

### Revisão qualitativa e falhas

Foram lidas as oito saídas distintas entre as 12 respostas aceitas. Cada caso
teve duas redações distintas; todas as tentativas continuam contabilizadas.
Esta é uma revisão técnica das respostas, não uma aprovação humana independente.

| Caso | F1 baseline / agente | Observação da revisão técnica |
|---|---:|---|
| OP-01 | 100% / 100% | Achados vazios corretos, mas agente declarou insuficiência indevida apesar da execução concluída. Perguntas sobre um suposto contrato comercial não são sustentadas pela entrada. |
| OP-02 | 100% / 0% | O agente omitiu a pendência dos achados e tratou o estado do diagnóstico como insuficiente. Os encaminhamentos pedem classificar/resolver sem resumir adequadamente a evidência existente. |
| OP-03 | 0% / 0% | O agente reconheceu a falha, mas chamou a execução operacional de investigação e se absteve indevidamente. O ID do achado difere do gold. O baseline usa severidade critical, compatível com a prioridade da entrada, enquanto o gold usa warning. |
| OP-04 | 100% / 100% | Abstenção correta. Uma redação pede evidência adicional; outra interpreta o contrato JSON como contrato operacional, sugerindo perguntas sobre prazos e responsabilidades que não estão na entrada. |

O OP-03 expõe uma limitação do gabarito: sua severidade diverge da regra do
baseline. O resultado foi mantido e explicado, sem alterar o gold depois de
observar o modelo. Qualquer revisão futura exige novo congelamento e nova rodada.
As recomendações do modelo são apenas texto; nenhuma foi executada.

Uma causa provável das perguntas irrelevantes é a interpretação do termo
"contrato de saída" como um contrato de negócio, em vez do schema JSON.
É uma hipótese baseada nas respostas, não uma conclusão sobre o treinamento.
O prompt não foi ajustado usando esses resultados reservados.

### Decisão e distância das metas

**Não promover esta configuração para o produto.** A medição foi concluída e
documenta um resultado negativo: não demonstrou benefício confiável sobre o
baseline. O F1 estrito dos achados ficou 45 pontos percentuais abaixo da meta de
95% do plano da PoC; a consistência exata ficou 95 pontos abaixo de 95%.
Essas métricas são conservadoras e não substituem fidelidade semântica; a revisão
qualitativa também encontrou omissões e encaminhamentos sem sustentação.

A meta de schema 100% foi atingida. Não se declara fidelidade factual de 99%
nem acurácia de escolha de ferramentas: não foram medidas nessa acepção.
O corpus de quatro casos é pequeno e já conhecido no projeto, portanto não
permite generalização estatística. Não há limite de latência/memória homologado
para este hardware. Nenhum resultado negativo foi ocultado.

### Evidências e verificações

Relatório completo, com saídas aceitas, consultas, hashes e parâmetros:
`/tmp/synergia-operational-review-final-20261006.json`.
SHA-256: `bf1d5d61a9610d1caced3b698fa356a46fd9d78a43042f79fc1a3bdbd6930e6d`.
Os dados brutos continuam fora do repositório; `/tmp` é efêmero. Este documento
preserva o resumo sanitizado, o protocolo e a análise.

Validação local após a rodada: **545 testes não integrados aprovados**,
592 desselecionados; Ruff aprovado; 92 arquivos sintéticos validados;
`git diff --check` aprovado. Os testes de regressão incluem resumo falso,
encaminhamento indevido, rodadas inteiramente inválidas, tokens preservados em
rejeições, consultas negadas e relatórios do CLI após falhas. Não houve novo push
nem reexecução remota da CI para estas alterações locais.

## Resultado real com seleção de ferramentas (v3)

Rodada concluída em **06/10/2026**, no mesmo hardware e modelo descritos acima,
com manifesto 2.1.0, prompt v3 e limites de seis consultas e sete inferências.
Foram quatro tentativas do baseline e 12 do agente (três por caso).
Uma execução anterior foi interrompida pelo reinício do ambiente e seus arquivos
temporários não foram recuperados. A rodada reiniciada preserva todas as suas
tentativas, sem repetição seletiva nem ajuste durante a medição.

| Métrica | Baseline | Agente v3 |
|---|---:|---:|
| Tentativas | 4 | 12 |
| Resposta final válida / aceita | 100% / 100% | 0% / 0% |
| F1 dos achados | 75% | 0% |
| Consistência de conteúdo válido | Não medida | 0% |
| Acurácia de escolha de ferramentas | Não se aplica | 15,48% |
| Precisão / recall de ferramentas | Não se aplica | 17,86% / 70,83% |
| Latência média / P95 | 0,0030 s / 0,0047 s | 96,779 s / 140,486 s |
| Tokens/s, tempo total da tentativa | Não se aplica | 2,845 |
| Pico de alocações Python | 12.912 bytes | 210.132 bytes |
| Pico RSS amostrado do runtime/modelo | Não se aplica | 2.460.499.968 bytes |

Todas as 12 tentativas terminaram em `tool_call_limit`: o modelo produziu
envelopes de consultas, mas não uma resposta final. Foram 84 inferências e
84 solicitações de ferramenta: **72 executadas e 12 bloqueadas pelo limite**.
A taxa técnica de consultas aceitas foi 85,71%, distinta da acurácia de escolha.
Houve 15 escolhas corretas, 69 solicitações incorretas e 12 consultas necessárias
ausentes. As métricas da tabela são médias por tentativa, não razões agregadas.
Schema final igual a zero não significa JSON inválido nas interações intermediárias.

### Análise das chamadas

- OP-01: recuperou a execução, mas repetiu consultas desnecessárias sobre coleções
  vazias e usou o ID do caso no filtro de eventos. Não concluiu o resumo.
- OP-02: recuperou execução e pendência; confundiu ID de evidência de pendência
  com `rule_id`, repetindo filtros que não recuperaram classificações nem eventos.
- OP-03: filtrou pendências por prioridade alta, omitindo a pendência crítica;
  repetiu a consulta da execução e atingiu o limite antes de recuperar eventos.
- OP-04: consultou repetidamente coleções vazias em vez de finalizar com abstenção.

Os padrões se repetiram nas três tentativas de cada caso. A repetição de falhas
não conta como consistência útil. Nenhuma ferramenta de escrita foi oferecida
ou executada. O gabarito não foi enviado ao modelo nem alterado após a rodada.

### Decisão e evidência

**Não promover esta configuração para produção.** O ciclo de escolha de ferramentas
e sua medição estão implementados, mas o modelo não concluiu nenhuma investigação.
A acurácia de ferramentas ficou 79,52 pontos percentuais abaixo da meta de 95%.
O resultado negativo não deve ser confundido com ausência de implementação ou
substituído pela taxa de sucesso técnico das consultas. Uma nova iteração exige
novo protocolo; estes quatro casos já conhecidos não constituem avaliação cega.

Relatório completo mantido fora do repositório:
`/tmp/synergia-operational-tool-loop-restarted-20261006.json`.
SHA-256: `6c9dbffc37b2f626a78192f00b7d7a3eb8861e78b3e560d9e07c6c0830c37ac4`.
O diretório `/tmp` é efêmero; este documento preserva o resultado sanitizado.

Validação local: **561 testes não integrados aprovados**, 592 desselecionados;
Ruff aprovado; 92 arquivos sintéticos validados. A cobertura inclui escolhas
corretas, argumentos inválidos, ferramentas desconhecidas, consultas desnecessárias,
filtros incompletos, evidências não recuperadas e limites de chamadas e tempo.
Testes de integração e CI remota não foram reexecutados nesta rodada.
