# PoC do RPA de exportação do NFP

**Situação em 25/11/2026.** A PoC alcançou o relatório Production Plan [R+F] pelo portal e produziu duas planilhas locais. A conversão manual consolidou 3.245 registros. A homologação operacional continua aberta, principalmente pela composição do arquivo da NW5. Esta branch, `poc/rpa-nfp`, é um registro isolado de pesquisa e deve permanecer sem merge.

## Percurso e decisões

O objetivo foi testar a extração antes de propor um conector para o Synergia. O operador mapeou o percurso em 17 capturas ordenadas e forneceu trechos do HTML do portal, do aplicativo e dos botões. A referência inicial foi um template SCM para Windows. A adaptação para Linux usou Node.js, Playwright e Chrome com perfil temporário. O template original, os HTMLs de sessão e os dados operacionais ficam no ambiente local.

O protótipo local explorou o login pelo SSO, o fluxo de solicitação de OTP temporário e a leitura do desafio visual. Nos testes apareceram uma janela de autenticação em origem diferente da inicialmente prevista, um aviso de matrícula vazia e códigos temporários alfanuméricos. A investigação levou à identificação das janelas corretas, à reabertura limitada da solicitação quando a matrícula vinha vazia e a uma alternativa manual. O executor desta branch deixa a autenticação a cargo do operador no navegador. O restante do percurso começa quando o portal está disponível.

| Etapa | Comportamento observado e implementado |
| --- | --- |
| Portal e painel | O painel lateral pode iniciar recolhido. O robô abre **Unfold**, aciona **System Map** e aguarda o carregamento de **My System**. Se a lista já estiver aberta, evita fechá-la. |
| Escolha do sistema | Existem atalhos **N-FP (GERP)** e **N-FP (N-FP)**. O robô seleciona o primeiro e observa a navegação na aba atual ou em uma nova, distinguindo abas antigas. |
| Relatório | Em **Analysis**, o botão com o ícone `open_in_new` da linha **Production Plan [R+F]** abre a tela de consulta. A rota e o botão Search identificam o destino. |
| Filtro | A tela usa um campo Plant pesquisável do Quasar. O robô digita o código, identifica a lista pelo `aria-controls` dinâmico, seleciona a opção e confere o valor do campo. O padrão é NW1. Datas e demais filtros seguem os valores da tela. A possibilidade de antecipar a data inicial em um mês ficou para avaliação. |
| Busca e exportação | A grade pode continuar mostrando os resultados anteriores após a troca de plant. O robô clica em **Search**, observa o ciclo de carregamento ou a transição de disponibilidade de **Download** e espera os controles ficarem disponíveis. Salva o XLSX em uma pasta exclusiva por execução. A confirmação de carregamento pela interface ainda precisa ser confrontada com os dados do portal. |

O objetivo futuro abrange todas as opções Plant que começam com N. O piloto recebe uma plant NW com sufixo numérico por execução. O código da seleção é parte da proveniência. A coluna Plant de uma linha pode conter outro código, como já se observou na consulta manual de NW4.

## Reproduzir

A partir da raiz do repositório, use as dependências de `web/` (`npm ci --prefix web`, com a versão de Node indicada em `web/.nvmrc`), Chrome instalado e acesso autorizado ao portal. A janela aberta pelo comando recebe o login do operador.

```bash
node RPA/NFP/exportar.cjs --nwm5
```

`--nw5` é equivalente a `--nwm5`. Sem argumento o executor consulta NW1. O XLSX é salvo em `RPA/NFP/downloads/<plant>-<execução>/`. O utilitário `browser.cjs` permite apenas a inspeção da janela do navegador. Para repetir os testes de navegação e exportação em páginas sintéticas:

```bash
node --test RPA/NFP/navigation.test.cjs RPA/NFP/export.test.cjs
```

**Conversão manual.** Escolha explicitamente um XLSX por consulta que deseja consolidar. No exemplo, substitua os diretórios entre sinais de menor e maior pelos diretórios das execuções. Use Python com `openpyxl` instalado (na estação de teste, a versão foi 3.1.5).

```bash
backend/.venv/bin/python RPA/NFP/consolidar.py \
  'RPA/NFP/downloads/<execução-NW1>/Production_Plan_NW1.xlsx' \
  'RPA/NFP/downloads/<execução-NW5>/Production_Plan_NW5.xlsx' \
  --output RPA/NFP/downloads/production_plan_unificado.json
```

O conversor confere a integridade do XLSX, a aba, os cabeçalhos e a unicidade de Plant + Target ID no lote. Uma divergência interrompe a geração. A leitura percorre as linhas reais porque a dimensão declarada pelo exportador pode ser apenas A1. Cada registro inclui o arquivo de origem por ID, a linha, a plant declarada, o Target ID e as quantidades por dia. Cada fonte registra o hash SHA-256, a plant solicitada e as plantas encontradas. Datas permanecem em MM/DD, como no cabeçalho. Dias vazios são omitidos e zeros explícitos são preservados.

## Evidências e limites

| Exportação local | Detalhes | Subtotais excluídos | Observação |
| --- | ---: | ---: | --- |
| NW1 | 3.095 | 11 | 1.339 detalhes declaram NW1. O arquivo inclui outras sete plantas. |
| NW5 | 150 | 2 | A coluna Plant contém NW4 (63), NWU (58) e NWX (29). A relação com o filtro NW5 precisa de confirmação no NFP. |

Ambos os arquivos abriram com a aba esperada e as mesmas 182 colunas de datas. Os 3.245 detalhes têm chaves Plant + Target ID distintas no conjunto. Foram preservados 54 detalhes sem quantidades. As 13 linhas de subtotal continham fórmulas SUMIFS com o trecho `null:null` e foram excluídas do JSON. O cálculo oficial dos totais permanece pendente de validação.

Os 11 testes de navegador desta branch passaram em páginas sintéticas. Cobrem o painel recolhido ou aberto, atalhos ambíguos, aba de destino, seleção e download após a busca. Uma nova execução manual do conversor sobre os dois XLSX locais reproduziu integralmente os registros e as colunas de datas do JSON conferido anteriormente. Essa comparação cobre a conversão. Para homologar a origem ainda é preciso comparar o arquivo baixado com a consulta real do NFP para os mesmos filtros.

## Próximos passos

1. **Validar as planilhas baixadas.** Repetir NW1, NW4 e NW5 no portal, registrar filtros e período e confrontar a grade com o XLSX. Confirmar o agrupamento de plantas, os subtotais, as quantidades e a completude das datas com o responsável pelos dados.
2. **Corrigir as pendências do RPA NFP.** Investigar a seleção NW5 e a possibilidade de exportação de uma consulta anterior. Testar buscas rápidas, lentas e vazias, sessão expirada, download interrompido e seleções alfanuméricas. Só então ampliar a coleta para todas as plantas previstas.
3. **Migrar todo o RPA de Node para Python.** Portar a abertura do navegador, a navegação, os filtros, a espera, a exportação, o diagnóstico e os testes. Executar os mesmos cenários e comparar arquivos e resultados antes de substituir o executor.
4. **Automatizar a consolidação em JSON.** Disparar a validação após cada download concluído, definir quais arquivos pertencem à mesma rodada e tratar repetições, mudanças de layout e falhas parciais. Publicar o JSON com proveniência somente quando o lote cumprir os critérios aprovados.
5. **Elaborar e submeter à revisão o plano do conector NFP no Synergia.** Mapear o contrato de ingestão, autenticação suportada, execução agendada, deduplicação, retenção, auditoria e monitoramento. Apresentar alternativas, dependências, critérios de aceite e estratégia de homologação. A entrega dessa etapa é o plano revisado. A implementação dependerá de decisão posterior.
