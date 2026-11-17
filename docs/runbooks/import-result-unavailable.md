# Resumo ou divergências da importação indisponíveis

## Responsável e evidência inicial

Aplicação lidera; plataforma participa quando houver falha de armazenamento e
banco quando houver falha de consulta. Use apenas execução, organização
autorizada, horário, código público, status HTTP e correlation ID. Na interface,
abra **Detalhes técnicos** e copie o identificador. Não envie planilha, células,
respostas brutas, tokens, paths ou stack traces no chamado.

## Triagem somente leitura

1. Na sessão autorizada por `import.read`, abra `/imports/<execução>` e consulte
   resumo, inspeção e divergências separadamente. Atualizar ou tentar novamente
   nessa tela faz somente GETs; não reenvia arquivo nem dispara processamento.
2. Consulte `GET /imports/<execução>/result-summary`. O PostgreSQL é a fonte
   dessa resposta; a ausência do JSON no storage não indica trabalho pendente.
3. Interprete disponibilidade e situação da execução como informações distintas:

   | Resultado | Interpretação e ação |
   | --- | --- |
   | `ready` | Contagens persistidas disponíveis, inclusive zero. Pode haver erros; examine a situação da execução e as divergências. |
   | `processing` | Estado ativo conhecido. Atualize a consulta; se não houver evolução, siga [processamento interrompido](processing-interrupted.md). |
   | `unavailable / preparation_error` | Falha antes de produzir resumo. Solicite investigação da preparação; não substitua contagens ausentes por zero. |
   | `unavailable / summary_unavailable` | Estado terminal sem contagens persistidas. Investigue persistência/retenção; ausência não significa processamento ativo. |
   | `unavailable / unknown_execution_state` | Estado não reconhecido pelo contrato. Escale à aplicação com a correlação. |
   | `not_applicable / duplicate` | Este envio não executou novamente o pipeline. Use o vínculo anterior se ele estiver autorizado; não solicite ampliação de permissão apenas para contornar o bloqueio. |
   | `not_applicable / security_rejected` | Use o código público da inspeção e o [runbook de arquivo inválido](invalid-file.md). Não libere ou processe conteúdo recusado. |

4. Em `GET /imports/<execução>/issues`, confira página, filtro de severidade e
   total. `issues_total` do resumo é geral; o total da lista e o CSV respeitam o
   filtro. Uma linha pode produzir várias ocorrências. Compare erros + alertas
   ao total de ocorrências do mesmo recorte, sem confundir com linhas rejeitadas.
5. Aba/linha/campo “Não informado” significa localização ausente ou removida da
   projeção pública. `unmapped_issue` não permite expor motivo livre: encaminhe
   execução e correlação à aplicação. A tabela e o CSV não são acesso ao
   arquivo original nem aos valores normalizados.

## HTTP e falhas parciais

- **401:** sessão ausente/expirada; autentique novamente. Não é fila pendente.
- **403:** permissão insuficiente; confirme o perfil autorizado. `import.read`
  não concede `execution.read`, `artifact.read` ou exportação da evidência.
- **404:** recurso inexistente, sem organização IAM ou fora do escopo. Confirme
  execução e organização por canal autorizado; não informe se há recurso em
  outra organização.
- **422:** revise filtros/paginação; não reenvie o arquivo para corrigir a consulta.
- **503 `import_result_unavailable` ou `import_issues_unavailable`:** falha
  operacional da consulta. Preserve o resultado carregado, registre correlação
  e horário e siga [banco indisponível](database-unavailable.md) ou
  [API indisponível](api-unavailable.md), conforme as sondas indicarem.

Uma falha na lista ou no CSV não invalida as contagens já carregadas. Repita
somente a seção necessária. Se o download for interrompido após os headers,
descarte o CSV incompleto e repita o GET de exportação; não espere um novo
status HTTP no meio do arquivo.

## Artefato ausente e limites de recuperação

A rota legada `/imports/<execução>/pipeline-summary` continua retornando seu
artefato ou 404. Se ela retornar 404 e `result-summary` retornar `ready`, use as
contagens persistidas. Nenhuma leitura deve recriar o JSON. Se ambos estiverem
ausentes em estado terminal, mantenha `unavailable`; não fabrique JSON, altere
histórico, invente contagens, aumente retenção ou reimporte automaticamente.

Se houver perda de arquivos referenciados ou storage indisponível, siga
[armazenamento indisponível](storage-unavailable.md) e
[backup/restauração](backup-restore.md). Uma restauração depende da política e
autorização operacionais existentes e preserva a consistência entre banco e
storage. Esta correção não recupera conteúdo apagado.

## Encerramento

Registre a disponibilidade, o motivo público, o resultado de cada consulta e
a correlação correspondente. Confirme que consultas repetidas mantêm dados,
transições e artefatos inalterados; autenticação e auditoria de acesso seguem
suas políticas próprias. Ver [contrato](../import-result-summary.md) e
[roteiro de validação](../import-diagnostics-validation.md).
