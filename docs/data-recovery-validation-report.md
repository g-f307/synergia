# Relatório de validação de recuperação

## Escopo

A validação automatizada usa PostgreSQL 16 e dados exclusivamente sintéticos.
Ela cria um banco de origem isolado, aplica as 26 migrations, gera um bundle,
restaura em outro banco vazio e destrói ambos ao final. O bundle e o manifesto
privado permanecem apenas no diretório temporário do runner.

## Cenários comprovados

- snapshot consistente enquanto uma escrita controlada é confirmada depois do
  início do backup;
- preservação de identidade, execução, arquivo aceito, avatar, relatório,
  notificação, aprovação e auditoria;
- conferência do inventário e hash das migrations;
- constraints estrangeiras validadas e contagens iguais ao snapshot;
- hash do snapshot JSON de relatório recalculado;
- arquivo presente aceito e arquivo de quarentena deliberadamente ausente;
- recusa diante de arquivo referenciado ausente ou corrompido;
- recusa diante de dump, arquivo ou manifesto alterado;
- restauração recusada sobre banco ou storage não vazio;
- expurgo da quarentena e do estado transitório de segurança;
- bloqueio e auditoria da tentativa de expurgo de dados protegidos;
- falha de armazenamento seguida de correção e novo backup íntegro;
- health, métricas e alertas de ausência, atraso e falha de recuperação.

## Evidência reproduzível

```bash
python scripts/validate_data_governance.py
pytest -q -m integration backend/tests/test_data_operations_persistence.py
docker run --rm --entrypoint promtool \
  -v "$PWD/observability/prometheus:/etc/prometheus" \
  prom/prometheus:v3.14.0 test rules /etc/prometheus/alerts.test.yml
```

Em execução local controlada, o teste integrado foi aprovado em menos de oito
segundos. Esse valor comprova o mecanismo no ambiente de desenvolvimento, mas
não substitui o RTO proposto de quatro horas nem a baseline da #95.

## Privacidade e limitações

O relatório registra apenas classes de entidade, resultados e duração
aproximada. Não contém conteúdo, nomes de arquivo, usuários, e-mails, caminhos,
hashes completos, DSN ou credenciais. A contratação de armazenamento, a
política jurídica definitiva e disaster recovery geográfico permanecem fora do
escopo.

O teste cruzado exigido pela issue continua explicitamente pendente no
[`registro de execução independente`](evidence/data-recovery-cross-test.md).
