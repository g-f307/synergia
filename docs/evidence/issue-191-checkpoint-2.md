# #191 — checkpoint 2: telemetria e auditoria operacional

16/11/2026, America/Manaus. Base do bloco `33632ac`, branch
`feature/191-ai-assistance-observability`. Bloco 2 de 4; alertas/painel e campanha
adversarial integrada permanecem nos próximos blocos. Não autoriza ativação.

## Resultado entregue

| Critério do bloco | Implementação e comprovação |
| --- | --- |
| Seis resultados de solicitação | Observação HTTP finalizada uma vez por POST; sucesso, reuso, insuficiência, rejeição, indisponibilidade e timeout exercitados |
| Timeout sem contagem duplicada | Worker controlado permanece ativo após 504; gauge continua em 1 até encerrar; conclusão tardia não altera a contagem HTTP nem executa segunda inferência |
| Fronteiras instrumentadas | Contexto, chamada ao provider, gerador, serviço/HTTP e repositório; histogramas de duração/tamanho e códigos fechados também em falhas |
| Reuso/insuficiência | Sem amostra artificial de inferência nem chamada ao provider; origem efetivamente entregue contada separadamente |
| Cardinalidade/privacidade | Somente environment/result/origin/code, mais le automático; marcadores privados e identificadores de negócio ausentes das amostras de métricas/logs |
| Acesso cruzado | Sinal exige conferência interna de organização/permissão; 404 de alvo ausente não cria incidente confirmado nem muda a resposta pública |
| Rotina após término do CLI | Metadados em data_operation_events; novo scrape recupera sucesso/heartbeat após subprocesso encerrar |
| Recuperação/retencão | Prévia sem evento de manutenção; lote vazio é sucesso; totais de reservas expiradas/liberadas, remoções, falhas e inícios sem conclusão consultáveis |
| Atomicidade | Exclusões, eventos por registro, sucesso do lote e respectivas projeções na mesma transação; falha interna/conflito no registro terminal revertem a exclusão |
| Correlação única | No máximo um início e um terminal por operação; repetição da correlação não executa outro lote; falha após sucesso não substitui o sucesso |
| Auditoria/Graylog | Reuso dos triggers existentes; os testes reconciliam eventos da operação e da assistência na view canônica e na outbox PostgreSQL |
| Sem alarmes legados indevidos | Agregados gerais de backup/retenção excluem os dois datasets de manutenção da IA; teste confirma que falha da IA não incrementa o contador crítico legado |
| Falha do próprio banco | Log/exit sanitizados e collection_success=0; não se publica ausência de falhas quando a leitura não foi possível |

## Migration e compatibilidade

Numeração conferida no remoto: a última publicada era `0039`. A nova `0040`
amplia o catálogo fechado de datasets de `data_operation_events`, acrescenta
shape/índices e unicidade para os workers finitos. Não cria nova trilha de
auditoria nem modifica dados de negócio.

Aplicação pelo runner em PostgreSQL 16 descartável aprovada. Adoção de baseline
recusa índice ausente/não único, shape/catálogo ausentes e triggers de
imutabilidade/outbox desabilitados. Adoção válida e runners concorrentes aprovados.

Rollback testado preserva os eventos imutáveis e a aceitação dos dois datasets;
remove os índices/guardas novos. Não restaura literalmente o CHECK antigo, o que
impediria manter o histórico. Reaplicação aprovada. Migrations publicadas não
foram reescritas. O ambiente em uso não recebeu a migration nesta entrega.

O contrato de resposta HTTP continua 1.0.0. Os labels da instrumentação inicial
de IA foram uniformizados; expressões externas que usem os labels anteriores
precisam seguir o [contrato de telemetria](../ai-assistance-observability.md).
O painel versionado anterior não os consumia.

## Validações executadas

Python 3.12; PostgreSQL 16 novo, sem volumes e publicado apenas em loopback.
Providers fakes/servidores de transporte locais; sem inferência real ou credenciais
externas. Resultados abaixo são de execuções com conjuntos sobrepostos, não devem
ser somados como casos distintos.

| Execução | Resultado real |
| --- | --- |
| Toda a suíte backend com `-m 'not integration'` | **2.212 aprovados**, 897 desmarcados, 16 subtestes aprovados; 107,06 s |
| Integrações selecionadas de assistência, auditoria, métricas, migrations e Graylog | **139 aprovados**, 92,93 s |
| Conferência após revisão de classificação de erros: telemetria, manutenção e repositório | **58 aprovados**, 9,30 s |
| Complemento dos guardas finais, baseline válido e runners concorrentes | **8 aprovados**, 11,97 s |
| Conferência final com novos casos, guardas, ativos e documentação | **92 aprovados**, 12,40 s |
| Ruff lint em backend/scripts, conforme CI | Aprovado |
| Ruff format dos arquivos Python afetados | Aprovado |
| Validador de observabilidade da homologação | Aprovado para a baseline: 10 alertas/7 runbooks; os cinco alertas da IA serão adicionados no bloco 3 |
| Inventário web/OpenAPI | Aprovado: 119 operações |
| Matriz de acesso | Aprovada: 112 operações privadas, 5 públicas e 2 técnicas autenticadas |
| `git diff --check` | Aprovado |

A rodada ampliada inicial detectou mudança no tipo de exceção de ator técnico
inexistente. A rotina continuava recusando o ator sem excluir registros; foi
corrigida para preservar `AssistancePersistenceError('actor_not_found')`. A
regressão posterior passou. Avisos remanescentes são depreciações já existentes
de Starlette/httpx e constantes HTTP de importação; nenhuma dependência alterada.

Reprodução dos testes novos, com `DATABASE_URL` apontando a banco **descartável**
migrado até 0040:

```bash
backend/.venv/bin/python -m pytest -c backend/pytest.ini \
  backend/tests/test_ai_assistance_telemetry.py \
  backend/tests/test_ai_assistance_maintenance.py -q
```

O runner de migrations usa as variáveis PostgreSQL do ambiente de teste e cria
bancos descartáveis próprios. Não usar conexão operacional para essa suíte.

## Amostra sanitizada e limites

[Amostra de logs e métricas](issue-191-telemetry-samples.json): três eventos e
12 amostras extraídos de um exercício sintético via aplicação/formatter reais,
com provider controlado, sem rede de inferência. `origin=model` exercita esse
caminho contratual com fake; não atesta uso ou qualidade de um modelo real.
Não contém prompt, contexto, resposta textual, hashes/modelo ou IDs de negócio.

- Os contadores HTTP, internos e persistidos têm semânticas diferentes e não
  devem ser somados. A origem só é contada como entregue em POST 200.
- Histograma de resposta não preenche zero quando o transporte falha sem conteúdo.
- Início sem terminal pode ser uma interrupção histórica, não trabalho ativo.
- Dados do CLI são consultáveis após seu encerramento; uma indisponibilidade
  total do banco continua dependendo de log/exit e monitoração da dependência.
- A outbox comprova projeção transacional, não recebimento/pesquisa no Graylog;
  essa demonstração e suas capturas continuam no bloco 4. Operações globais
  exigem autorização explícita no coletor existente.
- Nenhum frontend foi alterado neste bloco; não houve novo build/E2E Angular.
- Alertas/painel e threat model específico não são declarados concluídos.

Referências: [contrato](../ai-assistance-observability.md),
[runbook](../runbooks/ai-assistance.md), [checkpoint 1](issue-191-checkpoint-1.md).
