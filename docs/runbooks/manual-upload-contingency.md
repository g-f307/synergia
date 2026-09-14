# Contingência por upload manual

## Responsável e escalonamento

Operação de negócio executa; gestor autoriza a janela; segurança acompanha se a
fonte automática estiver comprometida. Conector ou RPA permanece fora de escopo.

## Pré-condições

- API, banco e storage com readiness saudável;
- usuário possui `import.create` na organização escolhida;
- arquivo veio do canal autorizado e corresponde ao contrato vigente;
- janela, fonte e responsável foram registrados no chamado.

## Procedimento

1. Gerar SHA-256 local para controle restrito, sem publicar o arquivo.
2. Selecionar fonte e organização explicitamente na tela de importação.
3. Enviar uma vez e guardar o execution ID e correlation ID retornados.
4. Acompanhar inspeção, processamento e resultado; duplicidade não é reenviada.
5. Quando a origem normal voltar, reconciliar pela chave idempotente e hash.

## Rollback

Não apagar uma execução aceita. Em arquivo incorreto, registrar nova importação
correta e manter a anterior com estado e auditoria. Suspender novos envios se o
escopo organizacional ou a proveniência não puderem ser confirmados.

## Validação e evidências

Confirmar fonte, organização, hash, resultado terminal e ausência de duplicação.
A evidência contém apenas IDs técnicos, contagens, horários e códigos seguros.
