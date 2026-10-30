# Issue #148 — checkpoint 1: protocolo e dados propostos

Data: 29/10/2026. Base: `85a31ba`. Branch: `test/148-local-models-hardware`.

## Entregue

- Protocolo prospectivo em [Markdown](../ai-reevaluation-protocol.md) e
  [JSON](../ai-reevaluation-protocol.json), com critérios de qualidade, recursos,
  candidatos, repetições, fases e condições para a avaliação reservada.
- [Inventário técnico](issue-148-environment.json) da nova máquina, runtime e
  modelos instalados, separado da configuração histórica.
- Qualidade v3: quatro cenários de desenvolvimento e 12 reservados, cada um em
  CSV e XLSX, com anotações e manifesto SHA-256 (34 arquivos no total).
- Operacional v3: quatro casos de desenvolvimento e oito reservados, com
  entradas, golds, fatos essenciais, ferramentas necessárias e hashes
  (25 arquivos no total).
- [Roteiro para revisão humana](../ai-reevaluation-gold-review.md), sem declarar
  aprovação em nome do usuário.
- Despacho do validador de ativos estendido explicitamente ao corpus de
  qualidade v3. Arquivos ilegíveis intencionais só são aceitos quando seus bytes
  correspondem ao manifesto; arquivos extras continuam sujeitos à validação.
- Roadmap e rastreabilidade registram a capacidade como parcial.

## Verificações realizadas

| Comando / verificação | Resultado |
| --- | --- |
| Testes `test_ai_reevaluation_protocol.py` | 48 aprovados |
| Testes de protocolo e ativos | 60 aprovados |
| Testes das oito suítes anteriores de PoC, novo protocolo e ativos | 198 aprovados |
| `python -m pytest -q -m 'not integration' backend/tests` | 1333 aprovados, 672 não selecionados, 15 avisos de depreciação Starlette |
| `ruff check backend scripts` | Aprovado |
| `validate_synthetic_data()` | 175 arquivos sintéticos validados |
| Hashes dos corpora de qualidade v2/v3 e manifesto legado | Íntegros |
| Links locais e JSON dos documentos novos | Válidos |
| `git diff --check` | Aprovado |

Os testes novos verificam códigos/posições da ingestão determinística, contratos,
evidências, contagens e hashes dos golds propostos. Não executam modelo real nem
substituem a revisão humana. Os conjuntos e prompts históricos não foram alterados.

## Estado e pendências

Revisão humana dos dois golds: **pendente**. Calibração e avaliação: **não
iniciadas**. Decisões por proposta: **não tomadas**. Nenhum modelo foi baixado,
carregado ou executado. O inventário consultou apenas metadados do runtime.

O checkpoint entrega a preparação do experimento. O executor comparativo,
instrumentação RAM/VRAM, retomada e bloqueio executável de avaliação reservada
serão entregues no Bloco 2. A presença de campos de orçamento no protocolo
não significa que o executor antigo já os impõe.

Não houve teste de integração PostgreSQL, migração, mudança de API/frontend ou
integração produtiva de IA. Não houve push, PR ou execução remota da CI para
este checkpoint. Os arquivos reais de `docs/files/` permanecem ignorados.
