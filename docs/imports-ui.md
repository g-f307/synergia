# Upload e acompanhamento inicial da ingestão

A jornada web de importação está disponível em `/imports/new` para usuários com
`import.create`. O formulário informa formatos, limite e inspeção antes do envio,
faz validações locais de conveniência e envia `multipart/form-data` para
`POST /imports`. A validação do servidor continua soberana.

Formatos, tamanho máximo e organizações selecionáveis são obtidos de
`GET /imports/policy`. A API retorna somente organizações ativas alcançadas pelo
escopo efetivo de `import.create`; uma permissão global alcança todo o catálogo
ativo. Se essa configuração estiver indisponível, o formulário falha de forma
fechada e mantém o envio bloqueado.

O seletor inclui as seis famílias reconhecidas pela API: `N-FP`, `OWM`,
`GMES/OQC`, `TMS`, `WO Status` e `Total Decision`. As duas famílias de workbook
aceitam somente XLSX. O frontend não fixa extensões nem tamanhos: para cada fonte,
usa `allowed_extensions` e `max_bytes` retornados pela política ativa. Assim, o
limite próprio de 64 MiB de `WO Status` e eventuais ajustes de homologação não
exigem uma nova compilação da aplicação web.

Durante o envio, a tela distingue transferência e inspeção/processamento. Não há
reenvio automático: clique duplo é bloqueado e uma nova tentativa depende de ação
explícita. Respostas `409` apontam para a execução original sem criar trabalho
duplicado. Rejeições que já possuem execução permitem consultar o motivo seguro.

O acompanhamento inicial fica em `/imports/:executionId`, protegido por
`import.read`, e reúne estado, inspeção e resumo do pipeline. Códigos estáveis do
backend são apresentados por traduções `pt-BR` e `en-US`, com fallback seguro.
Somente o nome base do arquivo aparece na interface; caminhos, stacks, conteúdo e
detalhes internos não são apresentados. IDs de correlação retornados pela API são
preservados para suporte.

`WO Status` e `Total Decision` podem concluir como `completed_with_errors` quando
somente parte das linhas é rejeitada. Esse estado é um resultado consultável, não
uma indisponibilidade. Em `WO Status`, `LOT PENDING_OQC` permanece negada com
`contract_blocked` até confirmação da fonte literal da chave. Um segundo envio do
mesmo conteúdo recebe `duplicate_file` e aponta para a execução original.

Antes da homologação dessas fontes, aplique as migrations `0031` e `0032` e
mantenha os limites medidos de `WO Status`: até 64 MiB no arquivo, 640 MiB
descompactados, 1 GiB estimado para o pipeline e 900 segundos. A execução local
autorizada do workbook representativo observou cerca de 688 MiB de RSS e 190
segundos; o contêiner deve possuir margem acima desses valores. O rollback das
migrations deve ocorrer antes de qualquer ingestão dessas famílias, conforme os
scripts de rollback recusam remover restrições que já possuem dados associados.

Os testes usam dados sintéticos equivalentes às fixtures homologadas em
`data/synthetic/fixtures/homologated-workbook/` e às famílias congeladas em
`data/synthetic/ingestion-v1/`. A jornada Playwright envia `WO Status` e
`Total Decision` pela mesma interface e API usadas pelo operador, verifica o
resultado parcial e confirma a idempotência por conteúdo. O acompanhamento
completo da execução, histórico e evidências permanece sob responsabilidade da
issue #59.
