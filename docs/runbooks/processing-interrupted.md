# Processamento ou fila interrompida

## Responsável e escalonamento

Aplicação lidera; banco participa se houver transação ou lock; negócio valida o
resultado. Falha recorrente ou perda de proveniência é escalada como alta.

## Pré-condições

- execução, estado e versão identificados pela API;
- banco e storage estão prontos;
- arquivo aceito possui hash válido e não há processamento concorrente ativo.

## Procedimento

1. Examinar transições, issues do pipeline e correlation ID.
2. Distinguir rejeição de entrada, falha persistente e interrupção transitória.
3. Usar a ação autenticada de reprocessamento com chave idempotente.
4. Para fila parada, recuperar o worker/processo e observar idade e profundidade.
5. Comparar consolidação e proveniência antes e depois.

## Rollback

Não editar estado ou apagar execução. Se a retomada falhar, conservar a nova
tentativa como falha auditada e manter a última execução válida como referência.

## Validação e evidências

Exigir estado terminal válido, ausência de duplicação silenciosa, mesmo escopo
organizacional e hashes preservados. Registrar IDs técnicos e correlation ID,
sem conteúdo de arquivo.
