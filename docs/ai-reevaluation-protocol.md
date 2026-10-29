# Protocolo de reavaliação local das PoCs — issue #148

Estado do Bloco 1: **preparado para revisão, sem inferência**. O registro
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

Orçamento inicial proposto, a ser imposto pelo executor do Bloco 2:

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
resultados propostos. Todos começam com `pending_human_review`, sem revisor,
data ou decisão inventados. Os testes verificam somente contratos, bytes,
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
O protocolo ainda é um documento de preparação: o bloqueio executável de
inferência reservada e a coleta de métricas pertencem ao Bloco 2.
