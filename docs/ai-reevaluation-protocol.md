# Protocolo de reavaliação local das PoCs — issue #148

Estado: **calibração encerrada e seleção final congelada**. O registro
legível por máquina é [ai-reevaluation-protocol.json](ai-reevaluation-protocol.json).
As duas decisões permanecem `not_decided`. Este documento não autoriza integração
de IA ao produto e não declara resultados positivos ainda não medidos.

## Dependências e preservação histórica

- #123: propostas, contratos e metas em [ai-poc-proposals.md](ai-poc-proposals.md)
  e [ai-poc-evaluation-plan.md](ai-poc-evaluation-plan.md).
- #124: fundação local, transporte Ollama e validação de schemas.
- #125: diagnóstico de qualidade v2, baseline e avaliador de CSV/XLSX.
- #126: investigação operacional v3, ferramentas de leitura e avaliador.

Os datasets anteriores, schemas publicados, prompts e relatórios são preservados.
Não se altera o gold de OP-03 da rodada antiga para melhorar seus números. A
rubrica prospectiva v3 explicita a severidade e será revisada antes da medição.
Mudanças de prompt, arquitetura, ferramenta ou contrato criam variantes nomeadas
com hashes próprios; nenhuma resposta recusada é substituída pelo baseline.

As rodadas históricas foram feitas em **outro computador**, com Intel i5-1335U,
aproximadamente 7,4 GiB RAM, CPU e Ollama 0.35.1. Os relatórios sanitizados estão
versionados; as evidências brutas não estão nos caminhos temporários indicados
neste computador. A nova máquina tem Ryzen 5 7535HS, cerca de 14,8 GiB de RAM,
RTX 3050 Laptop com **4 GiB de VRAM** e Ollama 0.40.12. Consulte o
[inventário sanitizado](evidence/issue-148-environment.json).

Comparações entre a rodada antiga e a nova identificam conjuntamente mudanças
de máquina/runtime e não provam causalidade exclusiva do hardware. CPU e
aceleração automática podem ser comparadas **nesta mesma máquina**, com a mesma
configuração e digest; isso não equivale a repetir o experimento no notebook antigo.

## Candidatos e recursos

| Configuração | Papel | Estado no inventário do Bloco 1 |
| --- | --- | --- |
| `qwen2.5:3b-instruct-q4_K_M` | Referência histórica, sem elegibilidade automática ao produto | Não instalado; cerca de 1,9 GB de download; Qwen Research License |
| `qwen3:4b`, Q4_K_M | Candidato principal inicial | Instalado, digest e tamanho registrados; capacidade ainda não medida |
| `qwen3:8b`, Q4_K_M | Alternativa maior condicionada aos recursos | Não instalado; cerca de 5,2 GB; exige verificação híbrida |
| `llama3.2:1b`, Q8_0 | Controle pequeno opcional | Instalado; licença e adequação pendentes de revisão específica |

Os Qwen3 publicados estão sob Apache 2.0. Pesos de 2,5 GB ou 5,2 GB **não são
estimativas da memória total de inferência**: contexto, buffers, runtime e uso
da GPU pelo desktop também contam. O 8B não cabe integralmente em 4 GiB VRAM.
O inventário observou aproximadamente 24,5 GiB livres em disco após a limpeza
do usuário; o executor deverá medir novamente antes de cada execução.

Fontes oficiais consultadas em 29/10/2026:
[referência 3B](https://ollama.com/library/qwen2.5:3b-instruct-q4_K_M),
[Qwen3 4B](https://ollama.com/library/qwen3:4b),
[Qwen3 8B](https://ollama.com/library/qwen3:8b),
[contexto e offload](https://docs.ollama.com/context-length),
[controle de thinking](https://docs.ollama.com/capabilities/thinking).

No Bloco 1 não houve download, carregamento ou inferência. A presença de um
modelo na lista não comprova capacidade, licença aprovada para implantação ou
autorização de uso produtivo. Downloads ausentes e probes serão informados no
checkpoint de recursos antes da execução correspondente.

Orçamento experimental verificado pelo executor do Bloco 2:

- um modelo e uma requisição por vez, apenas runtime local, nuvem desabilitada;
- pelo menos 2 GiB de RAM disponível e 8 GiB livres em disco antes da rodada;
- reservar 256 MiB de margem na VRAM e medir uso por processo e dispositivo;
- interromper e registrar limitação de recurso se swap crescer mais de 256 MiB
  sobre o início da rodada, ou se o limite de memória disponível for ultrapassado;
- timeout máximo de 300 s por requisição e prazo absoluto de 600 s por tentativa
  operacional: cada requisição deverá respeitar o tempo restante;
- amostrar RSS e VRAM a cada 0,5 s. Dado indisponível é `null` com motivo, nunca
  zero inventado. RSS somado pode contar páginas compartilhadas mais de uma vez;
- iniciar calibração em contexto 4096, geração 2048 e temperatura zero; aumentar
  contexto ou orçamento exige uma configuração explícita, nunca ajuste silencioso;
- conferir truncamento de contexto e separação CPU/GPU observada, sem presumir
  que o modelo inteiro foi carregado na GPU.

Esses limites são orçamento experimental local, não SLO de produção. Tempo de
carga, aquecimento, tokens/s de geração e tempo total serão reportados separados.
Warmup tem registro próprio e não entra no denominador de qualidade da avaliação.

## Dados e gabaritos prospectivos

Os novos corpora são inteiramente fictícios. "Novos" significa arquivos e casos
prospectivos com identificadores/conteúdos próprios; as categorias de erro podem
se repetir. Isso não torna o corpus uma amostra estatisticamente representativa.
Nenhum rótulo foi produzido pela resposta de um modelo ou pelo baseline.

| Corpus | Desenvolvimento | Avaliação reservada | Contrato reutilizado |
| --- | --- | --- | --- |
| `ai-quality-v3`, 3.0.0 | 4 cenários, 8 arquivos pareados | 12 cenários, 24 arquivos pareados | Qualidade 2.0.0 |
| `ai-operational-v3`, 3.0.0 | 4 casos JSON | 8 casos JSON | Operacional 1.1.0 |

CSV e XLSX são variantes do mesmo cenário, não sujeitos independentes. Os
manifestos registram hashes das entradas e gabaritos. A materialização do corpus
de qualidade reutiliza `materialize(dataset)` de `build_ai_quality_dataset.py`;
não executa inferência nem altera o corpus v2.

O [roteiro de revisão dos gabaritos](ai-reevaluation-gold-review.md) descreve os
resultados propostos. Os registros começaram com `pending_human_review`; em 29/10/2026 o usuário
confirmou “gabarito parece ok”, registrado como `approved_by_user`. Os testes verificam somente contratos, bytes,
contagens, códigos e posições; não substituem essa revisão humana.

Os golds operacionais fornecem redação de referência. A avaliação deverá medir
fatos sustentados, omissões, severidades e evidências, sem exigir igualdade
textual para considerar uma paráfrase correta. As métricas estritas antigas
continuarão identificadas separadamente, para preservar a comparação histórica.

## Fases e congelamento

1. **Preparação:** inventário, protocolo e gabaritos propostos, sem modelo.
2. **Infraestrutura:** executor, manifestos, telemetria e testes simulados.
3. **Calibração:** somente desenvolvimento. Variação de um fator por vez,
   histórico completo de configurações e critérios de seleção registrados.
4. **Congelamento:** após revisão dos gabaritos e calibração, registrar o digest
   dos candidatos selecionados, licença, parâmetros, perfil de processador,
   modo de thinking, prompts, schemas, código, runtime, dados e seus hashes.
5. **Avaliação:** pelo menos três repetições por configuração, inclusive baseline,
   nos mesmos casos. Não alterar parâmetros, labels ou prompts ao observar o
   reservado. Interrupção só permite retomar fingerprints idênticos e manter
   falhas concluídas. Alteração abre um protocolo novo, preservando o anterior.
6. **Decisão:** revisão factual/privacidade, resultados completos e decisão
   independente para cada proposta.

A calibração pode selecionar até dois candidatos finais por PoC, além do
baseline. A referência histórica é reportada separadamente. Uma arquitetura
guiada ou com ferramentas nativas deve aparecer como variante explícita e
continuar medindo as escolhas reais do agente; ações preenchidas por código
não podem ser contabilizadas como escolhas corretas do modelo.

## Métricas e critérios de decisão

Mantêm-se as metas do plano anterior: schema e referências corretas 100%;
F1 e consistência válida pelo menos 95%; precisão factual pelo menos 99%;
cobertura de fatos pelo menos 95%; acurácia de ferramentas pelo menos 95%
quando aplicável. O protocolo exige também aceitação completa das respostas
observadas para propor continuidade sem ressalva de contrato. Não se declara
segurança do texto livre a partir do schema ou de IDs existentes.

Falhas, timeouts, recusas, omissões e referências inexistentes permanecem nas
métricas. Reportar classificação estrutural bruta, aceitação e caso correto de
forma distinta; F1 estrutural alto não compensa resposta rejeitada. Na proposta
operacional, consultas negadas, repetidas, desnecessárias e necessárias ausentes
penalizam o resultado; sucesso técnico de execução não equivale a escolha correta.

A revisão humana deve contar afirmações sustentadas, afirmações sem suporte,
fatos esperados omitidos, hipóteses apresentadas como fatos e instruções de ação
indevidas. Reportar taxas com seus denominadores e o percentual de respostas
efetivamente revisadas. Ausência de afirmações ou de respostas válidas não pode
ser interpretada como 100% de utilidade. O bloco seguinte implementará essa rubrica.

Qualidade exige demonstrar utilidade de explicação/encaminhamento além da
classificação determinística; operacional exige investigação concluída com
evidências e benefício frente ao template. A decisão admite `continue`,
`reformulate` ou `stop`, com justificativa. Metas atingidas no corpus não são
garantia populacional, aprovação corporativa ou autorização de integração.

## Checkpoints e verificação do Bloco 1

O primeiro checkpoint entrega protocolo e gabaritos para revisão, enquanto a
infraestrutura e os experimentos permanecem pendentes. Para verificar a base:

```bash
backend/.venv/bin/python -m pytest -q backend/tests/test_ai_reevaluation_protocol.py backend/tests/test_project_assets.py
backend/.venv/bin/python -c 'from scripts.build_ai_quality_dataset import verify; from pathlib import Path; assert not verify(Path("data/synthetic/ai-quality-v3"))'
```

Não executar o modo de materialização sobre datasets congelados. Não enviar
arquivos de `docs/files/`, dados do cliente ou serviços corporativos a modelos.
O executor do Bloco 2 implementa o bloqueio de avaliação reservada e a coleta
de métricas descritos abaixo. A calibração e a decisão continuam pendentes.

## Executor do Bloco 2

O executor é `scripts/run_ai_reevaluation.py`, separado da aplicação. As quatro
configurações de desenvolvimento em `scripts/ai_reevaluation_configs/` cobrem
baseline e Qwen3 4B, nas duas propostas. Elas são pontos iniciais de calibração,
não candidatos finais aprovados. Cada execução possui um snapshot imutável e
um diretório exclusivo. Use o Python do ambiente do backend na raiz do repositório:

```bash
backend/.venv/bin/python scripts/run_ai_reevaluation.py freeze --config scripts/ai_reevaluation_configs/quality-baseline-development.json --output /tmp/quality-baseline-snapshot.json
backend/.venv/bin/python scripts/run_ai_reevaluation.py run --snapshot /tmp/quality-baseline-snapshot.json --output-dir /tmp/quality-baseline-run
```

O congelamento do agente consulta somente metadados locais, sem geração. Exige
tag, digest, quantização e versão do Ollama correspondentes à configuração:

```bash
backend/.venv/bin/python scripts/run_ai_reevaluation.py freeze --config scripts/ai_reevaluation_configs/quality-qwen3-4b-auto-development.json --output /tmp/quality-agent-snapshot.json
backend/.venv/bin/python scripts/run_ai_reevaluation.py run --snapshot /tmp/quality-agent-snapshot.json --output-dir /tmp/quality-agent-run --allow-inference
backend/.venv/bin/python scripts/run_ai_reevaluation.py compare --runs /tmp/quality-baseline-run/run.json /tmp/quality-agent-run/run.json --output /tmp/quality-comparison.json
```

Para operacional, trocar as configurações pelos arquivos `operational-*` e usar
outros caminhos de evidência. Não substituir artefatos existentes. `run --resume`
retoma somente o mesmo snapshot, plano, código, pacotes, hardware, dados e runtime.
Uma tentativa iniciada e interrompida vira falha `interrupted`, sem repetição.
Falhas concluídas também não são repetidas. Limitações de recursos deixam a
rodada incompleta; a retomada mantém a referência inicial de uso de swap.

O arquivo `run.json` é o diário autoritativo: `failure` no nível da tentativa
prevalece sobre uma saída que passou no contrato, por exemplo se houve estouro
de recurso. Os relatórios por tentativa são auxiliares. Warmup usa o primeiro
caso de desenvolvimento e fica fora do denominador de qualidade. `complete`
significa que todas as tentativas previstas foram registradas, incluindo falhas;
não significa aprovação. Rodadas incompletas mostram denominadores executado
e planejado e não sustentam uma decisão final.

Para liberar o reservado, após a calibração, definir `status: frozen` no protocolo
e incluir em `evaluation.final_configurations` cada objeto com `id` e
`config_sha256` (SHA-256 do JSON canônico calculado por `ai_reevaluation.digest`).
Selecionar os arquivos com `split: evaluation`, incluindo baseline; só então gerar
seus snapshots. A repetição deve corresponder ao protocolo e ser pelo menos três.
Mudar opções, prompt, modelo ou split invalida a seleção. As quatro configurações `*-evaluation.json` selecionadas constam do protocolo
`1.2.0-frozen`; a seleção ocorreu antes da primeira inferência reservada.

O manifesto registra hashes de código, prompts, schemas, datasets e protocolo,
versões dos pacotes usados, hardware sem identificadores pessoais e metadados do
modelo. A comparação recusa casos, repetições, hashes ou ambiente diferentes e
exige baseline. As configurações devem ser preservadas junto às evidências;
para variar um fator, criar outra configuração identificada e novos snapshots.

O runtime deve ser dedicado: uma execução por vez, sem outros clientes gerando
respostas. O executor serializa suas chamadas e recusa outro modelo carregado.
`think` é explícito, a resposta privada de raciocínio não é armazenada, e
`keep_alive` é configurável. Cada chamada registra tokens, duração de carga,
prefill e geração quando disponíveis, término/truncamento; `/api/ps` registra
estado carregado, contexto e alocação VRAM observados. Um warmup não comprova
que a chamada foi fria: conferir `loaded_before` e `load_duration`.

A amostragem mede RSS somado e VRAM total dos dispositivos, que inclui o desktop;
não atribui toda VRAM ao modelo. `/api/ps.size_vram` complementa a atribuição do
Ollama. Ausência de suporte a `nvidia-smi` fica como `null` com motivo. O monitor
verifica RAM, disco, margem GPU e crescimento de swap, interrompendo a sequência
no próximo checkpoint/chamada. **Não mata o processo externo e não é um limite
de memória imposto pelo sistema operacional.** A requisição em andamento fica
limitada pelo timeout e o ciclo operacional respeita o prazo restante. Não usar
um modelo maior antes do probe de capacidade.

O comparativo mostra aceitação, falhas, latência média/P95, cobertura da telemetria,
RAM/VRAM, geração e consistência estrutural. Na qualidade, F1 aceito não dá crédito
a diagnósticos rejeitados; uma tentativa interrompida sem escore torna F1
indisponível e permanece como falha. No operacional, a igualdade textual histórica
é conservadora e **não mede fidelidade semântica**. Fatos, alucinações e utilidade
continuam `pending_human_review`; o executor não emite aprovação automática.


## Seleção final de 29/10/2026

O [checkpoint de calibração](ai-reevaluation-calibration.md) registra os resultados
completos, controles negativos e justificativa das arquiteturas. As configurações
finais são `quality-baseline-evaluation`,
`quality-instruct-evidence-guided-evaluation`, `operational-baseline-evaluation`
e `operational-qwen3-8b-staged-guarded-evaluation`. Cada arquivo encontra-se em
`scripts/ai_reevaluation_configs/`. Executar `freeze` e `run` conforme acima,
em diretórios novos, sem modificar protocolo, dados, scripts ou configurações
entre as rodadas. Os snapshots incorporam o protocolo congelado completo.

Revisão textual: avaliar todas as respostas aceitas e manter falhas no denominador.
Unidades verificáveis são afirmações sobre estado, contagens, valores, posição,
classificação e eventos; hipóteses explicitamente incertas e recomendações humanas
são registradas separadamente e não comprovam causalidade. Referências existentes
não bastam: conferir se sustentam a afirmação. Registrar por tentativa trechos
problemáticos, omissões de fatos esperados, severidade e instruções indevidas.
Revisão feita pelo assistente deve ser identificada como tal; não substitui o
aceite humano de fatos/utilidade. Utilidade adicional ao baseline exige informação
correta de explicação/encaminhamento ou síntese que vá além do template, sem causa
inventada. Metas originais permanecem; métricas não medidas ficam indisponíveis.
