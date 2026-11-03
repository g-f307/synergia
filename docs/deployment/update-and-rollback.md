# Atualização e rollback

Use o mesmo projeto `synergia`, arquivos privados e overlays da instalação.
Um operador por vez; registrar SHA, tag, horário, decisão e responsável no
histórico privado. Não executar em produção sem os portões do [mapa](README.md).
Planeje indisponibilidade e suspenda tráfego/mutações na janela autorizada.

## 1. Preparar versão e ponto de recuperação

Antes de trocar a revisão, registre o SHA anterior, conserve o checkout anterior
e uma cópia 0600 de sua configuração. Retenha ambas as imagens com suas tags
imutáveis: não faça prune nem reconstrua a tag anterior. Crie outro checkout
limpo da candidata, conforme [primeira implantação](deployment-guide.md), e
construa/valide ali as imagens e config-check antes de parar serviços.
Se o build falhar, a versão atual deve continuar em execução.

```bash
git rev-parse HEAD
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env images
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/homologation.env stop web backend email-worker
```

- **Onde executar:** host, raiz do checkout anterior, após build da candidata e início da janela.
- **Efeito:** consulta versão/imagens e depois interrompe processos escritores. Suspenda também jobs e acessos externos ao banco/storage.
- **Resultado esperado:** SHA e imagens retidos no histórico privado; serviços parados, banco permanece ativo.
- **Interpretação de falhas:** escritor ainda ativo impede backup de manutenção e captura consistente do ledger.
- **Próxima ação:** confirmar parada dos transmissores/agendadores e preparar backup abaixo.

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
- **Interpretação de falhas:** `reason_code` do CLI, erro de cliente ou ausência da tabela bloqueiam atualização. Legado sem ledger precisa da adoção abaixo antes deste procedimento normal.
- **Próxima ação:** validar restauração isolada; somente liberar migração após evidência de backup recuperável.

**Limite comprovado no código:** o dump do CLI inclui apenas o schema
`synergia`; o inventário de migrations no manifesto são os arquivos do checkout.
Ele não inclui `public.synergia_schema_migrations`. Por isso o ledger é salvo
separadamente, durante a mesma janela sem escritores. O comando `verify` compara
o banco restaurado ao ponto do bundle; não o use contra o banco ativo que já
recebeu novas escritas. A restauração precisa do checkout anterior com inventário
idêntico ao manifesto. Veja [recuperação](../data-recovery.md).

## 3. Migrar e iniciar candidata

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/candidate.env run --rm --no-deps migrate
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/candidate.env up -d --no-deps backend web
```

- **Onde executar:** host, raiz do checkout candidato já construído/validado, com backup recuperável e aplicação parada.
- **Efeito:** mutável; migrations novas em transações individuais e início da candidata. O banco existente permanece.
- **Resultado esperado:** migrate 0 (`apply`/`skip`), depois backend/web healthy e aceite completo aprovado.
- **Interpretação de falhas:** falha intermediária pode deixar migrations anteriores confirmadas. Não inferir que todo SQL foi desfeito.
- **Próxima ação:** em sucesso executar [aceite](post-deployment-checklist.md); em falha manter tráfego suspenso e comparar ledger antes de decidir rollback.

O runner usa advisory lock `7347319119`; não iniciar outro migrador enquanto
há um ativo. Não editar migrations publicadas, checksums ou linhas do ledger.

### Adoção de banco legado

Se aparecer `legacy synergia schema detected without migration history`, pare.
Faça backup de dados/arquivos, comprove a última migration realmente aplicada
com o responsável pelo banco e defina temporariamente
`MIGRATION_BASELINE_THROUGH` no arquivo privado com o nome SQL exato comprovado.
Use o comando migrate acima uma única vez: o runner testa objetos mínimos,
registra o intervalo e aplica posteriores. Não escolha a última migration do
repositório por suposição. Remova a variável após sucesso; schema parcial ou
incompatível bloqueia adoção. Esse teste mínimo não substitui revisão do banco.

## 4. Rollback somente de aplicação

Somente quando o ledger atual for **exatamente igual** ao salvo antes da
atualização e a compatibilidade de configuração/storage tiver sido confirmada.
Compare filenames e SHA-256 pela consulta do [checklist](post-deployment-checklist.md)
com a evidência anterior. Sem ledger anterior confiável, não prossiga.

```bash
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/previous.env stop web backend email-worker
docker compose --project-name synergia --env-file /caminho/privado/synergia-config/previous.env up -d --no-deps --no-build --pull never backend web
```

- **Onde executar:** host, raiz do checkout anterior retido; `previous.env` aponta às tags anteriores e mesmos volumes.
- **Efeito:** mutável; para candidata e inicia imagens anteriores sem rebuild, pull ou SQL.
- **Resultado esperado:** serviços healthy; smoke/aceite aprovados com a origem anterior.
- **Interpretação de falhas:** imagem ausente ou incompatibilidade impede retorno; manter manutenção, não reconstruir tag como substituição.
- **Próxima ação:** validar integralmente antes de liberar tráfego; caso ledger tenha mudado seguir recuperação completa.

## 5. Recuperação completa

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
- **Próxima ação:** plataforma reconecta a versão anterior ao banco/storage recuperados com configuração/mounts revisados; executar migrations em modo idempotente, smoke e aceite antes do tráfego. Registrar RPO/RTO e escritas posteriores ao backup que precisam de tratamento humano.

O Compose base usa seu próprio `postgres` e volumes nomeados. A troca para alvo
recuperado exige provisionamento/mounts e configuração de banco aprovados pela
plataforma; não basta alterar `POSTGRES_PASSWORD`. Detalhes e responsabilidades:
[runbook de restauração](../runbooks/backup-restore.md).

## 6. Automação #166 e operação interrompida

`scripts/deploy.py` está indisponível neste checkout. Depois da entrega, conferir
seu contrato real antes de adotar `diagnose`, `precheck`, `apply`, `verify`,
`rollback` e `reconcile`; não misturar o histórico automatizado com o fluxo manual.
Contrato previsto: `--project synergia`, `--env-file` externo 0600,
`--state-dir` externo 0700 e `--revision` aprovado. `--initialize` é exclusivo
de instalação nova, sem containers/volumes existentes.

A proposta captura baseline, constrói antes da manutenção, migra uma vez,
inicia sem dependências, verifica e confirma. Rollback requer imagens/configuração
retidas, dois volumes existentes e ledger exatamente igual ao anterior; não
reconstrói imagem nem reverte SQL. Estado `running` ou `uncertain` bloqueia nova
operação. Inspecionar primeiro com diagnose/reconcile sem resolução. Só retomar
com `--operation` e `--resolution resume` se todas as migrations da candidata
estiverem confirmadas e não houver migrador ativo; `--resolution rollback`
somente com ledger anterior intacto. SQL parcialmente confirmado exige avaliação
e recuperação, nunca remoção manual de lock/histórico.
