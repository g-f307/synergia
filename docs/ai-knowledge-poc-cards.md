# Fichas experimentais da PoC #183

Material fictício, sem homologação operacional. Gerado de `data/synthetic/ai-knowledge-v1/knowledge.json`; não editar separadamente.

Indício compatível não é causa comprovada. Procedimentos são apenas verificações humanas no domínio simulado.

## K01 — Aprovação e retenção em lotes distintos

Versão 1.0.0; estado `current`; trecho `K01:P1`.

Uma aprovação exibida junto à retenção pode pertencer a outro lote. A coincidência de Workorder não confirma o mesmo escopo.

**Escopo:** Registros de inspeção e retenção com aprovação e OQC Hold presentes.

**Vocabulário:** escopo, lote distinto, aprovação, retenção, Workorder, abrangência.

- `supported`: approval=true, hold=true e scope_relation=different. Conferir os dois IDs literais, sem aproximar nomes.
- `rejected`: approval=true, hold=true e scope_relation=same.
- `possible`: approval=true e hold=true, mas vínculo de lote desconhecido.
- `not_applicable`: approval=false ou hold=false; a combinação necessária não está presente.

**Verificação V01:** Conferir o lote literal e a origem da aprovação e da retenção nos registros correspondentes antes de relacioná-las.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** approval, hold, approval_lot, hold_lot, scope_relation.

**Exemplo de desenvolvimento:** Aprovação e retenção observadas, vinculadas a lotes literais diferentes.

**Contraexemplo:** Hold comum explicitamente falso: a combinação exigida não existe.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.

## K02 — Retenção registrada depois da aprovação

Versão 1.0.0; estado `current`; trecho `K02:P1`.

Uma retenção pode ter sido registrada após a inspeção aprovada no mesmo lote. É preciso manter a sequência das decisões sem supor encerramento.

**Escopo:** Aprovação e OQC Hold simultâneos, com vínculo de lote.

**Vocabulário:** cronologia, depois, posterior, aprovação, retenção, sequência, decisão.

- `supported`: approval=true, hold=true, scope_relation=same e hold_after_pass=true.
- `rejected`: A combinação existe, mas os lotes são distintos ou a retenção não é posterior à aprovação no mesmo lote.
- `possible`: A combinação existe, mas faltam lote ou datas para determinar a sequência.
- `not_applicable`: approval=false ou hold=false.

**Verificação V02:** Localizar os registros datados da decisão no mesmo lote e verificar a sequência e eventual registro explícito de encerramento.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** approval, hold, approval_lot, hold_lot, approved_at, held_at, scope_relation, hold_after_pass.

**Exemplo de desenvolvimento:** Mesmo lote: aprovação em 01/10 e retenção em 02/10, com fusos explícitos.

**Contraexemplo:** Mesmo lote com retenção anterior à aprovação; não inverter a sequência.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.

## K03 — Retenção de longo prazo é um indicador independente

Versão 1.0.0; estado `current`; trecho `K03:P1`.

O hold comum desmarcado não elimina uma retenção longa marcada. Flags diferentes não se anulam automaticamente.

**Escopo:** Indicador de retenção de longo prazo no escopo da entidade.

**Vocabulário:** long term hold, retenção longa, prazo, indicador, hold comum, independente.

- `supported`: long_hold=true, mesmo quando hold=false ou approval=true.
- `rejected`: Não usar como explicação de retenção longa um valor long_hold=false; nesse caso está fora do escopo.
- `possible`: long_hold é desconhecido ou não exposto; conferir esse indicador antes de concluir ausência de restrição.
- `not_applicable`: long_hold=false.

**Verificação V03:** Conferir o indicador de retenção longa e seu histórico específico na fonte; não usar o hold comum como substituto.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** hold, long_hold, ship_block, any_hold.

**Exemplo de desenvolvimento:** Hold comum falso e retenção longa verdadeira; os indicadores são distintos.

**Contraexemplo:** Retenção longa explicitamente falsa; não inventar prazo prolongado.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.

## K04 — Motivo da restrição ausente ou não disponibilizado

Versão 1.0.0; estado `current`; trecho `K04:P1`.

Uma restrição registrada pode exigir consultar sua justificativa. Ausência confirmada no extrato e texto não disponibilizado são lacunas diferentes.

**Escopo:** Pelo menos uma flag hold, long_hold ou ship_block verdadeira.

**Vocabulário:** motivo, justificativa, razão, ausente, não exposto, desconhecido, restrição.

- `supported`: any_hold=true e estado de reason=confirmed_absent: o motivo está ausente neste recorte, sem explicar a causa da ausência.
- `rejected`: any_hold=true e reason observado/preenchido; não declarar que o motivo não existe.
- `possible`: any_hold=true e reason=unknown ou not_exposed. Não converter desconhecimento ou minimização em ausência confirmada.
- `not_applicable`: Nenhuma flag de restrição verdadeira foi confirmada no recorte; motivo vazio isolado não comprova retenção.

**Verificação V04:** Consultar a justificativa vinculada à restrição na fonte original; se não estiver disponível, encaminhar para esclarecimento sem preencher uma causa por suposição.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** hold, long_hold, ship_block, any_hold, reason.

**Exemplo de desenvolvimento:** Flag de retenção confirmada e motivo vazio no extrato conferido.

**Contraexemplo:** Justificativa preenchida; não apresentar o motivo como ausente.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.

## K05 — Indício documental de contraprova ainda pendente

Versão 1.0.0; estado `current`; trecho `K05:P1`.

Uma nota sobre nova amostra ou repetição de ensaio pode indicar uma etapa de confirmação ainda aberta. Mencionar teste encerrado não significa nova contraprova pendente.

**Escopo:** Restrição ativa e observação textual sobre confirmação por amostra ou ensaio.

**Vocabulário:** contraprova, segunda amostra, novo ensaio, repetição, confirmação, aguardando teste.

- `supported`: any_hold=true e nota afirma que uma segunda amostra, contraprova, repetição de medição ou novo ensaio ainda aguarda conclusão. Não é prova da causa física.
- `rejected`: any_hold=true e nota nega nova avaliação ou informa que a confirmação terminou; não reabrir esse procedimento por uma palavra isolada.
- `possible`: any_hold=true e nota indica dúvida explícita sobre existir repetição de ensaio pendente.
- `not_applicable`: any_hold=false ou nota não contém indício sobre amostra/ensaio de confirmação. Texto não disponibilizado não autoriza inventar esse indício.

**Verificação V05:** Localizar o registro da amostra ou ensaio de confirmação vinculado ao mesmo lote e conferir se a conclusão foi registrada.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** hold, long_hold, ship_block, any_hold, note.

**Exemplo de desenvolvimento:** O laboratório separou outra amostra; o parecer da nova medição ainda não voltou.

**Contraexemplo:** Não há outra medição pendente; o laboratório encerrou a confirmação.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.

## K06 — Indício de problema na identificação física

Versão 1.0.0; estado `current`; trecho `K06:P1`.

Uma nota pode apontar divergência de etiqueta, identificação de pallet ou rastreabilidade física. Isso é diferente de reprovação de qualidade e de documento fiscal.

**Escopo:** Restrição ativa e observação sobre correspondência da identificação física.

**Vocabulário:** etiqueta, rótulo, pallet, identificação física, marcação, rastreabilidade.

- `supported`: any_hold=true e nota descreve identificação física incompatível, etiqueta ilegível, troca de rótulo ou divergência entre marcação e volume.
- `rejected`: any_hold=true e nota confirma correspondência/legibilidade da identificação; negação precisa ser preservada.
- `possible`: any_hold=true e a nota deixa explicitamente em dúvida a correspondência da identificação física.
- `not_applicable`: any_hold=false ou não há menção pertinente a identificação física.

**Verificação V06:** Conferir a identificação física do volume e o vínculo literal com pallet/lote no registro de rastreabilidade, sem alterar etiquetas por inferência.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** hold, long_hold, ship_block, any_hold, note.

**Exemplo de desenvolvimento:** O código impresso na caixa não corresponde ao volume que foi separado.

**Contraexemplo:** O código impresso corresponde ao volume; nenhuma divergência de identificação foi encontrada.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.

## K07 — Indício de pendência administrativa ou documental

Versão 1.0.0; estado `current`; trecho `K07:P1`.

Uma nota pode indicar impedimento de documentação ou cadastro, coexistindo com inspeção aprovada. Isso não significa defeito físico nem autorização de embarque.

**Escopo:** Restrição ativa e observação administrativa/documental.

**Vocabulário:** administrativo, documentação, cadastro, fiscal, registro pendente, expedição.

- `supported`: any_hold=true e nota afirma documento, cadastro ou conferência administrativa ainda pendente.
- `rejected`: any_hold=true e nota nega pendência administrativa ou informa documentos já concluídos.
- `possible`: any_hold=true e nota não permite resolver se a pendência administrativa existe. Orientações documentais conflitantes de mesma precedência não têm vencedor presumido.
- `not_applicable`: any_hold=false ou ausência de indício documental/administrativo na nota.

**Verificação V07:** Consultar o registro administrativo vinculado e seu responsável; se as fontes de mesma precedência divergirem, esclarecer a orientação vigente antes de encaminhar uma ação.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** hold, long_hold, ship_block, any_hold, note.

**Exemplo de desenvolvimento:** Os dois registros confirmam documento fiscal pendente.

**Contraexemplo:** A nota trata exclusivamente de sequência de inspeção, sem indício administrativo.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.

## K08 — Aprovação sem registro de encerramento não resolve a restrição

Versão 1.0.0; estado `current`; trecho `K08:P1`.

Uma inspeção aprovada no mesmo instante ou depois da retenção não comprova que a restrição foi formalmente encerrada. É necessário um registro específico de encerramento no mesmo lote.

**Escopo:** Aprovação e OQC Hold presentes para o mesmo lote.

**Vocabulário:** encerramento, resolução, aprovação posterior, liberação, registro explícito, retenção anterior.

- `supported`: approval=true, hold=true, scope_relation=same, hold_after_pass=false e release_record não é true. A conclusão é falta de prova de encerramento, não afirmação de causa.
- `rejected`: A combinação existe, mas os lotes diferem, a retenção veio depois da aprovação ou release_record=true confirma um registro explícito.
- `possible`: A combinação existe e falta vínculo ou sequência para saber se a aprovação é posterior; preservar a lacuna.
- `not_applicable`: approval=false ou hold=false.

**Verificação V08:** Localizar o registro explícito de encerramento no mesmo lote, mantendo separadas a aprovação da inspeção e a resolução da restrição.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** approval, hold, approval_lot, hold_lot, approved_at, held_at, scope_relation, hold_after_pass, release_record.

**Exemplo de desenvolvimento:** Mesmo lote e instantes iguais, sem registro de encerramento: a aprovação não prova resolução.

**Contraexemplo:** Há registro explícito de encerramento vinculado ao mesmo lote.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.

## K09 — Carga parcial e indicador OQC são coexistência, não causa

Versão 1.0.0; estado `current`; trecho `K09:P1`.

Uma linha de container/modelo pode ter carga inferior ao planejado e indicador OQC positivo. A coexistência não demonstra que a qualidade causou o saldo.

**Escopo:** Situação de carregamento explicitamente fornecida.

**Vocabulário:** carregamento, container, planejado, saldo, OQC Pending, carga parcial.

- `supported`: Nunca confirmar causalidade somente por quantidades e flags.
- `rejected`: loading=true e carga completa ou oqc_pending=0 contrariam esta combinação específica.
- `possible`: loading=true e quantidades/indicadores são compatíveis com carga parcial e OQC positivo, ou faltam valores discriminantes.
- `not_applicable`: loading=false.

**Verificação V09:** Conferir planejamento, carregamento, vínculo container/modelo e sequência OQC antes de relacionar o saldo à qualidade.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** loading, planned, loaded, oqc_pending.

**Exemplo de desenvolvimento:** Planejado 220, carregado 39, indicador OQC 39; coexistência sem prova causal.

**Contraexemplo:** OQC Pending zero contraria essa combinação específica de indicadores.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.

## K10 — Repetição de arquivo não é repetição de retenção

Versão 1.0.0; estado `current`; trecho `K10:P1`.

Uma observação de arquivo já importado pode representar idempotência de ingestão, sem nova execução. Isso não descreve o estado de retenção de um lote.

**Escopo:** Ocorrência explicitamente técnica de importação de arquivo repetido.

**Vocabulário:** arquivo, upload, já importado, idempotência, processamento, execução existente.

- `supported`: Nota afirma arquivo já importado e nenhum novo processamento foi iniciado.
- `rejected`: Nota informa importação nova em vez de arquivo repetido.
- `possible`: Há indício de repetição do arquivo mas a existência de execução não está confirmada.
- `not_applicable`: Observação não trata de repetição de arquivo. A palavra repetição de ensaio não é repetição de upload.

**Verificação V10:** Consultar a execução existente pelo vínculo da importação, sem iniciar novo processamento só para investigar.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** note.

**Exemplo de desenvolvimento:** Arquivo já importado. Nenhum novo processamento foi iniciado.

**Contraexemplo:** Foi iniciada uma importação nova; não se trata de arquivo repetido.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.

## K11 — Versão antiga: aprovação genérica

Versão 0.0.1; estado `archived`; trecho `K11:P1`.

ARQUIVADA. Material de teste de vigência; não pode orientar a investigação. Uma aprovação exibida junto à retenção pode pertencer a outro lote. A coincidência de Workorder não confirma o mesmo escopo.

**Escopo:** Registros de inspeção e retenção com aprovação e OQC Hold presentes.

**Vocabulário:** escopo, lote distinto, aprovação, retenção, Workorder, abrangência.

- `supported`: approval=true, hold=true e scope_relation=different. Conferir os dois IDs literais, sem aproximar nomes.
- `rejected`: approval=true, hold=true e scope_relation=same.
- `possible`: approval=true e hold=true, mas vínculo de lote desconhecido.
- `not_applicable`: approval=false ou hold=false; a combinação necessária não está presente.

**Verificação V01:** Conferir o lote literal e a origem da aprovação e da retenção nos registros correspondentes antes de relacioná-las.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** approval, hold, approval_lot, hold_lot, scope_relation.

Substituída por `K01`; excluída por código.

**Exemplo de desenvolvimento:** Aprovação e retenção observadas, vinculadas a lotes literais diferentes.

**Contraexemplo:** Hold comum explicitamente falso: a combinação exigida não existe.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.

## K12 — Versão antiga: repetição de inspeção

Versão 0.0.1; estado `archived`; trecho `K12:P1`.

ARQUIVADA. Material de teste de vigência; não pode orientar a investigação. Uma nota sobre nova amostra ou repetição de ensaio pode indicar uma etapa de confirmação ainda aberta. Mencionar teste encerrado não significa nova contraprova pendente.

**Escopo:** Restrição ativa e observação textual sobre confirmação por amostra ou ensaio.

**Vocabulário:** contraprova, segunda amostra, novo ensaio, repetição, confirmação, aguardando teste.

- `supported`: any_hold=true e nota afirma que uma segunda amostra, contraprova, repetição de medição ou novo ensaio ainda aguarda conclusão. Não é prova da causa física.
- `rejected`: any_hold=true e nota nega nova avaliação ou informa que a confirmação terminou; não reabrir esse procedimento por uma palavra isolada.
- `possible`: any_hold=true e nota indica dúvida explícita sobre existir repetição de ensaio pendente.
- `not_applicable`: any_hold=false ou nota não contém indício sobre amostra/ensaio de confirmação. Texto não disponibilizado não autoriza inventar esse indício.

**Verificação V05:** Localizar o registro da amostra ou ensaio de confirmação vinculado ao mesmo lote e conferir se a conclusão foi registrada.

Exibir a verificação somente para supported ou possible; essa escolha é do código. Rejeitada/fora de escopo não autoriza liberação nem encerra outras hipóteses.

Conhecimento fictício para experimento. Compatibilidade de indícios não prova causa, não determina prioridade operacional nem autoriza corrigir, liberar ou alterar dados. Unknown/not_exposed significam desconhecimento; confirmed_absent confirma ausência somente no recorte, não na fonte inteira. Não misturar lotes nem momentos. Consultar a fonte indicada é uma verificação humana, sem execução automática.

**Campos pertinentes:** hold, long_hold, ship_block, any_hold, note.

Substituída por `K05`; excluída por código.

**Exemplo de desenvolvimento:** O laboratório separou outra amostra; o parecer da nova medição ainda não voltou.

**Contraexemplo:** Não há outra medição pendente; o laboratório encerrou a confirmação.

Os exemplos ficam fora do prompt inicial; uso posterior exige variante de desenvolvimento registrada.
