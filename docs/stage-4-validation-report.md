# Relatório de validação da Etapa 4

## Resultado

A Etapa 4 foi validada sobre os contratos reais da aplicação, PostgreSQL 16 e
massas exclusivamente sintéticas. A jornada automatizada parte da autenticação,
processa a planilha homologada, gera um relatório persistido, consulta seu
snapshot, exporta o CSV produzido pelo servidor e conclui uma decisão humana
auditável. Notificações internas e a entrega externa em captura local são
verificadas como consequência dos mesmos eventos.

Nenhum serviço corporativo, dado pessoal real ou mock de API participa do fluxo
principal. O adaptador de e-mail escreve somente em arquivo temporário da
execução e usa o identificador da entrega como chave de idempotência.

## Cenário ponta a ponta

1. O operador autentica, envia as fixtures N-FP e GMES/OQC e acompanha a
   execução persistida.
2. O gestor da mesma organização gera e visualiza o relatório correspondente.
   O CSV baixado é comparado com os identificadores persistidos e inspecionado
   contra injeção de fórmula.
3. O operador envia uma pendência para análise. Um gestor distinto atribui,
   devolve com justificativa, recebe o reenvio e aprova com consentimento
   explícito. O histórico completo permanece visível.
4. A central interna persiste leituras individuais e em lote. As preferências
   de canal são desativadas, recarregadas do servidor e reativadas.
5. O worker de e-mail é executado duas vezes sobre a captura local. A evidência
   confirma destinatários sintéticos, ausência de segredos e uma única mensagem
   por `delivery_id`.
6. Uma conta de outra organização comprova que busca e recursos privados não
   atravessam o escopo autorizado. A revogação de sessão também é exercitada.

## Cobertura complementar

Os testes HTTP e PostgreSQL cobrem os ramos que não devem ser fabricados na
demonstração feliz: relatório parcial e falho, exportação com conteúdo perigoso,
preferência desabilitada, falha temporária do provedor, rejeição, ausência de
justificativa, autoaprovação, falta de permissão, acesso entre organizações,
concorrência otimista e tentativa de decisão com sessão inválida.

O Playwright executa ainda a jornada em inglês e viewport móvel, navegação por
teclado e Axe para violações sérias ou críticas. Logs de console e respostas da
API são examinados contra JWT, hash de senha, caminhos internos e outros dados
sensíveis.

## Evidências reproduzíveis

O job `Banco e dados sintéticos` publica `fluxo-web-e2e`, contendo o relatório
HTML, vídeos quando habilitados, capturas, resultados Axe, o CSV exportado e a
captura local de e-mail. A preparação e a reprodução local estão descritas em
[web-e2e-demonstration.md](web-e2e-demonstration.md).

As quatro barreiras obrigatórias permanecem na CI: Angular, FastAPI, PostgreSQL
com dados sintéticos e preservação do protótipo. A entrega não declara RPA,
conectores corporativos ou capacidades planejadas para a Etapa 5.

## Decisão

Os critérios da Etapa 4 estão atendidos e possuem evidência automatizada,
auditável e reproduzível.
