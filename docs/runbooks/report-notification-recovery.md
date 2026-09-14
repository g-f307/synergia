# Recuperação de relatórios, notificações e e-mail

## Responsável e escalonamento

Aplicação lidera relatórios e notificações; plataforma lidera worker/provedor.
Vazamento entre destinatários ou organizações é escalado à segurança.

## Pré-condições

- banco disponível e filas consultadas por métricas agregadas;
- versão, estado e correlation ID identificados;
- nenhuma mensagem real é reenviada no ambiente controlado.

## Procedimento

1. Separar falha de geração, projeção interna e entrega externa.
2. Relatório falho gera uma nova versão; snapshots imutáveis não são editados.
3. Notificação é reconstruída somente pelo evento de origem idempotente.
4. Para e-mail, liberar lease obsoleto pelo worker e respeitar tentativas e
   `delivery_id`; nunca inserir captura manualmente.
5. Confirmar que a fila e a idade voltaram a avançar.

## Rollback

Cancelar apenas geração ainda ativa pela API. Não apagar relatório, evento,
notificação ou tentativa. Desabilitar o canal de e-mail se o provedor continuar
instável; a caixa interna permanece como fonte de entrega.

## Validação e evidências

Validar hash do snapshot, destinatário/organização, uma entrega por chave e
histórico completo. Evidência pública usa dados sintéticos e não inclui corpo,
endereço, justificativa ou hash.
