# Assistência — integridade ou acesso cruzado

Alerta `SynergiaAiAssistanceIntegrityViolation` (critical), sem espera: crescimento
nos últimos 5 minutos de falha de integridade persistida, violação de escopo
confirmada internamente ou rejeição de pin no gerador. Não comprova ataque bem
sucedido: os controles recusaram a operação. Um resultado simplesmente ausente
(404) ou uma rejeição isolada de conteúdo inválido não são esses sinais.


## Responsável e escalonamento

Segurança conduz o incidente com backend/plataforma; preservar evidências e escopo autorizado.

## Pré-condições

Ambiente e intervalo identificados, acesso autorizado ao painel/logs/auditoria e
configuração privada sob custódia do operador. Conferir coleta e scrape antes
de interpretar valores. Ações efetivas exigem janela e identidade técnica
autorizadas; não compartilhar credenciais nem usar dados reais em sondas.

## Procedimento

### Investigar e conter

1. Suspender novas gerações em todas as instâncias pelo
   [controle comum](ai-assistance.md#escolher-o-controle). Manter leitura sujeita à
   validação de integridade e contexto: resultados inválidos continuam recusados.
   Se a autorização ou o próprio banco estiverem comprometidos, aplicar também
   o procedimento de incidente da plataforma; este controle não substitui isso.
2. Em **AI security signals**, identificar o canal: `integrity_error`,
   `scope_violation`, persistido ou `runtime_pin_mismatch`. Os canais podem
   registrar o mesmo incidente; o alerta os une, não estima vítimas nem volume
   somando representações. Consultar a auditoria aprovada e logs por correlação.
3. Escopo: conferir organização/permissões no backend e a requisição negada.
   Não compartilhar identificadores de outra organização ou alterar o 404 público.
   Integridade: verificar contrato/hash atual e trilha imutável; não editar JSON
   ou hashes para fazer o resultado passar.
4. Pin: comparar a configuração privada aprovada e a
   [sonda informativa](ai-assistance.md#sonda-informativa), sem alterar automaticamente
   o digest para aceitar o runtime encontrado. Versão/digest anunciados não
   provam a integridade de um host já comprometido. Uma consulta da sonda isolada
   não incrementa a métrica do gerador: seu status deve ser inspecionado.

### Recuperar

Preservar histórico e evidências sanitizadas; investigar causa antes de
reabilitar. Confirmar configuração/runtime aprovados, teste negativo de acesso
cruzado, leitura válida e recusa do resultado adulterado em fixture isolada,
sem usar dados reais. Aplicar a janela/autorização e critérios do runbook comum.

O alerta recupera quando não há novos incidentes na janela de 5 minutos; o
contador acumulado não precisa zerar. Reiniciar a API não apaga o histórico
persistido. Suspender a geração não suprime um incidente real: leituras e
tentativas de acesso continuam relevantes. Flag desligada sem incidente não
gera alerta. Ausência de coleta não é comprovação de ausência de incidentes.

## Rollback

Não aceitar pin encontrado automaticamente nem alterar JSON/hashes. Manter suspensão, preservar trilha e reverter configuração/aplicação somente por revisão aprovada. Ver o
[controle comum](ai-assistance.md) e o [fluxo de rollback](../deployment/update-and-rollback.md).

## Validação e evidências

Confirmar as condições de recuperação descritas acima, coleta saudável e ausência
de nova falha no intervalo. Registrar revisão, horário, código fechado, ação e
correlação; reconciliar eventos na auditoria e, quando habilitado, na pesquisa
Graylog. Publicar somente amostras/capturas sanitizadas, sem conteúdo do modelo,
contexto, configuração privada ou identificadores de negócio. Desaparecimento
do alerta por suspensão ou falta de medição não comprova a correção.
