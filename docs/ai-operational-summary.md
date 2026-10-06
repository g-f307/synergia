# PoC de investigação e resumo operacional

Esta PoC é local, consultiva e isolada do produto. No protocolo v3, o agente
recebe apenas os identificadores do caso e da execução, além dos contratos das
ferramentas. Ele escolhe consultas somente leitura para execução, pendências,
eventos e classificações e recebe os resultados em um ciclo limitado.
Não há acesso ao banco, escrita, aprovação, reprocessamento ou RPA.

O baseline é determinístico: conta pendências e cria um finding por pendência.
O agente e o baseline usam o mesmo caso do manifesto
`data/synthetic/ai-operational-v2/manifest.json`; o gabarito permanece
independente do prompt. Cada achado precisa citar evidência efetivamente
recuperada por uma ferramenta; adivinhar um ID existente no caso não basta.

As ferramentas rejeitam nomes desconhecidos, parâmetros extras, IDs fora do
caso na consulta de execução e limites acima de 50. O ciclo permite seis
tentativas de ferramenta e sete inferências, incluindo a resposta final.
Tentativas negadas consomem o limite e são registradas. Ausência de evidência exige `insufficient_evidence`
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
latência média/P95, sucesso das consultas e acurácia da escolha de ferramentas
contra o gabarito versionado no manifesto. Consultas incorretas, desnecessárias,
repetidas ou ausentes penalizam a métrica. O modo `both` adiciona
repetições do runtime local e preserva omissões, alucinações e falhas no
denominador.

Consulte [protocolo e avaliação real](ai-operational-evaluation.md) para a
separação entre F1 dos achados, resumo e encaminhamentos, métricas de memória,
registro das falhas e limitações. Correspondência textual com o gabarito não
substitui revisão factual da redação. O agente permanece consultivo.
