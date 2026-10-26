# Exercícios de observabilidade da homologação

## Janela, responsáveis e segurança

Plataforma lidera a janela; backend acompanha aplicação; banco acompanha
PostgreSQL; operações valida a jornada. Use apenas organização, usuário e
arquivo sintéticos. Avise o início e o fim, impeça tráfego externo e mantenha um
rollback definido antes de provocar a falha.

## Roteiro comum

1. Confirmar liveness `200`, readiness `200`, scrape e painel atualizados.
2. Registrar horário, cenário e um correlation ID sintético.
3. Introduzir uma única falha controlada.
4. Confirmar alerta, estado esperado e runbook correto sem abrir o banco.
5. Reverter a falha e confirmar readiness, fila e jornada sintética.
6. Guardar somente estados, tempos, contagens e resultado sanitizados.

## Cenários

### PostgreSQL

Interromper somente a instância descartável. A liveness permanece `200`, a
readiness passa a `503` e identifica `postgresql`. Reativar o serviço e seguir
[`database-unavailable.md`](database-unavailable.md). Não executar restauração
se a retomada simples preservar a integridade.

### Armazenamento

Retirar temporariamente a permissão de escrita do volume descartável ou usar o
teste automatizado com diretório temporário. A readiness passa a `503` e
identifica `storage`. Restaurar a permissão/montagem e seguir
[`storage-unavailable.md`](storage-unavailable.md).

### SMTP e worker

Usar exclusivamente o provider falso ou a conta temporária autorizada. Tornar o
endpoint indisponível, confirmar fila degradada sem perda nem duplicação,
restabelecer o provider e seguir
[`report-notification-recovery.md`](report-notification-recovery.md). Resultado
incerto exige reconciliação; não reenviar manualmente.

## Rollback e interrupção

Interrompa o exercício se houver dado real, perda de correlação, falha fora do
componente escolhido ou suspeita de corrupção. Restaure a configuração anterior,
mantenha mutações suspensas até readiness `200` e preserve somente evidência
sanitizada. Produção não é ambiente de exercício.
