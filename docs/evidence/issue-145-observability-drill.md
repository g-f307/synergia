# Evidência sanitizada — issue #145

## Exercício executado

- cenário: indisponibilidade controlada do armazenamento;
- ambiente: teste automatizado, diretório temporário, sem rede e sem dados do
  cliente;
- baseline: `GET /health/ready` retorna `200` e `ready`;
- falha: escrita da sonda negada de forma controlada e o mesmo endpoint retorna
  `503` e `not_ready`;
- recuperação: bloqueio removido e o endpoint volta a `200` e `ready`;
- resultado: recuperação comprovada.

O teste executável é
`test_storage_probe_controlled_failure_and_recovery`. Ele valida a sequência
`baseline -> failure -> recovery` usando as respostas reais do endpoint e falha
se o estado final não for saudável. Essa evidência não afirma exercício de
PostgreSQL ou SMTP/worker, teste do destino corporativo nem aprovação de SLO.

## Controles verificados

- contrato, alertas, links de runbook e painéis são validados em conjunto;
- readiness trata banco e armazenamento como dependências obrigatórias;
- rejeição válida, falha sistêmica e orçamento de recurso têm leituras
  separadas;
- estimativa e orçamento de memória usam o mesmo modelo por ingestão;
- allowlist de logs não aceita credenciais, tokens, payload, conteúdo de célula
  ou caminho interno.

## Portões externos remanescentes

- escolha e credenciais do destino corporativo;
- retenção e grupos de acesso corporativos;
- baseline medida na infraestrutura de homologação;
- SLOs e escalonamento nominal aprovados pelos responsáveis.
