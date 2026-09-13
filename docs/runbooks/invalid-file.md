# Arquivo inválido ou em quarentena

## Responsável e escalonamento

Operação de negócio orienta o remetente; segurança analisa padrões repetidos ou
conteúdo ativo. Engenharia só participa quando uma fixture válida é rejeitada.

## Pré-condições

- execution ID e reason code obtidos pela API autenticada;
- arquivo permanece inacessível ao público;
- nenhum conteúdo é anexado ao chamado ou aos logs.

## Procedimento

1. Consultar a inspeção e confirmar extensão, tamanho, decisão e código seguro.
2. Para erro de contrato, solicitar novo upload corrigido pela jornada normal.
3. Para conteúdo ativo ou corrupção, manter isolamento até `retained_until`.
4. Executar o expurgo de quarentena primeiro em `dry-run` e depois com
   `--apply`, apenas quando o prazo tiver expirado.

## Rollback

Expurgo de bytes expirados não possui rollback; a decisão e o hash continuam no
banco. Antes do prazo, interromper a operação. Nunca mover manualmente um item
rejeitado para `accepted/`.

## Validação e evidências

Confirmar `discarded_at`, ausência do conteúdo e permanência do evento de
inspeção. Evidências contêm somente reason code, datas, contagens e correlação.
