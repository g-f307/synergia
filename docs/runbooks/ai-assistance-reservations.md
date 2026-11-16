# Assistência — crescimento de reservas expiradas

Alerta `SynergiaAiAssistanceExpiredReservationsGrowing` (warning): delta positivo
do gauge de reservas expiradas na janela de 10 minutos, ainda com reservas
expiradas, por 2 minutos contínuos. Usa delta de gauge, não increase de counter.
Um estoque estável ou decrescente não representa crescimento. Reservas antigas
sem progresso são acompanhadas também pelo [alerta de paralisação](ai-assistance-stalled.md).

## Diagnosticar

Conferir **AI reservations and provider work**, **AI reservation recovery**,
`collection_success` e os logs de persistência/recuperação. Expiração do lease
não cancela necessariamente a chamada ao provider. Comparar interrupções de
worker, falhas de persistência e manutenção, sem presumir que uma inferência
precisa ser repetida. Réplicas que leem o mesmo banco não são somadas.

## Recuperar

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
