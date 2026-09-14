# Armazenamento indisponível

## Responsável e escalonamento

Plataforma lidera; segurança participa em divergência de hash e aplicação em
reprocessamento. Corrupção ou acesso indevido é incidente crítico.

## Pré-condições

- readiness identifica `storage` como indisponível;
- novos uploads estão suspensos;
- último bundle íntegro e banco correspondente estão identificados.

## Procedimento

1. Verificar montagem, permissão, espaço e escrita/leitura com a sonda segura.
2. Não criar manualmente arquivos aceitos nem editar `storage_key`.
3. Recuperar o volume ou restaurar banco e storage como uma unidade pelo
   runbook de backup e restauração.
4. Executar `data_operations.py verify` antes de reabrir a escrita.

## Rollback

Se hashes ou inventário divergirem, retirar o volume de serviço, preservar uma
cópia restrita para investigação e voltar ao último bundle integral. Não
misturar arquivos de backups diferentes.

## Validação e evidências

Exigir readiness `200`, todos os arquivos referenciados presentes e íntegros e
download autenticado de uma evidência sintética. Registrar apenas contagens,
códigos e correlation IDs.
