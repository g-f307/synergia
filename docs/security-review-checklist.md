# Checklist de revisão de segurança

Use este checklist em PRs que alterem contrato, fronteira, dado sensível,
autorização ou operação crítica. Itens não aplicáveis devem receber uma
justificativa no PR.

## Contrato e entrada

- [ ] A operação está no OpenAPI e, quando privada, na matriz de acesso.
- [ ] Modelos de entrada rejeitam campos extras e valores fora do catálogo.
- [ ] Ordenação, paginação, filtros, formatos e tamanhos são limitados.
- [ ] SQL e comandos usam parâmetros; texto do usuário não compõe instruções.
- [ ] Upload valida nome, extensão, MIME, assinatura, conteúdo e limites.

## Autenticação e autorização

- [ ] O backend valida sessão, permissão, recurso e organização.
- [ ] Lista, detalhe, mutação e agregação aplicam o mesmo escopo.
- [ ] Recurso ausente e fora do escopo não permitem enumeração.
- [ ] Menu, guard ou campo oculto não são tratados como controle soberano.
- [ ] Operação privilegiada preserva segregação de função e auditoria.

## Navegador, resposta e arquivos

- [ ] Conteúdo não confiável é exibido como texto ou sanitizado com teste.
- [ ] Respostas e erros não expõem segredos, caminhos ou detalhes internos.
- [ ] Download usa tipo, nome e conteúdo controlados.
- [ ] Exportações neutralizam fórmulas e conteúdo ativo.
- [ ] Cache, CORS e headers são compatíveis com a sensibilidade da resposta.

## Estado, concorrência e abuso

- [ ] Mutações possuem versão, idempotência ou conflito definido.
- [ ] Retry não duplica importação, relatório, notificação ou decisão.
- [ ] Limites de frequência, tamanho, custo e concorrência foram considerados.
- [ ] Falha parcial preserva estado transacional e histórico anterior.
- [ ] Eventos e métricas permitem diagnosticar bloqueio e recuperação.

## Evidência e governança

- [ ] O risco correspondente em `security-risk-register.json` foi atualizado.
- [ ] O controle possui teste de sucesso, erro, permissão e escopo aplicável.
- [ ] A telemetria e os artefatos foram verificados contra dados sensíveis.
- [ ] Dependência ou configuração nova possui origem, versão e risco avaliados.
- [ ] Risco adiado registra etapa, responsável e condição de retomada.
- [ ] Correção de vulnerabilidade inclui regressão automatizada quando viável.

## Assistência de IA

- [ ] As doze ameaças R-32–R-43 têm origem, fronteiras, prevenção, detecção,
  testes nomeados e risco residual atualizados; executar o validador do threat model.
- [ ] Campos livres persistidos não entram no contexto; saída segue contrato,
  referências autorizadas e interpolação como texto, sem ferramentas/escrita.
- [ ] Endpoint fixo, pin e limites permanecem validados; proxy/redirect são
  recusados também com transporte real de teste.
- [ ] POST e GET são autorizados no backend por organização; a sonda exige
  Bearer técnico antes de acessar o runtime. Capability não concede permissão.
- [ ] Timeout/cancelamento não provocam retry cego; reserva obsoleta não conclui
  após recuperação. Suspender em todas as instâncias antes da recuperação.
- [ ] Flags, código e contexto não viram labels de alta cardinalidade; nenhum
  prompt/contexto/saída vai para log, métrica ou projeção de auditoria.
- [ ] Readiness e jornadas principais continuam com runtime indisponível;
  kill switch de geração preserva leitura autorizada e dados de negócio.
- [ ] Alerta tem runbook específico, disparo/recuperação testados e tratamento
  de falta de medição; outbox/HTTP aceito não são recibo de indexação Graylog.
- [ ] Testes com runtime controlado não são apresentados como prova de qualidade
  de modelo real ou aceite produtivo da #192.
