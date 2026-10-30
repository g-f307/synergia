# Reavaliação local das PoCs — issue #148


## Resultado executivo

**Decisão técnica: reformular as duas propostas.** A nova máquina executa os
modelos selecionados, inclusive o 8B híbrido, mas a avaliação reservada não
sustenta progressão para integração. A decisão estruturada está em
[ai-reevaluation-decision.json](ai-reevaluation-decision.json). O responsável
aceitou o relatório em 29/10/2026, com a mensagem “O relatorio está ok.”. A
revisão textual foi feita pelo assistente; o aceite abrange o relatório, suas
conclusões e limitações, sem anotação humana independente por afirmação.

O planejamento seguinte pode usar as
[recomendações para o próximo ciclo](ai-reevaluation-next-cycle.md), com prioridade
para qualidade e duas propostas independentes de reformulação.

| Métrica | Qualidade baseline | Qualidade 4B | Operacional baseline | Operacional 8B |
| --- | --- | --- | --- | --- |
| Tentativas medidas | 72 | 72 | 24 | 24 |
| Schema válido | 100% | 100% | 100% | 100% |
| Aceitação pelo contrato | 100% | 91,67% (66/72) | 100% | 100% |
| Caso/status correto | 100% | 91,67% | 87,5% | 87,5% |
| F1 estrutural aceito de códigos/categorias | 1,0 | 0,96296 | não aplicável | não aplicável |
| Acurácia média de ferramentas e parâmetros por tentativa | não aplicável | não aplicável | não aplicável | 83,33% |
| Consistência estrutural de qualidade | 100% | 91,67% | não aplicável | não aplicável |
| Igualdade integral de JSON operacional | não aplicável | não aplicável | 100% | 50% |
| F1 operacional de igualdade com referência | não aplicável | não aplicável | 0,625 | 0,375 |
| Latência média / P95 | 7,483 / 9,929 ms | 9,137 / 14,938 s | 0,201 / 0,358 ms | 29,054 / 39,946 s |
| Pico RSS somado | 22,12 MB | 3,40 GB | 295,40 MB | 6,77 GB |
| Pico total de GPU, incluindo desktop | 67,11 MB | 2,91 GB | 147,85 MB | 2,93 GB |

Todos os 192 registros medidos e quatro aquecimentos estão preservados. Não
houve limite de recurso, timeout ou truncamento na rodada final. As seis recusas
de qualidade permanecem nos denominadores. JSON/schema válido no operacional
não detectou afirmações falsas de ausência de eventos.

Os [registros completos sanitizados](evidence/issue-148-reserved-evaluation.json)
contêm snapshots com hashes de dados/código/prompts/schemas/configurações,
runtime, pacotes, hardware, resultados por tentativa, saídas aceitas, falhas,
referências, consultas, recursos e métricas de geração. Os quatro snapshots
compartilham os mesmos hashes de código/entradas e a comparação verifica os
mesmos casos e repetições por proposta.

Geração medida: 22.707 tokens em 72 chamadas de qualidade, aproximadamente
35,39 tokens/s de geração; 7.141 tokens em 102 chamadas operacionais,
aproximadamente 11,38 tokens/s. Essa taxa soma tokens e duração de avaliação do
runtime, não confunde prefill/carga com geração e não é taxa de requisições.
Aquecimentos partiram sem modelo carregado: qualidade 4,770 s com 2,571 s de
carga; operacional 18,752 s com 3,071 s de carga. Os aquecimentos usaram o
primeiro caso de desenvolvimento, ficaram fora das métricas e não falharam.
Swap global já existia: pico final observado 534,77 MB, sem ultrapassar o
crescimento permitido em cada rodada; não houve alegação de swap absoluto zero.

## Escopo e integridade

A rodada reservada usa o protocolo `1.2.0-frozen`, selecionado antes da primeira
inferência reservada. Implementação e configurações: commit `2366942`. O protocolo
é o plano imutável pré-execução; as decisões e os resultados são registrados
separadamente neste relatório e nas evidências finais. Não alterar o protocolo
para atualizar status após a medição, pois seu hash faz parte dos snapshots.

Foram selecionados um candidato por proposta e o baseline correspondente:

- **Qualidade:** Qwen3 4B Instruct 2507, Q4_K_M, política guiada e projeção de
  evidências v1; prompt `quality-v3.2.txt`, seed 125, `/api/generate`.
- **Operacional:** Qwen3 8B, Q4_K_M, ferramentas nativas, sinal de término,
  uma geração final estruturada e guarda contextual; prompt
  `operational-native-v3.txt`, seed 126, `/api/chat`.
- Contexto 4096, geração máxima 2048, temperatura zero, thinking desativado,
  seis threads e aceleração automática. Modelos Apache-2.0; digests completos
  constam das configurações e dos snapshots.
- Três repetições por configuração, um aquecimento separado em desenvolvimento,
  mesmos casos por proposta: qualidade 24 arquivos pareados de 12 cenários;
  operacional oito cenários. CSV/XLSX não são sujeitos independentes.
- Sem nova calibração, correção de saídas, fallback, retry seletivo, troca de
  modelo ou alteração de gold após observar o reservado. Falhas ficam nos
  denominadores. As configurações de desenvolvimento não executadas não contam
  como experimentos; o controle opcional 1B não foi avaliado.

As variantes históricas e a calibração, inclusive resultados negativos e erros
do executor anteriores à inferência, estão no
[checkpoint 3](evidence/issue-148-checkpoint-3.json) e no
[relatório de calibração](ai-reevaluation-calibration.md). O protocolo registra
até dois candidatos por proposta como máximo, não como obrigação de executar dois.

## Hardware e alcance da comparação

Ryzen 5 7535HS, 12 threads lógicas, aproximadamente 14,8 GiB RAM, RTX 3050 Laptop
com 4 GiB VRAM; Linux, Python 3.12.3 e Ollama 0.40.12. Inventário original em
[issue-148-environment.json](evidence/issue-148-environment.json). O 8B usa CPU/GPU
em conjunto: no probe, aproximadamente 5,99 GB de alocação de modelo e 2,72 GB
na VRAM. Ele cabe na configuração híbrida observada; 4 GiB não garante residência
integral, concorrência ou capacidade produtiva. Preferir 8 GiB para comparações
7B/8B com maior margem.

O notebook original tinha Intel i5-1335U, cerca de 7,4 GiB RAM, CPU e Ollama
0.35.1. Dataset, runtime, prompt e arquitetura também mudaram; não atribuir a
melhora exclusivamente ao hardware. O probe CPU/aceleração do 4B usa o mesmo
caso e os mesmos pesos nesta máquina e confirma capacidade pontual, sem garantir
qualidade. A referência Qwen2.5 3B foi medida nesta máquina somente em
calibração; sua licença não foi aprovada para produto.

## Interpretação das métricas

Schema válido é distinto de aceitação pelo contrato. F1 de qualidade mede códigos
/categorias; consistência de qualidade usa a projeção estrutural aceita e exige
três repetições sem falha. No operacional, F1 de referência exige texto/IDs iguais
ao gold e consistência do executor exige JSON integral igual: são métricas
conservadoras e **não representam fidelidade ou consistência semântica**.

Status e limites de perguntas da qualidade são guiados por política determinística.
No operacional, a guarda só restringe status/perguntas após o modelo consultar
uma execução parcial sem dados adicionais. Esses acertos pertencem ao conjunto
modelo + executor; não são prova de raciocínio independente do modelo.

A revisão textual do assistente identifica afirmações sem suporte, hipóteses e
omissões separadamente. O aceite do relatório foi registrado separadamente. Precisão por afirmação
atômica e utilidade percebida por usuários não são inferidas de schema, referência
existente ou simples ausência de flags. Métricas não medidas ficam `null`.

## Reprodução

Usar checkout do commit `2366942` ou da revisão final com os mesmos hashes,
Python do backend com dependências instaladas, modelos/digests e runtime fixados.
Manter Ollama dedicado, sem outro cliente, download, instalação ou teste durante
inferência. Conferir RAM, disco e GPU antes de iniciar. Os pesos são locais e não
fazem parte do Git. Nenhuma credencial externa é necessária.

Para cada ID abaixo, gerar um snapshot e executar em diretório novo, na ordem:

```text
quality-baseline-evaluation
quality-instruct-evidence-guided-evaluation
operational-baseline-evaluation
operational-qwen3-8b-staged-guarded-evaluation
```

Exemplo de execução do candidato de qualidade na raiz do repositório:

```bash
mkdir -p .test-tmp/issue-148-reproduction
backend/.venv/bin/python scripts/run_ai_reevaluation.py freeze --config scripts/ai_reevaluation_configs/quality-instruct-evidence-guided-evaluation.json --output .test-tmp/issue-148-reproduction/quality-agent-snapshot.json
backend/.venv/bin/python scripts/run_ai_reevaluation.py run --snapshot .test-tmp/issue-148-reproduction/quality-agent-snapshot.json --output-dir .test-tmp/issue-148-reproduction/quality-agent --allow-inference
```

Trocar ID, snapshot e diretório para os outros três arquivos. Baselines dispensam
`--allow-inference`. Antes do baseline e da troca de modelo, descarregar somente
os modelos desta PoC que estiverem carregados, por exemplo:

```bash
curl --fail --silent --show-error http://127.0.0.1:11434/api/generate -H 'Content-Type: application/json' -d '{"model":"qwen3:4b-instruct-2507-q4_K_M","keep_alive":0,"stream":false}'
```

O helper local utilizado na medição automatizou essa mesma sequência e preservou
todos os diários; o CLI versionado permite reproduzi-la sem depender dele.
Comparar baseline e candidato de cada proposta com:

```bash
backend/.venv/bin/python scripts/run_ai_reevaluation.py compare --runs .test-tmp/issue-148-reproduction/quality-baseline/run.json .test-tmp/issue-148-reproduction/quality-agent/run.json --output .test-tmp/issue-148-reproduction/quality-comparison.json
```

Usar caminhos correspondentes para o operacional. `--resume` aceita somente o
mesmo snapshot/ambiente e não repete tentativas concluídas ou interrompidas.
Não reexecutar para selecionar a melhor resposta. O tempo e a prosa podem variar
mesmo com seed e temperatura fixas; o registro completo permite auditar isso.

## Fronteiras

A rodada usa apenas dados sintéticos. `docs/files/` permanece ignorado; não houve
acesso ao banco operacional, serviço corporativo ou integração de IA à aplicação.
As ferramentas disponíveis são leituras de um único caso autorizado. Zero
mutação possível na allowlist não equivale a comprovação universal de segurança
de modelos. Decisões produtivas e aprovações de negócio continuam humanas.

## Revisão de qualidade e decisão técnica

O 4B teve seis recusas `duplicate_diagnosis`: os dois formatos do cenário
QD3-E03, em todas as repetições. Duas ocorrências do mesmo código em linhas/campos
diferentes deveriam formar um diagnóstico com ambas as evidências; o modelo
produziu diagnósticos separados, e o contrato os recusou. As recusas permanecem
na aceitação, no F1 e na consistência, sem reparo de saída.

Foram revisados pelo assistente os **66 textos aceitos**, incluindo comparação
de todas as repetições. No QD3-E06, as seis respostas dizem que o serial é `B`.
A ocorrência fornece `column: B` e informa a posição da primeira duplicação;
**não fornece o valor do serial**. Trata-se de confusão entre metadado de coluna
e valor de célula, apesar de referência/código corretos. Nove respostas também
incluem hipótese ou orientação sobre omissão intencional sem evidência. Uma
hipótese explicitamente incerta não é contada como causa comprovada, mas viola
a instrução de não atribuir intenção e não acrescenta utilidade verificada.

A precisão das referências aceitas é 78/78; a cobertura de ocorrências em saídas
aceitas é 78/90, mantendo as falhas no denominador de cobertura. O baseline cobre
90/90 e copia a razão da ocorrência sem inventar o valor. Isso demonstra por
que referência existente e F1 alto não comprovam fidelidade da prosa.

**Decisão técnica: reformular.** O candidato falha nos portões de aceitação e
consistência, e há afirmações sem suporte. A geração acrescenta explicações e
passos mais específicos em alguns textos, mas não demonstrou benefício confiável
sobre o baseline. Uma eventual nova POC deverá delimitar a função de explicação,
preservar desconhecimento de valores ausentes e validar utilidade com usuários;
não será executada outra calibração dentro desta rodada.

O [registro de revisão textual de qualidade](evidence/issue-148-quality-text-review.json)
identifica cada tentativa e os trechos problemáticos. Precisão por afirmação
atômica permanece não medida; o relatório foi aceito pelo responsável, sem
preenchimento artificial de 100%. Textos recusados não são persistidos; suas falhas, hashes e
projeções seguras permanecem auditáveis, sem crédito de sucesso.


## Revisão operacional e decisão técnica

Foram revisadas as 24 saídas do agente e as 24 do baseline, com as três
repetições, confrontando texto, consultas, entrada e gold. Exemplos relevantes:

- **OP3-E04 e OP3-E07:** `list_events(entity_id="OP3-E04")` e equivalente E07
  usam o ID do caso, enquanto os eventos pertencem a `syn-op3-e04`/`syn-op3-e07`.
  A leitura retorna vazio, e o agente afirma ausência de eventos. As entradas
  registram `validation_started` e `execution_failed`, respectivamente. Esses
  filtros incorretos contam como erro/omissão na métrica de ferramentas.
- **OP3-E08:** o agente lista aprovação e retenção da mesma ordem, mas não
  reconhece o conflito nem solicita sua resolução: retorna `completed`, quando
  o gold prospectivo exige `insufficient_evidence`. Erro nas três repetições;
  a guarda não força status desse caso e não foi ampliada após a medição.
- **OP3-E03:** agrupa a pendência crítica e a alta em um achado `warning`,
  enquanto atribui `critical` à execução. A existência de um achado crítico
  genérico não substitui a severidade fundamentada da pendência crítica.
- **OP3-E06:** há síntese correta da retenção e da pendência crítica, com ambas
  as evidências; duas repetições descrevem melhor o estado que a primeira.
  Esse ganho localizado não compensa os erros dos demais cenários.

A guarda contextual foi aplicada em 3/24 tentativas (OP3-E05), após a consulta
escolhida pelo modelo. Não se atribui esse status ao raciocínio do modelo.
Não houve consultas negadas ou mutações; as ferramentas desta POC são somente
leituras. Isso não comprova segurança universal nem fidelidade dos textos.

Na rubrica de fatos **já existentes no manifesto**, a revisão do assistente
identificou cobertura explícita de **36/54 unidades (66,67%)** no agente e
**45/54 (83,33%)** no baseline. São 18 unidades por repetição; conjunções exigem
ambas as partes. O texto que não informa explicitamente contagem de pendências
ou conflito não recebe crédito por esses fatos. Essa anotação está vinculada
aos hashes das saídas; o responsável aceitou o relatório e suas limitações,
sem anotação humana independente. Essa cobertura não equivale a precisão por
cada afirmação possível. A consistência semântica e o F1 semântico permanecem
indisponíveis, sem converter igualdade literal em aprovação semântica.

O baseline também tem limitações: omite o achado de evento isolado em OP3-E07 e
não reconhece o conflito OP3-E08; seu status acerta 21/24. Ele foi preservado,
sem correções oportunistas para melhorar o comparativo. Os
[registros de revisão operacional](evidence/issue-148-operational-text-review.json)
identificam todas as tentativas, fatos esperados, cobertura e problemas.

**Decisão técnica: reformular.** O 8B é executável nesta máquina e melhorou a
capacidade de concluir consultas frente à POC histórica, mas não demonstrou
investigação confiável nem vantagem global sobre o template. Uma eventual nova
POC deverá prevenir inferências de ausência a partir de filtros incompletos,
preservar conflitos e severidades e comprovar utilidade com usuários. Isso exige
outro ciclo de desenho/avaliação, sem reutilizar o reservado como calibração.

## Diagnóstico por fator

| Fator | Evidência | Alcance da conclusão |
| --- | --- | --- |
| Hardware | 4B e 8B completaram a rodada, sem violação do orçamento; 8B híbrido | capacidade local observada; não há evidência de que falta de memória causou os erros finais |
| Modelo/configuração | repetição de código na qualidade, coluna tratada como valor, omissão de conflito | as configurações congeladas não atingiram as metas; não é rejeição de toda família ou porte |
| Prompt | instrução de agrupar códigos e não atribuir intenção foi descumprida | instrução textual sozinha não garantiu contrato ou fidelidade |
| Arquitetura | ferramentas nativas encerram o ciclo, mas filtros podem omitir eventos; schema permite texto falso | protocolo de ferramentas/saída melhora execução, porém não prova investigação correta |
| Contrato | recusa diagnósticos duplicados, mas valida IDs existentes sem provar a afirmação | contrato protege parte da estrutura; revisão factual continua necessária |
| Amostra | desenvolvimento tinha quatro cenários por proposta; reservado expôs outros modos de falha | resultado positivo de calibração não generalizou; não declarar qualidade populacional |

## Aceite e encerramento do ciclo

A medição e a revisão técnica foram encerradas, com decisão de reformular para
cada proposta. Não há novo experimento em execução nem autorização automática
para ampliar modelos, alterar a amostra ou integrar ao produto. Em 29/10/2026,
o responsável confirmou “O relatorio está ok.”, aceitando as conclusões e
limitações documentadas. Esse aceite não transforma a revisão do assistente em
anotação humana independente nem quantifica as métricas ausentes. O estado
pré-aceite dos registros brutos permanece preservado; o aceite vigente está
na decisão estruturada e nos registros de revisão textual.
CI remota, publicação de branch e PR permanecem para o fluxo autorizado pelo
responsável. Os resultados negativos são entregáveis desta issue e não serão
substituídos por novas tentativas até obter resultado positivo.


## Verificações executadas

- Antes da rodada, a suíte geral da implementação passou com **1.417 testes**,
  672 de integração desmarcados e 15 avisos de depreciação do Starlette. Não
  houve execução de testes de integração contra o banco local da aplicação.
- Depois da medição, a verificação final dos módulos de reavaliação e ativos
  passou com **144 testes** em 6,76 s. Comando:
  `backend/.venv/bin/python -m pytest -q backend/tests/test_ai_reevaluation_protocol.py backend/tests/test_ai_reevaluation_runner.py backend/tests/test_ai_reevaluation_guidance.py backend/tests/test_ai_reevaluation_native.py backend/tests/test_ai_reevaluation_probe.py backend/tests/test_project_assets.py`.
- `backend/.venv/bin/ruff check backend scripts`: aprovado.
- `node web/scripts/validate_ai_poc_schemas.mjs`: oito schemas em AJV estrito
  aprovados; sem alteração de produto Angular.
- `backend/.venv/bin/python -c 'from scripts.validate_project_assets import validate_synthetic_data; validate_synthetic_data()'`:
  175 arquivos sintéticos validados, inclusive hashes dos corpora preservados.
- `backend/.venv/bin/python scripts/security_release.py validate`: aprovado.
- `git diff --check`: aprovado. As verificações finais rodaram após o término
  das inferências, preservando o isolamento da medição.
