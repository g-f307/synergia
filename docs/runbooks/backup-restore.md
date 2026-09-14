# Backup, restauração e retomada

## Responsável e escalonamento

Operação de plataforma executa; operação de banco acompanha o PostgreSQL;
segurança valida proteção e engenharia valida integridade. Falha de backup,
restore ou hash bloqueia a liberação.

## Pré-condições

- PostgreSQL 16 e ferramentas cliente disponíveis;
- destino protegido, criptografado e fora do repositório;
- identidade técnica definida e acessos mínimos ativos;
- banco/storage alvo da restauração vazios;
- bundle escolhido dentro da retenção e sem alteração manual.

## Procedimento

1. Executar backup conforme [`data-recovery.md`](../data-recovery.md).
   Se o bundle já tiver sido publicado, mas a operação tiver retornado falha ao
   registrar o sucesso, repetir exatamente o mesmo destino; a ferramenta valida
   e finaliza a operação existente sem sobrescrever ou duplicar o backup.
2. Guardar somente o resumo sanitizado no chamado; mover o bundle ao cofre.
3. Provisionar PostgreSQL 16 e diretórios vazios em ambiente isolado.
4. Executar `restore` e depois `verify` usando o mesmo bundle.
5. Conferir health, métricas e os domínios exigidos no relatório de validação.
6. Em falha anterior à criação do banco alvo, encaminhar somente a linha JSON
   sanitizada do CLI ao coletor protegido e abrir o incidente.
7. Registrar RPO/RTO observados e o segundo executor.

## Rollback

A ferramenta remove o schema parcial se falhar depois de iniciar o restore.
Se o alvo tiver recebido tráfego, isolá-lo e reprovisionar outro banco vazio;
nunca usar `--clean`, sobrescrever storage ou editar o manifesto.

## Validação e evidências

São obrigatórios migrations idênticas, constraints validadas, contagens
esperadas, hashes de relatórios/arquivos e presença de usuários, execuções,
notificações, aprovações e auditoria. Uma pessoa diferente do autor executa o
roteiro e preenche [`data-recovery-cross-test.md`](../evidence/data-recovery-cross-test.md).
Em projeto solo sem segundo executor disponível, o mantenedor pode dispensar
explicitamente apenas a independência humana; o registro deve identificar o
executor real, a exceção e os resultados reproduzíveis, sem simular outra autoria.
