# PoC de investigação e resumo operacional

Esta PoC é local, consultiva e isolada do produto. O agente recebe somente
resultados de ferramentas de leitura allowlisted: execução, pendências e
eventos. Não há acesso ao banco, escrita, aprovação, reprocessamento ou RPA.

O baseline é determinístico: conta pendências e cria um finding por pendência.
O agente e o baseline usam o mesmo caso do manifesto
`data/synthetic/ai-operational-v2/manifest.json`; o gabarito permanece
independente do prompt. Cada conclusão precisa citar uma evidência existente.

As ferramentas rejeitam nomes desconhecidos, parâmetros extras, IDs fora do
caso e limites acima de 50. Ausência de evidência exige `insufficient_evidence`
e pergunta aberta. Saídas são validadas pelo schema v1.1.0 e conteúdo sensível
é rejeitado antes do registro.

Para reproduzir, use `scripts/run_ai_operational.py` com `--mode baseline` ou
`--mode agent`, `--repetitions 3`, um caso do manifesto e uma pasta de saída
nova. O relatório registra hash do caso, modo, modelo, latência e falhas; nunca
grava a resposta bruta inválida.

Para comparar o conjunto completo sem modelo, execute:

```bash
python scripts/evaluate_ai_operational.py --mode baseline --output reports/ai-operational/summary.json
```

O avaliador publica precisão, revocação, F1, validade do schema, consistência,
latência média/P95 e acurácia das chamadas autorizadas. O modo `both` adiciona
repetições do runtime local e preserva omissões, alucinações e falhas no
denominador.
