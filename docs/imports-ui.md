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

Os testes usam dados sintéticos equivalentes às fixtures homologadas em
`data/synthetic/fixtures/homologated-workbook/`. O acompanhamento completo da
execução, histórico e evidências permanece sob responsabilidade da issue #59.
