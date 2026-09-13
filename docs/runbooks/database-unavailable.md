# PostgreSQL indisponível

## Responsável e escalonamento

Operação de banco lidera; plataforma controla tráfego e aplicação valida a
retomada. Suspeita de perda ou corrupção é escalada imediatamente como crítica.

## Pré-condições

- confirmar que liveness responde e readiness acusa `postgresql`;
- identificar a instância e o último backup aprovado sem copiar credenciais;
- suspender uploads, reprocessamentos, relatórios e decisões.

## Procedimento

1. Verificar processo, espaço, conexões e rede no provedor autorizado.
2. Tentar recuperação do serviço antes de qualquer restauração.
3. Se o banco não for recuperável, provisionar PostgreSQL 16 vazio.
4. Executar [`backup-restore.md`](backup-restore.md) com o último bundle íntegro.
5. Liberar primeiro sondas e leituras; depois, uma escrita sintética controlada.

## Rollback

Uma restauração incompleta não pode receber tráfego. Remover o schema parcial,
preservar o bundle original e retornar o endpoint ao estado não pronto. Nunca
restaurar sobre banco com dados.

## Validação e evidências

Validar readiness, migrations, constraints, contagens e hashes. Registrar RPO e
RTO observados, versão do PostgreSQL, resultado sanitizado e responsáveis.
