# Roteiro reproduzível — PoC de diagnóstico de qualidade (#125)

## Mensagem central

O agente é consultivo. A validação determinística é a autoridade e nenhuma
resposta executa correções, decisões OQC ou transições de estado.
Demonstrar tanto um diagnóstico útil quanto uma resposta rejeitada.
Não apresentar fluência, JSON válido ou aprovação do código como homologação do modelo.

## Preparação

1. Instalar as dependências de desenvolvimento em `backend/.venv`.
2. Usar Ollama 0.35.1 e `qwen2.5:3b-instruct-q4_K_M`; conferir digest no relatório.
   Download requer autorização prévia; o executor não instala nem baixa modelos.
3. Iniciar o runtime restrito ao computador:

```bash
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 \
OLLAMA_CONTEXT_LENGTH=4096 OLLAMA_NUM_PARALLEL=1 \
OLLAMA_MAX_LOADED_MODELS=1 ollama serve
```

Nesta estação, o executável está em `/home/marcelo/.local/bin/ollama`.
Não é um serviço automático do sistema. Use esse caminho se não estiver no PATH.

## Demonstração (5–7 minutos, com resultados longos previamente disponíveis)

1. **Contexto e limites (30 s):** mostrar a separação desenvolvimento/avaliação,
   os schemas v2 e a revisão humana do gabarito.
2. **CSV (1 min):** abrir D02 e apontar a célula de Workorder vazia. Mostrar
   leitura, código `required_field`, linha/coluna e baseline.
3. **XLSX (1 min):** abrir D04, destacar estado não mapeado e explicar por que
   a interpretação exige esclarecimento. Não inferir aprovação operacional.
4. **Agente (1–2 min):** exibir um `attempt.json` e seu `output.json` validado,
   com modelo, hashes, duração, hipótese, evidências e revisão humana obrigatória.
5. **Falha (1 min):** exibir uma tentativa com `ungrounded_evidence` ou
   `unsupported_certainty`; mostrar que não há saída aceita nem fallback oculto.
6. **Comparação (1 min):** apresentar métricas finais do baseline e agente,
   limitações do corpus, decisão e distância das metas. Não esconder rejeições.

Execução pontual, na raiz (CSV e XLSX):

```bash
backend/.venv/bin/python scripts/run_ai_quality.py \
  --input data/synthetic/ai-quality-v2/development/QD2-D02.csv \
  --case-id QD2-D02 --mode both --timeout-seconds 300 \
  --synthetic-only --output-dir /tmp/synergia-demo-csv

backend/.venv/bin/python scripts/run_ai_quality.py \
  --input data/synthetic/ai-quality-v2/development/QD2-D04.xlsx \
  --case-id QD2-D04 --mode both --timeout-seconds 300 \
  --synthetic-only --output-dir /tmp/synergia-demo-xlsx
```

Essas execuções pontuais usam o paralelismo padrão do runtime. A avaliação
formal fixa seis threads, registra todos os parâmetros e mede memória do processo.
Não comparar tempos entre configurações sem explicitar a diferença.

## Reprodução da rodada formal

```bash
backend/.venv/bin/python scripts/build_ai_quality_dataset.py --verify
backend/.venv/bin/python scripts/evaluate_ai_quality.py \
  --split development --repetitions 1 \
  --output-dir /tmp/synergia-quality-final-v2-development
backend/.venv/bin/python scripts/evaluate_ai_quality.py \
  --split evaluation --repetitions 3 \
  --output-dir /tmp/synergia-quality-final-v2-evaluation
```

Cada nova rodada requer diretório vazio. Para retomar a mesma rodada, usar
`--resume` com os mesmos argumentos e versões. `frozen.json` trava prompt,
schemas, código, gold, manifesto, modelo/digest, runtime e parâmetros.
Alteração em componente congelado interrompe a retomada: iniciar uma nova rodada,
sem apagar a anterior. Respostas recusadas contam como tentativas, não são repetidas
até “dar certo”. Artefatos de tentativas ficam em diretórios UUID.

`summary.json` contém métricas agregadas; `records.json` contém resultados
por arquivo/repetição, inclusive falhas. Exit code zero indica que a medição
terminou, **não** que o modelo atingiu metas. Retomadas pulam somente resultados
já registrados; uma tentativa interrompida antes do registro pode deixar
artefato órfão, preservado e não contado como resultado concluído.

O pico de memória do modelo é o máximo observado, a cada 0,5 s, da soma RSS de
Ollama e llama-server. Páginas compartilhadas podem ser contadas duas vezes.
Exige runtime dedicado. Não é VRAM nem substitui a métrica separada de alocações
Python. Latência inclui geração/validação e, quando aplicável, carga/cache do modelo;
ingestão é registrada separadamente. P95 usa nearest-rank e inclui tentativas falhas.

## Limpeza operacional

```bash
ollama stop qwen2.5:3b-instruct-q4_K_M
```

Isso libera o modelo da memória, sem apagar instalação ou pesos.
Evidências em `/tmp` podem desaparecer após reinício; preservar o relatório
sanitizado no repositório e exportar os artefatos necessários antes de gravar o vídeo.
Este roteiro não declara um vídeo gravado; a produção audiovisual pertence à #127.
