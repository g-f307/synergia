# Falhas controladas e recuperação exploratórias pré-RPA

## Resultado e comparabilidade

Em 15/09/2026, F01–F06 foram exercitados em fixtures sintéticas pequenas.
F04 revelou um defeito: uma Workorder confirmada individualmente podia ser
consultada enquanto sua execução permanecia em `applying_rules`. A publicação
operacional foi limitada a execuções terminais e o fluxo de importação passou
a confirmar registros importados, normalizados, unidades de processamento,
auditoria e estado terminal em **uma transação PostgreSQL**. Cada Workorder
continua isolada por savepoint; falha em uma unidade não invalida outra.

Uma queda real de subprocesso antes do commit reverteu todos esses resultados;
o utilitário de recuperação releu os arquivos aceitos verificados e concluiu
a mesma execução uma vez. Uma queda depois do commit deixou a execução
terminal e a recuperação não a duplicou. Duas recuperações simultâneas
produziram uma confirmação e uma resposta de execução já terminal.

Isto **não é uma baseline comparável**: worktree suja, PostgreSQL 18.3 em vez
do alvo 16, fixtures unitárias e não os volumes de 6.800 linhas/88.000 seriais,
sem instrumentação de recursos durante a injeção. A interrupção real foi do
subprocesso executor, não do container/API completa. A retomada é **operacional
e explícita**, não automática; não certifica a capacidade corporativa nem os
volumes de referência.

## Ambiente e massa

Host Linux 7.1.5 (Fedora 44), Python 3.14.7, 12 CPUs lógicas e
8.022.978.560 bytes de RAM. PostgreSQL 18.3 local temporário na porta 55432,
`max_connections=100`, `shared_buffers=128MB`, sem limites de CPU/RAM por
serviço. API e banco no mesmo host, armazenamento temporário local. Commit base
`61c25fb6a158c1a25f0932b72646e06ca0637c1e`; mudanças desta execução
permaneceram não commitadas. O teste usou registros sintéticos das fixtures
de `backend/tests`; os testes novos de queda usam um CSV aceito com uma linha
de plano, uma Workorder, um lote e um serial, organização sintética única e
SHA-256 validado. Outros casos usam uma ou poucas Workorders. Não foram usadas
massas `reference`, dados reais nem credenciais de produção.

## Fronteiras verificadas

| Caso | Falha injetada e verificação | Resultado |
| --- | --- | --- |
| F01 | exceção após reserva; reserva incompleta após interrupção | execução falha e sem claim global; nova execução pode reservar os mesmos bytes |
| F02 | exceção e saída abrupta durante validação | sem saída publicada; retomada releu o arquivo aceito e concluiu |
| F03 | exceção após gravar Workorder/lote/serial, antes do commit da unidade | tabelas operacionais revertidas; evento de falha de persistência registrado |
| F04 | saída abrupta durante o savepoint da unidade e após o commit final | antes: todas as saídas revertidas e retomadas uma vez; depois: estado terminal, retomada no-op |
| F05 | exceção durante geração de relatório | versão falha e auditada, zero artefatos; exportação recusada com `409` |
| F06 | exceção no evento de auditoria da reserva de reprocessamento | execução/vínculo/chave/evento revertidos; mesma chave pode ser tentada novamente |

Os testes de queda real, reserva incompleta, hash adulterado e recuperação
concorrente estão em `backend/tests/test_import_recovery.py`. Os testes de
injeção controlada F01/F02/F04 do importador estão em
`backend/tests/test_imports.py`; F03/F04, em
`backend/tests/test_processing_persistence.py`; F05 e F06, respectivamente,
em `backend/tests/test_report_persistence.py` e
`backend/tests/test_execution_lifecycle.py`. Os JUnit XML locais sob
`artifacts/performance/` são artefatos não versionados da execução. A
regressão final integrada F01–F06, recuperação, consultas, persistência,
relatórios, reprocessamento e autorização concluiu com 63/63 testes após a
mudança atômica (`artifacts/performance/f01-f06-final-local-pg18-junit.xml`).
Seis deles cobrem recuperação, incluindo três saídas abruptas e duas
retomadas concorrentes. O dashboard concluiu 10/10 em Chromium headless.
Quantidade ausente no indicador permanece
`null`; zero explícito permanece zero.

## Correção e decisão de release

No caminho de importação novo, `PostgresProcessingRepository.persist_in_transaction`
usa savepoints dentro da transação de `commit_pipeline`. A transição terminal
ocorre na mesma confirmação. O filtro de publicação de
`PostgresQueryRepository` permanece como defesa para execuções parciais
legadas e mantém escopo organizacional, autorização, proveniência e auditoria.
Antes, F04 retornava Workorder de execução ativa; depois, ela só aparece quando
a confirmação terminal existe.

`scripts/recover_interrupted_import.py` faz prévia por padrão. Com `--apply`,
serializa a recuperação por execução via advisory lock, compara a reserva
idempotente com os hashes dos arquivos, verifica bytes/tamanho, versão do
pipeline/catálogo e escopo organizacional, relê fontes aceitas e conclui a
execução na transação atômica. O tempo de classificação é derivado de
`executions.started_at`, também usado pelo upload normal, para manter a
reclassificação determinística. Se não houve reserva idempotente e a execução
permanece `pending`, o operador pode marcá-la `failed` e criar nova tentativa.
Se há saída parcialmente confirmada pelo código antigo, o utilitário recusa
alterações e exige reconciliação manual; **não remove dados nem auditoria**.

Antes de aplicar, parar os workers de upload e usar um ambiente isolado. Uma
queda da própria recuperação antes do commit pode ser repetida; após o commit,
ela retorna `already_terminal`. A política operacional ainda precisa ser
integrada ao procedimento de release e repetida no PostgreSQL 16/volume de
referência. Não se deve editar dados diretamente para fazer a recuperação
passar.

Para repetir a parte verificada, iniciar PostgreSQL isolado, aplicar todas as
migrations e definir `DATABASE_URL`; executar:

```bash
backend/.venv/bin/pytest -q backend/tests/test_imports.py
backend/.venv/bin/pytest -q backend/tests/test_import_recovery.py
backend/.venv/bin/pytest -q backend/tests/test_processing_persistence.py \
  backend/tests/test_query_persistence.py \
  backend/tests/test_authorization_persistence.py \
  backend/tests/test_report_persistence.py \
  backend/tests/test_execution_lifecycle.py
python scripts/recover_interrupted_import.py <execution-id> \
  --storage-root /caminho/isolado/imports
python scripts/recover_interrupted_import.py <execution-id> \
  --storage-root /caminho/isolado/imports --apply
```

Na execução definitiva, registrar `environment.json`, manifesto da massa,
amostras e recursos do processo/banco, antes e depois da interrupção; usar
PostgreSQL 16, volumes de referência e um ambiente descartável. A queda deve
ser aplicada antes/depois de commits reais, com verificação de contagens,
consolidados, artefatos, auditoria, isolamento organizacional e tentativa de
retomada com a mesma chave. O teste de ruptura e a capacidade final permanecem
fora desta evidência exploratória.
