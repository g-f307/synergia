# Issue #191 — revisão integral

Data: 16/11/2026. Base da revisão: quatro commits `33632ac`, `6ae7f4f`,
`af3b5ae`, `02d8576`, sobre `e618902`.
Escopo: descrição atual da #191, diff completo, caminhos de sucesso/erro,
contratos, migrations, operação, testes e procedência das evidências.

## Conclusão

Após as correções abaixo, não foram encontrados bloqueadores locais remanescentes
nos critérios da #191. A implementação e as validações locais atendem ao escopo;
isso não declara CI remoto aprovado, aceite produtivo ou qualidade do modelo.
Dependências #187/#188/#189/#190 conferidas no GitHub como encerradas; #192
permanece aberta e responsável pela validação final de integração/implantação.

## Correções encontradas pela revisão

1. **Adoção de baseline 0040:** o runner aceitava um índice terminal único com
   nome/predicado parcialmente compatíveis, mesmo indexando `id` em vez de
   `correlation_id`, ou cobrindo apenas `quarantine`. Dois novos testes em
   PostgreSQL reproduziram a aceitação incorreta. O runner agora verifica a tabela,
   número/identidade das chaves e presença dos dois datasets da assistência no
   predicado. Nenhuma migration publicada foi alterada. Adoção válida, aplicação,
   concorrência e rejeição dos schemas incompletos passaram no reteste.
2. **Classificação de admissão:** recusas 422 por corpo inválido/grande retornavam
   o código HTTP correto, mas a observação da assistência o convertia em
   `internal_error`. Dois testes reproduziram a perda do código. O catálogo fechado
   agora inclui `ai_assistance_invalid_contract`; as recusas continuam fora do
   denominador de disponibilidade, não inferem e não viram falha interna.
3. **Coerência da documentação:** a referência da API foi alinhada à migration
   0040. O guia de persistência passou a usar identidade técnica informada com
   segurança, sem placeholder interpretável como redirecionamento de shell;
   também distingue suspensão operacional de rollback SQL destrutivo de 0038.

As quatro regressões novas falharam antes das correções e passaram depois.
As probes de baseline continuam sendo verificações mínimas de adoção; não são
substituto da revisão de compatibilidade pelo operador/DBA.

## Conferência dos critérios

| Critério | Resultado e fundamento |
| --- | --- |
| Threat model completo | Doze ameaças em R-32–R-43, com origem, fronteiras, prevenção, detecção, testes nomeados e residual; validador confere funções por AST e operações contra OpenAPI/matriz |
| Cardinalidade e conteúdo | Famílias da assistência usam environment/result/origin/code fechados, mais labels automáticos; canários e testes verificam ausência de texto/IDs de negócio em métricas e logs |
| Fronteiras instrumentadas | Contexto, provider, gerador, HTTP e persistência; rotinas finitas observáveis pela auditoria existente, inclusive após o processo CLI terminar |
| Falhas/fallback e contagem coerente | Seis resultados HTTP contados uma vez; reuso/insuficiência sem inferência; worker tardio não altera timeout já entregue; denegações e flags não contaminam a disponibilidade |
| Cinco alertas | Indisponibilidade sustentada, trabalho sem conclusão, integridade/escopo, crescimento de expiradas e falhas repetidas de retenção; disparo/recuperação e cenários negativos aprovados no promtool |
| Runbooks e painel | URLs exatas e severidades verificadas, cinco runbooks específicos com seções obrigatórias; 14 painéis adicionados aos 15 anteriores; consultas reais exportadas e testadas |
| Readiness e degradação | Sonda técnica autenticada de metadados, sem inferência; runtime fora das dependências essenciais; leitura anterior e consulta da execução preservadas no exercício |
| Kill switch | Flag só de geração bloqueia novos POSTs e preserva leitura autorizada; frontend atualiza capability; alteração deve atingir todas as instâncias |
| Reservas e retenção | Recuperação limitada de expiradas, SKIP LOCKED e UUID antigo impedido de concluir; prévia não produz heartbeat; lote vazio é sucesso; exclusão/sucesso/auditoria/outbox atômicos |
| PostgreSQL/Graylog | Evidência anterior comprova 20 eventos sintéticos indexados e reconciliados por ID/ação/origem/outcome/correlação, com reexportação zero; outbox isolada não foi considerada recibo |
| Testes adversariais | Fonte persistida com instruções, HTML/URL/comando/afirmação sem fundamento, referência inválida, pin, SSRF/configuração, redirect/proxy, resposta grande/lenta, rate limit, concorrência e acesso cruzado |
| Implantação e rollback | Limites/capacidade, configuração privada, manutenção, suspensão sem apagar negócio e critérios de reabilitação documentados; 0040 preserva histórico no rollback |
| Convenções | Branch da issue, commits lógicos, API 0.13.0/resultado 1.0.0, sem dependência de aplicação nova; planilhas/arquivos privados fora do Git; sem push/merge nesta revisão |

## Validações executadas nesta revisão

| Execução | Resultado |
| --- | --- |
| Backend completo sem integration | **2.259 aprovados**, 909 desmarcados, 16 subtestes, 93,92 s |
| Integrações de assistência, manutenção, auditoria/Graylog, métricas e runner | **135 aprovadas**, 81,69 s; PostgreSQL 16 descartável em loopback |
| promtool check config | Configuração válida; 21 regras totais |
| promtool test rules | Suítes anterior e IA aprovadas: 13 + 34 cenários |
| Consultas reais do dashboard | 42 expressões com sintaxe válida; dez verificações semânticas aprovadas |
| Contrato de observabilidade | 15 alertas contratados, 12 runbooks e 17 vistas aprovados |
| Threat model | Oito jornadas, nove fronteiras, 43 riscos aprovados |
| Matriz de acesso/mapa web | 112 operações privadas, cinco públicas, duas técnicas; 119 operações inventariadas |
| Governança | Política de 18 grupos e runbooks aprovados |
| Ruff e git diff --check | Aprovados |

As 135 integrações são o recorte pertinente à alteração, não toda a suíte de
integração do repositório. Os avisos remanescentes são depreciações já existentes
de Starlette/httpx e constantes HTTP. O banco desta revisão foi descartado.

Não se repetiu o laboratório externo nesta revisão: foram conferidas as
[evidências do checkpoint 4](issue-191-checkpoint-4.md), incluindo os 61 testes
Angular e os 20 recibos reais do laboratório Graylog. Nenhum código frontend,
transporte GELF ou schema de resultado foi alterado pelas correções desta revisão.

## Limites preservados

- Runtime do exercício era HTTP sintético, sem modelo real; Grafana reproduzia
  captura autenticada de métricas. Isso comprova controles/integração, não utilidade,
  qualidade de explicação ou capacidade produtiva.
- Pin anunciado não atesta host comprometido; grounding lexical não prova verdade.
  Recursos compartilhados, trabalho admitido após timeout e necessidade de
  recuperação explícita permanecem documentados como riscos residuais.
- Falha de coleta não significa zero falhas. Increase extrapola valores;
  contagem exata de manutenção pertence à auditoria. Os alertas não aprovam um SLO
  ou supervisionam por si só a ausência de agendamento de retenção.
- CI remoto, revisão do PR e homologação #192 permanecem etapas posteriores.
  Nenhuma configuração/migration foi aplicada ao ambiente em uso.
