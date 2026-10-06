# Avaliação da PoC operacional

O avaliador executa baseline e agente sobre os mesmos quatro casos congelados e
registra uma linha por tentativa. Cada linha contém o hash do caso, validade do
schema, acerto de status, precisão factual, revocação, F1, exatidão de campos,
latência, tokens por segundo, memória e chamadas de ferramenta.

Um finding só é considerado factual quando o identificador, a severidade, a
afirmação e as evidências coincidem com o gabarito. Um identificador correto
com texto ou evidência incorretos é registrado como alucinação ou erro factual.

O P95 usa nearest-rank (`ceil(n * 0.95)`). A consistência compara as pontuações
canônicas das repetições do mesmo caso. Falhas de schema e omissões permanecem
no denominador, sem substituição silenciosa pelo baseline.

Execute a comparação local com um Ollama já instalado e configurado:

```bash
python scripts/evaluate_ai_operational.py \
  --mode both --repetitions 3 \
  --output reports/ai-operational/evaluation.json
```

O agente recebe o `case_id`, o schema completo e apenas os resultados das
ferramentas `get_execution`, `list_pending`, `list_classifications` e
`list_events`. O relatório deve ser sanitizado antes de ser compartilhado.
