# Assistência — indisponibilidade e timeout

Alerta `SynergiaAiAssistanceUnavailable` (warning): mais de 20% dos POSTs
atendidos terminam como unavailable/timeout, em janela móvel de 5 minutos,
por 10 minutos contínuos. Os seis resultados HTTP entram no denominador;
denegações e instâncias com geração suspensa não entram. Sem tráfego não há taxa
nem alerta. O limiar é operacional inicial, não um SLO aprovado.


## Responsável e escalonamento

Operações aciona backend; plataforma quando envolver runtime/host/banco.

## Pré-condições

Ambiente e intervalo identificados, acesso autorizado ao painel/logs/auditoria e
configuração privada sob custódia do operador. Conferir coleta e scrape antes
de interpretar valores. Ações efetivas exigem janela e identidade técnica
autorizadas; não compartilhar credenciais nem usar dados reais em sondas.

## Procedimento

### Diagnosticar

1. No painel técnico, comparar **AI request outcomes**, **AI availability**,
   **AI latency p95** e **AI persistence outcomes** no mesmo ambiente/intervalo.
   Não somar conclusões persistidas, inferências e respostas HTTP.
2. Conferir flags e executar a [sonda autenticada](ai-assistance.md#sonda-informativa).
   Ela verifica versão e digest anunciados sem enviar fatos nem gerar texto.
   Conferir a configuração privada com a referência aprovada; não publicar o
   endpoint, nome/digest ou o token em evidências. `busy` não comprova falha do pin.
3. Nos logs estruturados, filtrar correlation ID e eventos de contexto, provider,
   validação e persistência. `unavailable` também pode vir de contexto/banco:
   identificar o código fechado antes de culpar o runtime. Um timeout HTTP pode
   deixar chamada ao provider ativa até o prazo interno; conferir in-flight.
4. Se o backend atende corretamente e a tela falha, conferir capability, sessão
   e status da chamada no navegador; distinguir apresentação de erro do provider.

### Conter e recuperar

Aplicar a [suspensão só da geração](ai-assistance.md#escolher-o-controle) em todas
as instâncias. Manter leitura autorizada e as jornadas principais; `/health/ready`
não depende do modelo. Corrigir configuração/recursos ou a dependência identificada.
Não disparar POSTs sucessivos para testar, nem habilitar proxy/redirect para contornar
o transporte. Se houver reservas presas, seguir o [runbook próprio](ai-assistance-stalled.md).

Reabilitar somente na janela autorizada, com pin e sonda válidos, readiness saudável,
workers antigos encerrados e caso sintético autorizado aprovado. Conferir novas
entregas e logs sem conteúdo. O alerta sai quando a razão volta a ≤20%, o tráfego
cessa na janela ou a geração é suspensa. O desaparecimento ao suspender **não**
comprova correção: registrar causa, ação e resultado do teste antes de reabilitar.

`collection_success=0`, alvo sem scrape ou série ausente significam falta de
medição; investigar também os alertas gerais de API/banco/coleta. Não interpretar
um painel sem dados como disponibilidade de 100%.

## Rollback

Manter geração suspensa durante a reversão da configuração ou aplicação, seguindo o histórico do deploy; leitura continua autorizada. Ver o
[controle comum](ai-assistance.md) e o [fluxo de rollback](../deployment/update-and-rollback.md).

## Validação e evidências

Confirmar as condições de recuperação descritas acima, coleta saudável e ausência
de nova falha no intervalo. Registrar revisão, horário, código fechado, ação e
correlação; reconciliar eventos na auditoria e, quando habilitado, na pesquisa
Graylog. Publicar somente amostras/capturas sanitizadas, sem conteúdo do modelo,
contexto, configuração privada ou identificadores de negócio. Desaparecimento
do alerta por suspensão ou falta de medição não comprova a correção.
