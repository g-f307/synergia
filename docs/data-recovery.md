# Backup e recuperação de dados

O ciclo controlado preserva o schema `synergia`, uploads aceitos, relatórios de
validação, resumos do pipeline, dados normalizados e avatares referenciados.
Relatórios de negócio, notificações, decisões e auditorias estão no dump do
PostgreSQL. Quarentena, captura local de e-mail, logs e métricas são excluídos
deliberadamente segundo a política de retenção.

## Objetivos propostos

- RPO: 24 horas, com um backup consistente diário;
- RTO: 4 horas para provisionar, restaurar, verificar e liberar homologação;
- tolerância operacional versionada para o alerta: 25 horas.

Esses valores são propostas e não SLOs contratuais. Devem ser revistos após a
baseline da #95 e o aceite dos responsáveis.

## Proteção e pré-condições

O operador precisa de `pg_dump` e `pg_restore` da mesma major version do
PostgreSQL no host ou do serviço `postgres` do Compose, acesso ao banco e
leitura dos dois diretórios controlados. Configure
`DATABASE_URL`, `IMPORT_STORAGE_DIR`, `PROFILE_AVATAR_STORAGE_ROOT` e uma
identidade técnica em `DATA_OPERATIONS_ACTOR`.

A senha nunca é incluída nos argumentos do processo, manifesto ou saída. O
bundle é criado com diretório `0700` e arquivos `0600`, mas contém dados
restritos: seu destino deve possuir criptografia em repouso, controle de acesso,
versionamento/imutabilidade e descarte seguro. Não use o repositório, GitHub
Actions público ou diretório servido pela aplicação como destino.

## Backup consistente

```bash
python scripts/data_operations.py backup --destination /backup-protegido/synergia-AAAA-MM-DD
```

A ferramenta abre uma transação `REPEATABLE READ`, exporta o snapshot para
`pg_dump`, inventaria no mesmo snapshot os arquivos referenciados e inclui os
artefatos derivados somente para execuções já terminais. Todos os hashes são
conferidos antes e depois do arquivamento. Escritas confirmadas depois do
snapshot pertencem ao próximo backup. Se um arquivo referenciado sumir ou mudar
durante a operação, o bundle é recusado em vez de produzir uma cópia inconsistente.

O bundle privado contém:

- `database.dump`, em formato custom do PostgreSQL;
- `storage.tar.gz`, com uploads aceitos, artefatos derivados íntegros e avatares
  atuais;
- `manifest.json`, com versão, contagens, migrations e hashes completos.

O manifesto também mantém correlation ID, identidade técnica e contagens
necessárias para finalizar a auditoria. Se o bundle for publicado, mas o evento
de sucesso falhar, repetir o comando com o mesmo destino valida integralmente o
bundle e conclui o mesmo evento de forma idempotente. Um destino sem evento
inicial correspondente continua protegido contra sobrescrita.

Somente contagens, duração, resultado e correlation ID aparecem na saída e em
`data_operation_events`. Caminhos, nomes originais, conteúdo e hashes não são
registrados na telemetria.

Falhas esperadas e falhas de infraestrutura no CLI retornam apenas operação,
reason code e correlation ID seguros. Como uma restauração pode falhar antes de
o banco alvo possuir a tabela de eventos, o operador deve encaminhar essa saída
ao coletor protegido e abrir o incidente do runbook; o alerta Prometheus cobre
somente falhas que puderam ser persistidas no banco operacional.

## Restauração e verificação

O alvo deve ser um banco vazio, sem schema `synergia`, e diretórios de storage
ausentes ou vazios:

```bash
python scripts/data_operations.py restore --bundle /backup-protegido/synergia-AAAA-MM-DD
python scripts/data_operations.py verify --bundle /backup-protegido/synergia-AAAA-MM-DD
```

Antes de modificar o alvo, a ferramenta valida manifesto, hashes do dump e do
arquivo, inventário de migrations e todos os membros do TAR. A restauração usa
uma única transação do PostgreSQL, impede sobrescrita e extrai arquivos por
caminhos validados. Uma falha após restaurar o banco remove o schema parcial; o
alvo não é liberado sem verificação integral.

A verificação compara contagens de todas as tabelas, constraints estrangeiras,
hashes dos snapshots de relatório e hashes/tamanhos dos arquivos. Eventos de
operação criados depois do snapshot são a única contagem que pode crescer.

## Frequência e evidências

Operação de homologação proposta:

1. backup diário e antes de migration ou release;
2. verificação de bundle em toda criação;
3. restauração mensal em ambiente isolado reconstruído;
4. retenção de 30 cópias diárias e 12 mensais;
5. revisão diária dos alertas e mensal do relatório de restauração.

A CI cria dados exclusivamente sintéticos, restaura em banco vazio e publica
somente JUnit e um resumo sanitizado. `database.dump`, `storage.tar.gz` e o
manifesto privado são destruídos ao fim do job e nunca são artefatos públicos.
O procedimento completo está no
[`runbook de backup e restauração`](runbooks/backup-restore.md).
