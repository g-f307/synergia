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
