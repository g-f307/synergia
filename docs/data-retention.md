# Retenção, minimização e expurgo

A política versionada está em
[`data-retention-policy.json`](data-retention-policy.json). Todos os prazos são
propostas para homologação até aceite formal de operação, segurança e negócio.
Na ausência desse aceite prevalece a conservação: nenhuma rotina reduz dados de
negócio, decisão ou auditoria automaticamente.

## Princípios

- coletar apenas o necessário para a jornada e sua responsabilização;
- separar conteúdo, metadados e trilhas append-only;
- nunca usar exclusão física para ocultar uma decisão ou evento;
- executar expurgo em `dry-run`, com identidade técnica e correlation ID;
- manter backups fora do repositório e das evidências públicas;
- usar exclusivamente dados sintéticos em testes e relatórios públicos.

## Matriz resumida

| Grupo | Classificação | Retenção proposta | Destino | Backup |
| --- | --- | --- | --- | --- |
| identidade, perfis e avatares | confidencial | vínculo e decisão posterior | anonimização aprovada; avatar removível | sim |
| papéis, grupos e permissões | restrito | enquanto houver evidência relacionada | sem expurgo automático | sim |
| sessões e tokens protegidos | restrito | 90 dias após encerramento | aguarda aceite | sim |
| tentativas e rate limiting | restrito | 90 dias | expurgo permitido | sim |
| execuções, dados e proveniência | confidencial | 5 anos | aguarda aceite de negócio | sim |
| uploads aceitos | confidencial | 365 dias | aguarda aceite de negócio | sim |
| conteúdo em quarentena | restrito e não confiável | 24 horas por padrão | apagar bytes, preservar decisão | não |
| relatórios e snapshots | confidencial | 5 anos | histórico imutável | sim |
| notificações e e-mail | confidencial | 180 dias | aguarda aceite | sim |
| aprovações e justificativas | restrito | 5 anos | histórico imutável | sim |
| auditorias | restrito | mínimo de 5 anos | sem expurgo automático | sim |
| logs técnicos | interno | 30 dias | rotação da plataforma | não |
| métricas Prometheus | interno | 15 dias | rotação automática | não |
| backups | restrito | 30 diários e 12 mensais | descarte seguro da plataforma | não |
| evidências sintéticas de CI | interno | 14 dias | expiração do GitHub Actions | não |

O JSON contém a decisão integral para captura local de e-mail, catálogo IAM,
estado transitório de segurança e demais subgrupos. O validador impede que algum
grupo desapareça da matriz sem revisão explícita.

## Expurgo permitido

Somente dois conjuntos estão habilitados nesta release:

```bash
python scripts/data_operations.py retention --dataset quarantine
python scripts/data_operations.py retention --dataset quarantine --apply
python scripts/data_operations.py retention --dataset security_transient --apply
```

Sem `--apply`, a operação apenas informa a contagem agregada. A quarentena
remove os bytes expirados e mantém `file_inspections.discarded_at`, hash,
decisão e motivo. O conjunto `security_transient` remove tentativas de login,
eventos de rate limiting e buckets expirados anteriores ao prazo informado.

Para não perder conteúdo sem metadado correspondente, o expurgo move primeiro
cada arquivo para uma área temporária privada no mesmo filesystem. A alteração
de `discarded_at` e o evento inicial são confirmados sob lock no PostgreSQL antes
da exclusão definitiva. Um manifesto privado correlaciona o lote aos metadados e
permanece até a confirmação do evento de sucesso. Toda nova aplicação serializa
o expurgo e reconcilia primeiro os lotes interrompidos: restaura os arquivos se
o commit não ocorreu ou retoma a exclusão se `discarded_at` já foi confirmado.
Falhas parciais de `unlink()` preservam esse estado para uma nova tentativa.

Auditoria, aprovações, relatórios, notificações, uploads aceitos e avatares são
explicitamente bloqueados pela allowlist. Uma tentativa aplicada é registrada
como `refused`, sem executar exclusão.

## Anonimização

Uma solicitação futura de anonimização deve desativar a identidade, revogar
sessões, remover e-mails e avatar conforme autorização, substituir atributos de
apresentação e preservar o UUID técnico referenciado pelas trilhas. Não existe
expurgo automático de identidade nesta entrega porque prazo, base legal e
responsável ainda precisam de aceite. Implementá-lo antes disso violaria a
regra de conservação da issue #94.

## Responsabilidades

- `business_operations`: prazo de dados operacionais, relatórios e decisões;
- `security`: IAM, auditoria, quarentena e dados de abuso;
- `identity_operations`: solicitações de perfil e anonimização;
- `platform_operations`: backups, logs, métricas e descarte seguro;
- `engineering`: fixtures e evidências sintéticas.

Toda exceção ou retenção legal suspende o expurgo e deve ter chamado, aprovador,
escopo, prazo e correlation ID. A política jurídica definitiva está fora do
escopo e deve substituir formalmente estas propostas quando aprovada.
