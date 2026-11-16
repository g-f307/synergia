# Assistência — crescimento de reservas expiradas

Alerta `SynergiaAiAssistanceExpiredReservationsGrowing` (warning): delta positivo
do gauge de reservas expiradas na janela de 10 minutos, ainda com reservas
expiradas, por 2 minutos contínuos. Usa delta de gauge, não increase de counter.
Um estoque estável ou decrescente não representa crescimento. Reservas antigas
sem progresso são acompanhadas também pelo [alerta de paralisação](ai-assistance-stalled.md).


## Responsável e escalonamento

Operações e backend; escalar ao DBA se a recuperação limitada falhar.

## Pré-condições

Ambiente e intervalo identificados, acesso autorizado ao painel/logs/auditoria e
configuração privada sob custódia do operador. Conferir coleta e scrape antes
de interpretar valores. Ações efetivas exigem janela e identidade técnica
autorizadas; não compartilhar credenciais nem usar dados reais em sondas.

## Procedimento

### Diagnosticar

Conferir **AI reservations and provider work**, **AI reservation recovery**,
`collection_success` e os logs de persistência/recuperação. Expiração do lease
não cancela necessariamente a chamada ao provider. Comparar interrupções de
worker, falhas de persistência e manutenção, sem presumir que uma inferência
precisa ser repetida. Réplicas que leem o mesmo banco não são somadas.

### Recuperar

Suspender geração e confirmar workers antigos encerrados. Executar a
[prévia e recuperação limitada](ai-assistance.md#recuperar-reservas-expiradas).
Verificar eventos expired, conclusão do lote e projeção na outbox. Outbox não é
recibo do Graylog; reconciliar entrega pelo fluxo autorizado existente.
Não apagar histórico nem resultados, não reduzir o prazo da reserva e não
disparar retries para liberar exclusão.

O alerta sai ao zerar as expiradas ou quando o crescimento deixa a janela.
Conferir estabilidade posterior, causa corrigida, sonda/readiness e um caso
sintético autorizado antes da reabilitação. A limpeza pode continuar necessária
com geração suspensa, por isso a flag não mascara este alerta: desligá-la,
sozinha, também não o dispara. Se a coleta falhar, recuperar a medição antes de
declarar sucesso. Um estoque estável pode exigir ação mesmo sem este alerta.

## Rollback

Não restaurar UUID de reserva removida ou apagar auditoria. Manter geração suspensa; recuperação não apaga resultados válidos. Ver o
[controle comum](ai-assistance.md) e o [fluxo de rollback](../deployment/update-and-rollback.md).

## Validação e evidências

Confirmar as condições de recuperação descritas acima, coleta saudável e ausência
de nova falha no intervalo. Registrar revisão, horário, código fechado, ação e
correlação; reconciliar eventos na auditoria e, quando habilitado, na pesquisa
Graylog. Publicar somente amostras/capturas sanitizadas, sem conteúdo do modelo,
contexto, configuração privada ou identificadores de negócio. Desaparecimento
do alerta por suspensão ou falta de medição não comprova a correção.
