# Nota de Release — Assistência Informativa de IA (Contrato 1.0.0)

- **Capacidade:** explicação assistida no detalhe da execução (`/executions/:executionId`).
- **Natureza:** **somente leitura e supervisionada**. Não altera dados de negócio, não executa ferramentas, não toma decisões automáticas e exige conferência humana das evidências referenciadas.
- **Escopo:** restrita ao contexto determinístico persistido de uma única execução terminal, sem RAG, embeddings, busca vetorial, chat ou memória entre execuções.
- **Implantação e configuração:**
  - Desligada por padrão: `SYNERGIA_AI_ASSISTANCE_ENABLED=false`.
  - Kill switch de geração (mantém leitura de resultados persistidos): `SYNERGIA_AI_ASSISTANCE_GENERATION_ENABLED=false`.
  - Modelo e digest fixados: `SYNERGIA_AI_ASSISTANCE_MODEL=qwen3:4b-instruct` e `SYNERGIA_AI_ASSISTANCE_DIGEST=sha256:0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
  - Retenção obrigatória fora de desenvolvimento: `SYNERGIA_AI_ASSISTANCE_RETENTION_DAYS` (1–365, padrão 30; limpeza via `scripts/expire_ai_assistance.py`).
  - Sonda operacional autenticada: `GET /operations/ai-assistance/health` (independente de `/health/ready`).
- **Rollback operacional:** desligar `SYNERGIA_AI_ASSISTANCE_ENABLED=false` (ou `GENERATION_ENABLED=false` para manter leitura); para reversão de schema em cópia descartável, usar `database/rollbacks/0040..0037_*.down.sql`.
- **Retirada experimental:** `/ai/quality` e `/ai/quality/scenarios` das PoCs #179 e #183 foram retirados da aplicação operacional na API `0.14.0` (#192), preservando apenas os scripts offline em `scripts/`.
- **Referências:** [ai-assistance-web.md](../ai-assistance-web.md), [ai-assistance-api.md](../ai-assistance-api.md), [runbooks/ai-assistance.md](../runbooks/ai-assistance.md), [deployment/deployment-guide.md](../deployment/deployment-guide.md) e [deployment/update-and-rollback.md](../deployment/update-and-rollback.md).
