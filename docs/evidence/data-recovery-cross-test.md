# Registro de teste cruzado de recuperação

Estado: executado com exceção explícita de independência humana para projeto solo.

O mantenedor confirmou em 2026-09-14 que não existe outro colaborador disponível
e autorizou uma execução substitutiva no ambiente local. O mesmo agente que
participou da implementação executou o roteiro; portanto, este registro não se
apresenta como revisão de uma segunda pessoa. Não foram anexados bundle,
manifesto privado, credenciais, conteúdo, nomes de arquivo, e-mails ou hashes.

| Campo | Registro |
| --- | --- |
| executor | mantenedor do repositório, com execução automatizada pelo Codex; exceção de projeto solo, sem alegação de segundo autor |
| ambiente isolado e versão PostgreSQL | Linux local; PostgreSQL 16.15 em container; bancos sintéticos descartáveis criados e removidos pelas fixtures |
| data/hora inicial e final | 2026-09-14, 09:29:00–09:29:41 America/Manaus |
| bundle dentro da retenção | aprovado; bundle sintético criado durante a própria execução e destruído ao término |
| backup | aprovado; snapshot consistente, hashes conferidos e finalização idempotente após falha simulada no evento de sucesso |
| restauração em banco vazio | aprovada; banco e storages vazios, restauração e verificação concluídas |
| migrations e integridade | aprovadas; 26 migrations, inventário de hashes, contagens e constraints verificados |
| arquivos presentes/ausentes/corrompidos | aprovados; conteúdo presente restaurado e ausências ou corrupção recusadas com códigos seguros |
| expurgo permitido/proibido | aprovado; quarentena e estado transitório permitidos, conjuntos protegidos recusados e auditados |
| indisponibilidade e retomada | aprovadas; falha final do backup, interrupção anterior ao commit e falhas no primeiro e no segundo `unlink()` retomadas sem incoerência |
| RPO/RTO observados | snapshot sem perda dentro do ponto capturado; escrita posterior destinada ao próximo ciclo; fluxo integrado principal em 4,25 s e suíte em 14,54 s; valores locais não substituem RPO de 24 h e RTO de 4 h propostos |
| decisão e observações sanitizadas | mecanismo aprovado no ambiente sintético; independência humana dispensada explicitamente pelo mantenedor devido à inexistência de outro colaborador |

Comando reproduzido:

```bash
pytest -q -m integration backend/tests/test_data_operations_persistence.py \
  --durations=10
```

Resultado sanitizado: `5 passed in 14.54s`.
