# Evidência sanitizada — issue #145

## Exercício executado

- cenário: indisponibilidade controlada do armazenamento;
- ambiente: teste automatizado, diretório temporário, sem rede e sem dados do
  cliente;
- baseline: sonda de armazenamento saudável;
- falha: escrita da sonda negada de forma controlada e componente indisponível;
- recuperação: bloqueio removido e sonda novamente saudável;
- resultado: recuperação comprovada.

O teste executável é
`test_storage_probe_controlled_failure_and_recovery`. Ele valida a sequência
`baseline -> failure -> recovery` e falha se o estado final não for saudável.
Essa evidência não afirma teste do destino corporativo nem aprovação de SLO.

## Controles verificados

- contrato, alertas, links de runbook e painéis são validados em conjunto;
- readiness trata banco e armazenamento como dependências obrigatórias;
- rejeição válida, falha sistêmica e orçamento de recurso têm leituras
  separadas;
- memória observada é comparada ao orçamento efetivamente configurado;
- allowlist de logs não aceita credenciais, tokens, payload, conteúdo de célula
  ou caminho interno.

## Portões externos remanescentes

- escolha e credenciais do destino corporativo;
- retenção e grupos de acesso corporativos;
- baseline medida na infraestrutura de homologação;
- SLOs e escalonamento nominal aprovados pelos responsáveis.
