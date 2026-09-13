# API indisponível ou degradada

## Responsável e escalonamento

Operação de plataforma lidera. Segurança participa diante de bloqueios ou
tráfego anômalo; aplicação participa se dependências estiverem saudáveis.
Incidente crítico sem recuperação em 30 minutos é escalado ao responsável pela
homologação.

## Pré-condições

- ambiente e janela do incidente identificados;
- acesso somente leitura ao Prometheus e aos logs sanitizados;
- correlation IDs, nunca tokens ou corpos, separados para evidência.

## Procedimento

1. Confirmar `up{job="synergia-api"}` e `GET /health/live`.
2. Se viva, consultar `/health/ready` para separar aplicação, banco e storage.
3. Conferir taxa 5xx, latência e última alteração implantada.
4. Isolar instância defeituosa ou reiniciá-la conforme o orquestrador.
5. Acionar o runbook específico da dependência indicada.

## Rollback

Reverter somente a última implantação identificada, preservando banco e
storage. Não limpar filas nem dados. Se a reversão falhar, manter a instância
fora de rotação e escalar.

## Validação e evidências

Exigir scrape `up=1`, liveness `200`, readiness `200` e janela sem novos 5xx.
Registrar horários, versão, ações, responsável e correlation IDs seguros.
