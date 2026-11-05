# Casos adversariais da explicação assistida

`adversarial.json` contém quatro fixtures ficcionais de saída do pipeline:
serial ausente na coluna B, duas ocorrências do mesmo código com severidades
diferentes, quantidade inválida sem causa e referência ausente.

Essas fixtures testam a projeção e o validador; não alteram a regra de negócio
que define quando o pipeline deve produzir cada ocorrência. Em particular,
`QE-A01` representa uma ocorrência de serial obrigatório já detectada, sem
tornar o serial obrigatório para todas as fontes da aplicação.

Não contêm dados do cliente ou identificadores pessoais. São casos adversariais
conhecidos, sem revisão humana independente ou alegação de amostra reservada.
O comando de congelamento registra o hash deste arquivo e dos envelopes.
Consulte [o protocolo local](../../../docs/ai-quality-explanation.md).
