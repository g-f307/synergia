# Assistência — trabalho sem conclusão

Alerta `SynergiaAiAssistanceStalled` (warning): existem reservas processing,
a mais antiga tem pelo menos 600 segundos e não houve conclusão persistida
(completed/rejected) nos últimos 600 segundos, com geração habilitada. Os dois
relógios já medem dez minutos; não existe outro `for: 10m`. Timestamp zero
significa nenhuma conclusão registrada. Uma conclusão por falha é progresso,
embora possa alimentar o alerta de indisponibilidade.


## Responsável e escalonamento

Operações e backend confirmam encerramento dos workers; DBA se houver falha de persistência.

## Pré-condições

Ambiente e intervalo identificados, acesso autorizado ao painel/logs/auditoria e
configuração privada sob custódia do operador. Conferir coleta e scrape antes
de interpretar valores. Ações efetivas exigem janela e identidade técnica
autorizadas; não compartilhar credenciais nem usar dados reais em sondas.

## Procedimento

### Diagnosticar

1. Conferir **AI reservations and provider work**, **AI completion age** e
   **AI control and collection**. Reservas são leases de exclusão, inclusive as
   expiradas; não há uma fila nova de inferência. In-flight conta chamadas do
   provider e pode continuar positivo depois do timeout HTTP.
2. Confirmar `collection_success=1`. Consultar a auditoria PostgreSQL e os logs
   pela correlação, usando as ferramentas já autorizadas. O catálogo imutável
   registra transições; não inferir atividade de worker apenas por uma linha
   processing antiga. Agregados do mesmo banco são deduplicados por ambiente.
3. Verificar interrupção/reinício, erro de persistência, limite do provider e
   versão/pin pela [sonda sem inferência](ai-assistance.md#sonda-informativa).

### Conter e recuperar

Suspender novas gerações em todas as instâncias e confirmar o encerramento dos
workers antigos. Seguir [recuperação de reservas expiradas](ai-assistance.md#recuperar-reservas-expiradas):
prévia limitada, conferência, depois `--apply`. O comando mantém resultados,
reservas ainda válidas e histórico; não envia outra inferência. Não executar
DELETE manual, reduzir o lease ou repetir o mesmo POST enquanto o anterior
puder estar ativo. UUIDs já recuperados ficam impedidos de concluir.

Com a causa corrigida, confirmar lote/auditoria, ausência de reservas expiradas
sem justificativa, readiness e sonda saudáveis. Reabilitar conforme o procedimento
comum e testar um caso sintético autorizado. Uma conclusão recente, o esvaziamento
das reservas ou a suspensão faz o alerta sair; suspensão isolada não comprova
recuperação. Nova reserva após longo período ocioso tem seus próprios dez minutos
de tolerância. Sem tráfego, sem reservas ou com geração suspensa, não há esse alerta.

## Rollback

Não recriar leases recuperados nem desfazer histórico. A recuperação é auditada; manter suspensão e revisar a causa antes de novas gerações. Ver o
[controle comum](ai-assistance.md) e o [fluxo de rollback](../deployment/update-and-rollback.md).

## Validação e evidências

Confirmar as condições de recuperação descritas acima, coleta saudável e ausência
de nova falha no intervalo. Registrar revisão, horário, código fechado, ação e
correlação; reconciliar eventos na auditoria e, quando habilitado, na pesquisa
Graylog. Publicar somente amostras/capturas sanitizadas, sem conteúdo do modelo,
contexto, configuração privada ou identificadores de negócio. Desaparecimento
do alerta por suspensão ou falta de medição não comprova a correção.
