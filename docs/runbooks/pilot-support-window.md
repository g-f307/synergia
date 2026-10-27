# Checklist de suporte da janela do piloto

## Responsável e escalonamento

Operação da janela: plataforma, com apoio do backend, do banco e da
segurança. O PO e o responsável técnico acompanham a janela e decidem
interromper. Suspeita de vazamento, adulteração ou corrupção escala para
segurança de imediato.

## Antes da janela

- [ ] PC-01 a PC-06 de [`stage-6-pilot-decision.json`](../stage-6-pilot-decision.json) estão `ready`.
- [ ] `python scripts/validate_stage6_pilot.py` passa.
- [ ] A execução do validador foi entendida como conferência do registro;
      a autorização da janela e os aceites humanos foram conferidos separadamente.
- [ ] Snapshot de banco e arquivos feito e restauração validada em ambiente vazio
      ([backup e restauração](backup-restore.md)).
- [ ] Login local com data de fim registrada, ou identidade corporativa
      autorizada ([ativação](corporate-identity-activation.md)).
- [ ] `/health/ready`, painel e alertas verificados
      ([observabilidade](homologation-observability.md)).
- [ ] Arquivos autorizados fora do Git, em local controlado.
- [ ] Canal de contato e plantonista nominais definidos.

## Durante a janela

- [ ] Acompanhar o painel técnico: rejeição válida separada de falha sistêmica.
- [ ] Para cada incidente, registrar horário, `correlation_id` e `execution_id`
      (nunca o conteúdo do arquivo).
- [ ] Arquivo recusado: usar [arquivo inválido](invalid-file.md); não
      reprocessar sem entender a causa.
- [ ] Orçamento de memória excedido: [orçamento de memória](ingestion-memory-budget.md).
- [ ] Execução parada: [processamento interrompido](processing-interrupted.md).
- [ ] API ou banco indisponível: [API](api-unavailable.md),
      [banco](database-unavailable.md), [armazenamento](storage-unavailable.md).
- [ ] Contingência de upload: [upload manual](manual-upload-contingency.md).

## Critérios para interromper o piloto

Interromper e acionar o rollback ao ocorrer qualquer um:

- indício de exposição de dado a quem não tem escopo;
- perda ou corrupção de dados;
- falha sistêmica sem diagnóstico no tempo combinado com o PO;
- defeito crítico ou alto sem tratamento acordado.

## Rollback

Seguir [backup e restauração](backup-restore.md). Não aumentar limites nem
reiniciar serviços para "limpar" um sinal sem registro e aprovação. Registrar
o motivo e o estado final em `docs/evidence/` sem dados reais.

## Depois da janela

- [ ] Registrar cenários `passed`/`failed` e evidências sanitizadas.
- [ ] Usar o [modelo de execução](../stage-6-pilot.md#modelo-de-registro-de-execução),
      preenchendo horário, papel responsável e pelo menos um resultado observado;
      revisar a privacidade antes de versionar.
- [ ] Registrar defeitos (severidade, estado, responsável) e limitações
      (responsável e prazo).
- [ ] Registrar a decisão e o motivo; aceites do PO e do técnico no PR.
- [ ] Se SMTP incluído falhou, somente considerar `release_with_limitations`
      com limitação aceita vinculada a S-12, responsável e prazo, além dos
      demais critérios. Falha nos cenários S-01–S-11 impede a liberação.
- [ ] Encerrar ou revogar o login local conforme a regra de fim.
