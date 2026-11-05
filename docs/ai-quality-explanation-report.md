# Resultado da PoC de explicação assistida — #179

**Escopo atualizado:** a entrega de interface é a
[área IA — Qualidade integrada ao SYNERGIA](ai-quality-ui.md), com geração real.
Os números abaixo pertencem à rodada offline congelada anterior à integração;
não são métricas de uma nova rodada sobre o código atual. As verificações da
interface estão em `integrated-browser-checks.json`. Vídeo não integra a entrega.

Rodada local de 05/11/2026, em Manaus (UTC−4). Apenas dados sintéticos.
O protocolo, o contrato e os comandos de reprodução estão em
[ai-quality-explanation.md](ai-quality-explanation.md).

## Decisão

A separação entre fatos determinísticos e linguagem controlada resolve os
defeitos de agrupamento e impede que texto aceito transforme uma posição em
valor ou acrescente causa/intenção. Isso demonstra o funcionamento dos limites
implementados. **Não autoriza integração ao produto nem comprova vantagem do
modelo sobre templates.** A utilidade e a facilidade de compreensão ainda
precisam de avaliação humana independente.

## Desenho da rodada

- Regressão conhecida: 24 arquivos dos 12 cenários da #148, CSV e XLSX pareados.
- Adversariais adicionais: quatro fixtures de saída do pipeline; serial
  ausente, duas ocorrências com severidades diferentes, quantidade inválida
  sem causa e referência ausente.
- Três repetições, sem aquecimento excluído ou retry: 84 tentativas por braço.ja f
- Uma geração por grupo: 96 explicações planejadas para o candidato; casos
  vazios são registrados sem chamada ao modelo.
- Qwen3 4B Instruct Q4_K_M, Ollama 0.40.12, digest idêntico ao da #148.
  Nome instalado abreviado registrado no manifesto. Temperatura zero,
  seed 125, seis threads, contexto 4096 e máximo 2048 tokens, sem thinking.
- Nenhum ajuste de prompt, schema, casos ou parâmetros após observar saídas.
  O congelamento foi gravado antes da primeira inferência. O HTML teve somente
  um ajuste posterior de largura do seletor, encontrado no teste móvel; a
  versão anterior está preservada e sua integridade é conferida separadamente.
- Não é nova amostra reservada; não há revisão independente do novo gold nem
  anotação humana de cada afirmação. Não extrapolar para qualidade produtiva.

## Resultados completos

| Medida | Baseline | Candidato com fallback |
| --- | --- | --- |
| Tentativas de caso completas | 84 | 84 |
| Casos vazios, sem geração | 12 | 12 |
| Explicações por grupo | 96 determinísticas | 96/96 aceitas do modelo |
| Ocorrências preservadas | 105/105 | 105/105 |
| Diagnósticos duplicados | 0 | 0 |
| Grupos aceitos fora das frases permitidas | 0 | 0 |
| Recusas naturais / fallback | Não aplicável | 0 / 0 |
| Latência média por caso | 0,007 ms | 9.503,083 ms |
| P95 por caso | 0,016 ms | 19.440,250 ms |
| Pico de alocação Python no trecho instrumentado | Não comparável; ver limitação abaixo | 997.683 bytes |

Todas as 96 explicações do candidato são textualmente iguais à explicação do
baseline. Nas 96, o modelo escolheu mais verificações humanas que o baseline.
Isso **não demonstra melhora de compreensão**: pode apenas aumentar a leitura.
O custo adicional de geração é observado, e o benefício ainda não foi medido.
Sem ganho demonstrado, não há recomendação técnica de substituir os templates.

A telemetria coletou 1.377 amostras: pico de RSS somado de 5.572.804.608 bytes,
pico de VRAM total de 2.452.619.264 bytes, swap observado zero e nenhuma falha de
recurso. Esses picos abrangem a rodada intercalada, com o modelo residente;
não são memória atribuída separadamente a cada braço. RSS pode contar páginas
compartilhadas; VRAM inclui outros processos.

**Limitação da instrumentação Python:** a montagem do baseline e a cópia dos
fatos acontecem antes de iniciar `tracemalloc`. O zero registrado para o braço
determinístico significa que não houve alocação rastreada no trecho seguinte,
e não consumo zero de memória. Não comparar esse zero ao pico do candidato.
A memória do runtime é a medida observada de processo/GPU acima.

Ambiente desta rodada: WSL2/Linux, Python 3.12.15, Intel i5-11300H,
12.429.488.128 bytes de RAM visíveis ao WSL e GTX 1650 de 4 GiB. Os pesos,
Ollama e parâmetros foram preservados; o hardware difere da máquina do
relatório #148. As latências não são comparação causal com a rodada histórica
nem benchmark de capacidade: houve tarefas locais de desenvolvimento durante
a execução e não foi isolado o custo de carga/cache.

Hash do manifesto pré-execução:
`c7df610c895b5985ce6b36f7e1c6dac777c23dca727f4b47bf53bed27994cc67`.

## O que os resultados demonstram

Os seis casos históricos de duplicidade (`QD3-E06`, dois formatos e três
repetições) mantêm um único diagnóstico. O caso adversarial com duas
ocorrências mantém ambas, inclusive a diferença de severidade. A cobertura é
calculada sobre as referências preservadas, e não sobre texto gerado.

Os casos com valor ausente declaram explicitamente que ele não pode ser
determinado. Toda explicação inclui a limitação causal. O modelo não pode
retornar código, categoria, severidade ou localização; esses campos são
reapresentados exclusivamente a partir do envelope.

“Nenhum grupo fora das frases permitidas” mede conformidade com a política
fechada, não precisão semântica generalizável de prosa livre. Frases fora dessa
política são recusadas mesmo quando poderiam ser paráfrases corretas. O custo
desse controle é uma contribuição textual bastante limitada do modelo.

Recusas naturais e falhas reais da rodada permanecem nos resultados. Os
controles de serial inventado/intenção, timeout e indisponibilidade do
demonstrador são simulações sintéticas identificadas, não resultados obtidos
do Qwen. Os testes automatizados verificam fallback com uma única tentativa e
ausência de texto recusado nos artefatos.

## Artefatos e integridade

- [Manifesto congelado](evidence/issue-179-quality-explanation/manifest.json):
  hashes de código, prompt, schemas, casos, configuração e envelopes.
- [Resultados completos](evidence/issue-179-quality-explanation/results.json):
  todas as tentativas, textos aceitos, códigos de recusa, hashes, latências e
  memória, sem persistência de texto livre recusado.
- [Conferência de integridade](evidence/issue-179-quality-explanation/integrity-review.json):
  comparação dos hashes e das métricas, seis regressões de duplicidade e
  identificação do único ajuste posterior de apresentação.
- [Ambiente sanitizado](evidence/issue-179-quality-explanation/environment.json):
  sistema, Python, CPU, RAM e GPU, sem hostname, usuário ou número de série.
- [Demonstrador offline](evidence/issue-179-quality-explanation/demo.html):
  reprodução das três repetições e controles sintéticos separados.
- [Verificações de navegador](evidence/issue-179-quality-explanation/browser-checks.json)
  e capturas sanitizadas no mesmo diretório.

O original de apresentação do congelamento está em
`frozen-demo-template-v1.html`. O ajuste posterior acrescenta somente limites
de largura ao seletor; os arquivos de inferência permanecem idênticos aos
hashes congelados. O demonstrador final é pós-processamento dos resultados
completos, sem nova geração, edição de resposta ou exclusão de tentativa.

## Verificação técnica

Comandos realmente executados com o Python do ambiente local:

```bash
python -m pytest -c backend/pytest.ini \
  backend/tests/test_ai_quality_explanation.py \
  backend/tests/test_ai_poc_evaluation.py \
  backend/tests/test_ai_reevaluation_runner.py \
  backend/tests/test_ai_reevaluation_native.py \
  backend/tests/test_ai_reevaluation_probe.py -q
# 115 aprovados, incluindo os 30 testes novos.

python -m pytest -c backend/pytest.ini \
  backend/tests/test_ai_poc_foundation.py \
  backend/tests/test_ai_quality_diagnosis.py \
  backend/tests/test_ai_quality_metrics.py \
  backend/tests/test_ai_reevaluation_guidance.py \
  backend/tests/test_ai_reevaluation_protocol.py -q
# 148 aprovados.

python -m pytest -c backend/pytest.ini backend/tests/test_project_assets.py -q
# 12 aprovados. Total: 275 testes distintos aprovados.

python -m ruff check --config backend/pyproject.toml \
  scripts/ai_quality_explanation.py scripts/run_ai_quality_explanation.py \
  scripts/render_ai_quality_explanation.py backend/tests/test_ai_quality_explanation.py
python -m ruff format --check \
  scripts/ai_quality_explanation.py scripts/run_ai_quality_explanation.py \
  scripts/render_ai_quality_explanation.py backend/tests/test_ai_quality_explanation.py
git diff --check
```

Lint e formatação aprovados. Os dois schemas também foram verificados pelo
metaschema Draft 2020-12 e os 178 arquivos sintéticos passaram pelo validador
existente, sem executar migrations. O ensaio Playwright cobriu agrupamento,
severidades, ausência de valor, três controles de fallback, temas, teclado,
cenário vazio, console sem erro e ausência de requisições de rede. O primeiro
teste móvel falhou por largura do seletor; passou depois do ajuste CSS.

Na etapa offline inicial não foram executados build Angular, persistência
ou CI remota. A integração posterior acrescentou rotas Angular/API; a
validação atual está registrada abaixo. Banco, migrations e dependências
declaradas permanecem sem alterações. O navegador e os utilitários de vídeo foram instalados
somente no ambiente local de evidências, sem novas dependências da aplicação.

## Validação da integração solicitada

A correção de escopo adiciona a área autenticada `/ai/quality`, geração real
pelo backend e referências visuais dentro do shell. A política textual é
compartilhada entre o módulo da aplicação e o executor offline, sem nova
dependência. O prazo interativo é 30 s por cenário; os 300 s do executor da
rodada histórica não descrevem a interface.

Após a integração foram executados:

- `pytest` nos testes de explicação, API, fundação, diagnóstico, métricas,
  avaliação, runner e protocolo: **236 aprovados**; aviso de depreciação
  preexistente da integração Starlette/httpx no ambiente local.
- `npm test -- --watch=false --browsers=ChromeHeadless`: **345 aprovados**,
  incluindo nove testes novos do componente e serviço.
- `npm run lint` e `npm run build`: aprovados. O build mantém avisos de orçamento
  CSS em componentes preexistentes; a área nova não excede o orçamento.
- Ruff e validadores de i18n, sistema visual e mapa de jornadas: aprovados.
- Ensaio Playwright do shell, API e modelo reais: agrupamento, valor ausente,
  abstenção, temas e viewport 390×844; sem violações Axe graves/críticas na
  área nova. A identidade foi substituída somente no servidor descartável de
  teste, sem acesso a banco real; o produto mantém a autenticação normal.

O primeiro ensaio do teste unitário de desabilitação do select precisou aguardar
a estabilização do `ngModel`; a suíte completa passou após corrigir a espera.
O primeiro ensaio Axe falhou por criação inadequada do contexto no script de
teste; após corrigir o harness, a auditoria passou. Nenhum desses ajustes
desabilita validações da aplicação.

As [capturas da interface integrada](ai-quality-ui.md#padrão-visual-e-referências-para-gravação)
são referências para quem realizará a gravação. Vídeo não integra os artefatos
versionados desta entrega.

Não executados: suíte completa PostgreSQL/E2E com login real e CI remota.
O teste `web/e2e/ai-quality.spec.ts` está preparado para esse ambiente e não
grava vídeo. Permanecem humanos: avaliar utilidade, gravar a apresentação e
decidir se a pesquisa deve avançar para ocorrências operacionais. Não houve
deploy; a publicação e a revisão do código ficam registradas no PR da #179.
