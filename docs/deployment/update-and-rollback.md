# Atualização, rollback e recuperação

Use o mesmo projeto `synergia`, configuração externa e histórico da instalação.
Prepare uma janela autorizada, preserve a versão anterior e confirme backup
recuperável antes de qualquer SQL. Produção permanece condicionada aos portões
do [mapa](README.md). O fluxo principal é a automação da #166, cujo contrato
completo está em [deploy-automation.md](../deploy-automation.md).

## Preparar candidata e manutenção

Obtenha um checkout limpo da revisão candidata sem sobrescrever o anterior.
Retenha configuração e imagens anteriores e não execute prune. A automação
retém IDs e cria uma baseline privada ao adotar uma instalação que ainda não
possui histórico; ela não cria backup de domínio/banco automaticamente.

```bash
python3 scripts/deploy.py diagnose --project synergia --env-file /caminho/privado/synergia-config/candidate.env --state-dir /caminho/privado/deploy-history
python3 scripts/deploy.py precheck --project synergia --env-file /caminho/privado/synergia-config/candidate.env --state-dir /caminho/privado/deploy-history
```

- **Onde executar:** host, raiz do checkout candidato limpo; candidate.env preenchido e protegido.
- **Efeito:** somente leitura; confere fonte, perfil, daemon/projeto/volumes e histórico, sem build/SQL/HTTP.
- **Resultado esperado:** saída 0; identidade da instalação e recursos existentes reconhecidos.
- **Interpretação de falhas:** volume ausente, projeto divergente, configuração inválida ou operação anterior running/uncertain exigem diagnóstico; não acrescentar --initialize.
- **Próxima ação:** suspender agendadores externos, esperar qualquer transmissor/migrador terminar e preparar backup consistente.
- **Pré-condições:** Checkout limpo, Docker acessível, projeto correto e env-file externo 0600 pertencente ao operador.
- **Entradas:** Arquivo externo --env-file, histórico --state-dir e identidade --project; revisão/UUID quando indicados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

Não interrompa uma transmissão SMTP em andamento. Espere o worker finito
terminar e impeça novo agendamento. Confirme ausência de outros escritores e
planeje indisponibilidade. Para o backup, pare web/backend e suspenda também
acessos externos a banco/storage; não altere imagens ou volumes.

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/previous.env stop web backend
```

- **Onde executar:** host, checkout anterior e configuração aprovada da instalação, dentro da janela de manutenção.
- **Efeito:** pausa a aplicação; PostgreSQL e volumes permanecem, sem forçar parada do transmissor.
- **Resultado esperado:** web/backend parados e nenhum outro escritor ativo.
- **Interpretação de falhas:** escritores ativos impedem backup consistente. Sem janela/autorização ou sem cópia anterior recuperável, interrompa a atualização.
- **Próxima ação:** realizar e verificar backup de domínio, arquivos e ledger no mesmo ponto; prosseguir somente após recuperação isolada validada.
- **Pré-condições:** Host e autorizações do passo disponíveis; executar um comando por vez e interromper em falha.
- **Entradas:** Ferramentas e configuração indicadas no comando; caminhos são exemplos privados a substituir.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

## 2. Backup antes de qualquer SQL

`scripts/data_operations.py` roda **no host operacional**, não na imagem atual
do backend (que não inclui esse CLI). Pré-requisitos: ambiente Python com
`backend/requirements.txt`, clientes nativos `pg_dump`, `pg_restore` e `psql`
da major 16, e acesso autorizado aos arquivos reais dos volumes. Não use
diretórios locais vazios como se fossem o storage dos containers.

O administrador deve fornecer um arquivo shell privado 0600, revisado, apenas
com exports de `DATABASE_URL`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`,
`PGPASSWORD`, `IMPORT_STORAGE_DIR`, `PROFILE_AVATAR_STORAGE_ROOT` e
`DATA_OPERATIONS_ACTOR`. `DATABASE_URL` e `PG*` devem apontar ao mesmo banco;
storage deve apontar às montagens reais. O arquivo do Compose não é esse arquivo
shell. Não escreva senha em argumento de comando.

```bash
python3 -m venv /caminho/privado/synergia-ops-venv
/caminho/privado/synergia-ops-venv/bin/python -m pip install -r backend/requirements.txt
```

- **Onde executar:** host operacional, raiz do checkout anterior; somente na preparação do ambiente Python.
- **Efeito:** mutável; instala dependências já declaradas em ambiente privado.
- **Resultado esperado:** 0, importações disponíveis; clientes PostgreSQL 16 instalados separadamente pela plataforma.
- **Interpretação de falhas:** acesso ao índice, compatibilidade ou ferramentas ausentes; não iniciar atualização sem capacidade de backup/restore.
- **Próxima ação:** disponibilizar montagens de storage, configuração privada e destino protegido fora do Git.
- **Pré-condições:** Host e autorizações do passo disponíveis; executar um comando por vez e interromper em falha.
- **Entradas:** Ferramentas e configuração indicadas no comando; caminhos são exemplos privados a substituir.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

```bash
source /caminho/privado/synergia-config/data-operations.sh
install -d -m 0700 /caminho/privado/backups/RELEASE_ANTERIOR
umask 077
pg_dump --format=custom --no-owner --no-privileges --table=public.synergia_schema_migrations --file=/caminho/privado/backups/RELEASE_ANTERIOR/ledger.dump
/caminho/privado/synergia-ops-venv/bin/python scripts/data_operations.py backup --destination /caminho/privado/backups/RELEASE_ANTERIOR/bundle
```

- **Onde executar:** host operacional, raiz do checkout anterior; arquivo shell confiável, destino novo por release, escritores parados.
- **Efeito:** mutável; carrega configuração privada, salva ledger separado e bundle de dados/arquivos.
- **Resultado esperado:** cada comando com 0; CLI retorna `outcome=succeeded`; ledger e bundle guardados juntos no cofre, com acesso restrito e integridade protegida.
- **Interpretação de falhas:** `reason_code` do CLI, erro de cliente ou ausência da tabela bloqueiam atualização. Legado sem ledger segue o procedimento especializado abaixo antes de atualização normal.
- **Próxima ação:** validar restauração isolada; somente liberar migração após evidência de backup recuperável.
- **Pré-condições:** Janela sem escritores/migrations, clientes PostgreSQL 16 e storage real montado com acesso autorizado.
- **Entradas:** Arquivo shell confiável, PG*/DATABASE_URL, diretórios de storage e destino novo protegido.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

**Limite comprovado no código:** o dump do CLI inclui apenas o schema
`synergia`; o inventário de migrations no manifesto são os arquivos do checkout.
Ele não inclui `public.synergia_schema_migrations`. Por isso o ledger é salvo
separadamente, durante a mesma janela sem escritores. O comando `verify` compara
o banco restaurado ao ponto do bundle; não o use contra o banco ativo que já
recebeu novas escritas. A restauração precisa do checkout anterior com inventário
idêntico ao manifesto. Veja [recuperação](../data-recovery.md).

## Aplicar candidata pela automação

```bash
python3 scripts/deploy.py apply --project synergia --env-file /caminho/privado/synergia-config/candidate.env --state-dir /caminho/privado/deploy-history --revision "$(git rev-parse HEAD)"
python3 scripts/deploy.py verify --project synergia --env-file /caminho/privado/synergia-config/candidate.env --state-dir /caminho/privado/deploy-history
```

- **Onde executar:** host, checkout candidato limpo; backup recuperável, escritores pausados e revisão aprovada.
- **Efeito:** captura runtime anterior, constrói imagens por operação, valida perfil, pausa web/backend, migra uma vez, inicia sem dependências e confirma após smoke.
- **Resultado esperado:** apply e verify com saída 0; referência ativa e IDs promovidos somente após verificações.
- **Interpretação de falhas:** falha antes da manutenção pode ficar failed; interrupção/incerteza fica running/uncertain e bloqueia novas mutações. SQL confirmado não é automaticamente desfeito.
- **Próxima ação:** sucesso segue [aceite](post-deployment-checklist.md); falha segue inspeção/reconciliação abaixo, sem repetir migrate manualmente.
- **Pré-condições:** Checkout limpo, Docker acessível, projeto correto e env-file externo 0600 pertencente ao operador. Precheck aprovado, janela e backup recuperável; initialize somente em instalação nova.
- **Entradas:** Arquivo externo --env-file, histórico --state-dir e identidade --project; revisão/UUID quando indicados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

Não use `--initialize` na atualização. PostgreSQL existente não é recriado:
troca de senha/usuário/banco, porta publicada ou major version exige procedimento
próprio. Migrations já registradas são puladas pelo runner com os mesmos hashes
e datas. Checksum divergente, migration ausente ou lock ocupado bloqueia a
operação. Não editar SQL publicado, ledger ou arquivo de intenção.

## Rollback somente de aplicação

```bash
python3 scripts/deploy.py rollback --project synergia --env-file /caminho/privado/synergia-config/candidate.env --state-dir /caminho/privado/deploy-history
```

- **Onde executar:** host, checkout aprovado, mesma identidade/histórico e janela autorizada.
- **Efeito:** restaura imagens/configuração anteriores preservadas por ID; não baixa/reconstrói imagens nem reverte SQL.
- **Resultado esperado:** saída 0; nova referência de rollback confirmada depois de runtime, ledger e smoke validados.
- **Interpretação de falhas:** exige ambos os volumes, imagens preservadas e ledger exatamente igual ao da versão anterior. Migration nova confirmada impede esse retorno por padrão; primeira instalação não possui versão anterior.
- **Próxima ação:** validar checklist antes de liberar tráfego; divergência de schema exige decisão de correção para frente ou recuperação conjunta de banco e arquivos.
- **Pré-condições:** Checkout limpo, Docker acessível, projeto correto e env-file externo 0600 pertencente ao operador. Versão anterior, imagens/configuração/volumes preservados e ledger compatível.
- **Entradas:** Arquivo externo --env-file, histórico --state-dir e identidade --project; revisão/UUID quando indicados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

O retorno da aplicação não é restauração de banco ou arquivos. Uma falha após
início da manutenção pode deixar o rollback uncertain; preserve referências,
mantenha manutenção e use reconciliação. Não recrie serviços manualmente para
contornar o estado registrado.

## Operação interrompida e reconciliação

```bash
python3 scripts/deploy.py diagnose --project synergia --env-file /caminho/privado/synergia-config/candidate.env --state-dir /caminho/privado/deploy-history
python3 scripts/deploy.py reconcile --project synergia --env-file /caminho/privado/synergia-config/candidate.env --state-dir /caminho/privado/deploy-history --operation UUID_DA_OPERACAO
```

- **Onde executar:** host, mesmo histórico; substituir o UUID pelo operation.id retornado no diagnóstico.
- **Efeito:** inspeção somente leitura; não toma resolução, inicia containers, executa migrations ou chama readiness.
- **Resultado esperado:** relatório com estado do banco/lock, processo da migration e igualdade do ledger; ou initialization_pending na inicialização ainda não migrada.
- **Interpretação de falhas:** container running/unknown, lock ativo, SQL parcial ou artefato ausente não autorizam retry. not_found não prova que a migration nunca rodou.
- **Próxima ação:** decidir resolução com responsáveis, conforme condições abaixo; preservar journal, candidate e configurações privadas.
- **Pré-condições:** Checkout limpo, Docker acessível, projeto correto e env-file externo 0600 pertencente ao operador.
- **Entradas:** Arquivo externo --env-file, histórico --state-dir e identidade --project; revisão/UUID quando indicados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

| Situação | Decisão segura |
| --- | --- |
| failed antes da manutenção | Corrigir a causa e rever diagnose/precheck; confirmar que não há outra operação ativa. |
| running/uncertain | Bloqueia apply/rollback até reconciliação explícita pelo UUID atual. |
| SQL já tentado e ledger completo da candidata | resume pode iniciar/verificar a candidata sem repetir SQL, se não houver processo/lock ativo ou desconhecido. |
| SQL parcial ou ledger divergente | Resume bloqueado; avaliar correção para frente ou recuperação de banco e arquivos. |
| Ledger anterior intacto | resolution rollback pode restaurar runtime anterior, se configuração/imagens/volumes estiverem íntegros. |
| initialization_pending antes da primeira tentativa SQL | resume pode aguardar/iniciar PostgreSQL preservado e realizar a primeira tentativa; exige identidade válida e ausência de escritores/processo/lock/ledger incompatíveis. |

Escolha **uma** resolução, somente depois de validar suas pré-condições:

```bash
python3 scripts/deploy.py reconcile --project synergia --env-file /caminho/privado/synergia-config/candidate.env --state-dir /caminho/privado/deploy-history --operation UUID_DA_OPERACAO --resolution resume
```

- **Onde executar:** host, inspeção concluída e resolução autorizada para o UUID atual.
- **Efeito:** mutável; retoma instalação preservada ou conclui candidata usando configuração congelada, não mudanças posteriores do env-file.
- **Resultado esperado:** operação succeeded, verify aprovado e referência ativa promovida.
- **Interpretação de falhas:** depois de migration-attempted.json, resume não repete SQL; exige ledger completo. Exceção anterior à primeira tentativa só vale para inicialização comprovadamente pendente.
- **Próxima ação:** sucesso segue checklist; nova incerteza exige inspeção de novo. Não apagar intenção, journal, locks ou containers para forçar repetição.
- **Pré-condições:** Checkout limpo, Docker acessível, projeto correto e env-file externo 0600 pertencente ao operador. Inspeção concluída e resolução autorizada, sem migrador ativo ou desconhecido.
- **Entradas:** Arquivo externo --env-file, histórico --state-dir e identidade --project; revisão/UUID quando indicados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

```bash
python3 scripts/deploy.py reconcile --project synergia --env-file /caminho/privado/synergia-config/candidate.env --state-dir /caminho/privado/deploy-history --operation UUID_DA_OPERACAO --resolution rollback
```

- **Onde executar:** host, alternativa a resume; exige versão anterior compatível e decisão autorizada.
- **Efeito:** mutável; retorna ao runtime anterior pelos artefatos preservados, sem SQL reverso.
- **Resultado esperado:** operação reconciled, não candidata succeeded; runtime anterior verificado antes de promover referência.
- **Interpretação de falhas:** ledger alterado, imagem/configuração ausente ou volume perdido bloqueia a resolução; manter manutenção.
- **Próxima ação:** repetir checklist em sucesso; falha segue responsáveis por aplicação/banco e recuperação completa, preservando histórico.
- **Pré-condições:** Checkout limpo, Docker acessível, projeto correto e env-file externo 0600 pertencente ao operador. Inspeção concluída e resolução autorizada, sem migrador ativo ou desconhecido.
- **Entradas:** Arquivo externo --env-file, histórico --state-dir e identidade --project; revisão/UUID quando indicados.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

## Recuperação completa de banco e arquivos

Migration nova confirmada exige plano de recuperação. Não executar SQL reverso
improvisado. Provisione **outro banco PostgreSQL 16 vazio** e **outros diretórios
de storage vazios**, mantendo o ambiente com falha isolado. Prepare um novo
arquivo shell confiável para esse alvo. Não reutilize configuração do banco ativo.

```bash
source /caminho/privado/synergia-config/recovery-target.sh
/caminho/privado/synergia-ops-venv/bin/python scripts/data_operations.py restore --bundle /caminho/privado/backups/RELEASE_ANTERIOR/bundle
pg_restore --exit-on-error --no-owner --no-privileges --dbname "$PGDATABASE" /caminho/privado/backups/RELEASE_ANTERIOR/ledger.dump
/caminho/privado/synergia-ops-venv/bin/python scripts/data_operations.py verify --bundle /caminho/privado/backups/RELEASE_ANTERIOR/bundle
```

- **Onde executar:** host operacional, checkout anterior; PG* e DATABASE_URL conferidos para o mesmo alvo isolado vazio.
- **Efeito:** mutável; restaura dados/storage, ledger público separado e registra verificação.
- **Resultado esperado:** cada comando 0; restore e verification com `outcome=succeeded`; ledger corresponde à evidência anterior.
- **Interpretação de falhas:** hash, inventário, constraints ou ledger divergentes impedem liberar o alvo. Interromper no primeiro erro; reprovisionar alvo vazio se necessário.
- **Próxima ação:** plataforma reconecta a versão anterior ao banco/storage recuperados com configuração/mounts revisados; validar ledger/schema, smoke e aceite antes do tráfego, e definir com a plataforma a identidade/histórico da instalação recuperada. Não reutilizar uma referência ativa que identifique outro banco/daemon. Registrar RPO/RTO e escritas posteriores ao backup que precisam de tratamento humano.
- **Pré-condições:** Autorização de recuperação, banco/storage isolados vazios e cópia anterior com integridade comprovada.
- **Entradas:** Arquivo shell confiável do alvo, PG*/DATABASE_URL, bundle, ledger.dump e configuração de storage real.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.

O Compose base usa seu próprio `postgres` e volumes nomeados. A troca para alvo
recuperado exige provisionamento/mounts e configuração de banco aprovados pela
plataforma; não basta alterar `POSTGRES_PASSWORD`. Detalhes e responsabilidades:
[runbook de restauração](../runbooks/backup-restore.md).

## Adoção de banco legado sem ledger

A baseline da automação captura uma instalação anterior **com ledger válido**.
Ela não inventa o histórico SQL de um banco legado. Se aparecer
`legacy synergia schema detected without migration history`, pare o fluxo
normal, faça backup e confirme com o DBA a última migration realmente aplicada.

O procedimento especializado pode usar temporariamente
`MIGRATION_BASELINE_THROUGH` com o nome SQL exato comprovado, e uma única
execução do runner em janela sem escritores, antes de adotar a instalação na
automação. Não escolha a última migration do checkout por suposição.
As probes mínimas não substituem revisão de compatibilidade.

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/legacy-adoption.env run --rm --no-deps migrate
```

- **Onde executar:** host, checkout/imagem aprovados, somente no procedimento especializado de adoção legado com backup e prova do ponto de baseline.
- **Efeito:** mutável; registra intervalo comprovado e aplica migrations posteriores em transações por arquivo.
- **Resultado esperado:** saída 0 e ledger compatível com filename/hash e schema esperado.
- **Interpretação de falhas:** schema parcial/incompatível ou SQL posterior falho exige avaliação do DBA; não repetir por suposição ou alterar checksums.
- **Próxima ação:** conferir o ledger, retirar MIGRATION_BASELINE_THROUGH da configuração privada e retomar diagnose/precheck para adoção pela automação.
- **Pré-condições:** Host e autorizações do passo disponíveis; executar um comando por vez e interromper em falha.
- **Entradas:** Ferramentas e configuração indicadas no comando; caminhos são exemplos privados a substituir.
- **Evidência permitida:** registrar data, revisão, etapa, saída/códigos e decisão sanitizados; nunca publicar configuração, chaves, dumps, hosts internos, usuários ou logs brutos.
