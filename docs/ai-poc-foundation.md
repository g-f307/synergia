# Fundação local das PoCs de IA

`scripts/ai_poc_foundation.py` é um módulo isolado: não é importado pelo
FastAPI nem pelo Angular. Ele lê CSV/XLSX, valida e normaliza registros,
carrega prompts versionados, chama somente um runtime local configurado e
valida a resposta contra JSON Schema 2020-12.

## Execução

Instale as dependências do backend (`pip install -r backend/requirements-dev.txt`).
O modelo não é baixado automaticamente. Para usar Ollama localmente, inicie-o
manualmente e informe `SYNERGIA_POC_MODEL` (padrão: `qwen2.5:3b-instruct-q4_K_M`).
`SYNERGIA_POC_MODEL_ENDPOINT` só aceita `localhost` ou `127.0.0.1`.

Os resultados são gravados em diretório escolhido pelo operador com um UUID por
execução e um arquivo de métricas separado. Nenhum payload é registrado nas
métricas; apenas hash do contexto, modelo, latência, tokens e memória de pico.

Comando reproduzível (baseline e agente, duas repetições):

```bash
python scripts/run_ai_poc.py \
  --kind quality \
  --input data/synthetic/ai-poc-foundation/sample.csv \
  --prompt scripts/ai_poc_prompts/quality-v1.txt \
  --schema scripts/ai_poc_schemas/quality-output-v1.json \
  --model qwen2.5:3b-instruct-q4_K_M \
  --repetitions 2 \
  --mode both \
  --output-dir reports/ai-poc/run-001
```

O baseline e todas as repetições do agente recebem o mesmo conjunto
normalizado. Cada execução produz um UUID, saída e métricas; o relatório
`run-report.json` identifica o modelo e a quantidade de repetições.
O P95 é calculado somente no resumo de uma série pelo método nearest-rank;
não é atribuído artificialmente a cada execução individual.

## Contrato de entrada

Cada dataset deve conter `record_id`, `status` e `amount`. `status` aceita
`valid`, `warning` ou `error`; `amount` é numérico. Extensões, tamanho,
colunas, tipos e domínio são validados antes da execução. Erros são reportados
como `PoCFoundationError`, sem fallback silencioso.

## Reprodutibilidade

O baseline e o agente devem receber os mesmos registros normalizados e o mesmo
prompt versionado. Execute cada caso em uma pasta nova ou mantenha o UUID
gerado; nunca sobrescreva evidência anterior. Registre manualmente o modelo,
quantização, memória disponível e versão do commit no relatório da execução.
