# Roteiro narrado — demonstração geral do SYNERGIA

Preparado em 07/11/2026. Duração principal: **19 minutos**, com aproximadamente
**4 minutos e 20 segundos dedicados ao Agente de qualidade**.

Este roteiro considera a API `0.11.0`, a base local `9226374` e os ajustes locais
de apresentação solicitados: nome **Agente de qualidade** e comparação com o
baseline oculta. Esses ajustes de apresentação ainda não estão versionados.
Antes de gravar, confirme qual revisão e quais ajustes compõem a versão exibida.

As falas abaixo são um texto de apoio: use linguagem natural e narre durante os
cliques. Os tempos incluem navegação e esperas, não apenas leitura. Um ensaio
cronometrado é necessário para ajustar o ritmo do apresentador e a latência do
ambiente. O público presumido combina negócio, equipe técnica e avaliadores.

## 1. Mensagem central e percurso

Mensagem a transmitir:

> O SYNERGIA organiza a entrada de planilhas, torna o processamento e seus
> resultados rastreáveis e oferece informação para investigação e decisão
> humana. Cada pessoa acessa funções compatíveis com seu papel e organização.
> O Agente de qualidade acrescenta uma PoC de explicação assistida, com geração
> local e limites explícitos.

Use uma história única: **uma entrada de dados é processada, uma ocorrência é
investigada, uma pessoa decide e o resultado pode ser acompanhado e comunicado**.
Em seguida, apresente o agente em seus próprios cenários sintéticos. Ele ainda
não explica automaticamente os registros da importação mostrada antes.

| Tempo | Bloco | Conta em uso | Resultado que precisa aparecer |
| --- | --- | --- | --- |
| 00:00–00:45 | Abertura e propósito | Operador | Visão geral com dados sintéticos |
| 00:45–02:00 | Papéis e administração | Administrador | Usuários, grupos, papéis e escopos |
| 02:00–03:00 | Perfil, preferências e consulta | Consulta | Menu restrito, idioma, aparência e sessões próprias |
| 03:00–05:00 | Importação e validação | Operador | Fonte, envio, inspeção e resumo de processamento |
| 05:00–06:45 | Execuções e consulta operacional | Operador | Rastreabilidade e relações entre entidades |
| 06:45–08:45 | Pendências e decisão humana | Operador → Gestor | Submissão, atribuição, aprovação e histórico |
| 08:45–10:00 | Indicadores e Modo TV | Gestor | Visão consolidada e monitor em apresentação |
| 10:00–11:20 | Relatórios | Gestor | Geração, visualização e exportação |
| 11:20–12:05 | Notificações | Operador | Aviso interno e navegação ao recurso |
| 12:05–13:15 | Feedback e triagem | Operador → Gestor | Protocolo, transição e histórico |
| 13:15–17:35 | Agente de qualidade | Gestor | Duas gerações reais, evidências e limites |
| 17:35–18:35 | Sustentação técnica | Gestor / cartão de apoio | Arquitetura, auditoria e operação |
| 18:35–19:00 | Encerramento | Gestor | Síntese do percurso e estágio da PoC |

## 2. Preparação obrigatória antes do ensaio

### Estado verificado neste computador

Foi feito um diagnóstico somente de leitura na elaboração inicial, antes da
carga fictícia solicitada posteriormente:

| Item | Situação encontrada |
| --- | --- |
| Angular e API | Responderam em `localhost:4200` e `localhost:8000`; readiness HTTP 200 |
| Usuários e organizações | 4 usuários e 2 organizações cadastrados |
| Vínculos diretos de papel vigentes | Administrador, consulta, gestor e operador |
| Papel analista | O acesso efetivo por outros vínculos não foi inventariado; preparar uma conta se ele for demonstrado com login próprio |
| Execuções | 6 cadastradas; não foi conferido o conteúdo para uso em vídeo |
| Pendências, relatórios, aprovações e feedbacks | Nenhum registro cadastrado em cada uma dessas quatro áreas |
| Notificações | 4 cadastradas; conteúdo não foi conferido para uso em vídeo |

**Atualização: as pendências fictícias já foram criadas.** A carga técnica
`demo-video` processou quatro fontes sintéticas por organização: N-FP, OWM,
GMES/OQC e TMS. Foram criadas duas execuções concluídas, cada uma com 32 registros
válidos, oito Workorders, oito lotes, oito seriais e 20 pendências abertas.
A consulta utilizada pela aplicação confirmou os 20 itens por organização e o
isolamento entre os escopos. Usuários, senhas, papéis e execuções anteriores
foram preservados. Nenhuma solicitação de aprovação foi criada ou decidida.

| Massa atual | Organização principal | Segunda organização |
| --- | --- | --- |
| Organização | `syn-org-001` — operador e gestor existentes | `syn-org-002` — consulta existente |
| Prefixo dos dados | `DEMO-VIDEO-` | `DEMO-VIDEO-B-` |
| Pendências abertas | 20 | 20 |
| Prioridades | 4 críticas, 5 altas, 8 normais, 3 baixas | 4 críticas, 5 altas, 8 normais, 3 baixas |
| Execução | `5c323c8c-e0ff-44ad-81fd-6145598d6775` | `098bac33-90a1-4cf5-85d8-f47e972f85f8` |

Para a demonstração de aprovação, use a primeira organização, onde operador e
gestor já possuem seus papéis. Reserve, por exemplo:

- **Gravação:** pendência `2`, Workorder `DEMO-VIDEO-WO-001`,
  categoria `oqc_pending`, prioridade normal.
- **Ensaio:** pendência `3`, Workorder `DEMO-VIDEO-WO-002`,
  categoria `oqc_hold`, prioridade alta.
- **Consulta operacional:** `DEMO-VIDEO-WO-001`, `DEMO-VIDEO-LOT-001` e
  `DEMO-VIDEO-SN-001`.

Conta dedicada criada para a gravação: `gestor.video@example.invalid`, com
papel `gestor` somente em `syn-org-001`. Seu UUID, para colar no campo de
atribuição de aprovação, é `eb1deedc-2a3d-43db-8d3c-ce1e7283bf84`.
A senha foi fornecida separadamente ao responsável e não integra este roteiro.
A conta de gestor anterior foi preservada.

Os arquivos sintéticos e o inventário local estão em `.test-tmp/video-demo/`,
ignorados pelo Git. A autoria da carga é técnica; não apresente essas execuções
como uploads realizados pelo operador durante o vídeo.

Os relatórios de reserva já foram gerados com a conta `gestor.video@example.invalid`,
ambos na versão 1, concluídos e completos, com exportação CSV verificada:

- **Workorders consolidadas:** `/reports/5777fec4-0caf-4247-8a3e-f62dd0d6acf9`.
- **Resumo OQC:** `/reports/9f6c8901-f2a4-4cf6-ad0f-b63969f4d804`.

Também foram cadastrados dois feedbacks fictícios dessa mesma conta, visíveis
em **Meus feedbacks** e **Triagem de feedback**:

- **[DEMO] Salvar filtros favoritos** — Recebido; `/feedback/97433cc9-a494-4c83-9bb1-f2d45c6dc879`.
- **[DEMO] Exemplo ficticio de filtro de relatorios** — Em análise; `/feedback/e3b1afc0-2b59-4cf1-a910-80c576e64ac9`.

Esses exemplos são prévios e foram registrados pelo gestor, não pelo operador.
Para demonstrar ao vivo o percurso operador → gestor, crie outro feedback com a
conta de operador conforme o bloco 10. O bug de exemplo é explicitamente
fictício e não representa um defeito confirmado. Nenhuma aprovação foi iniciada.
Ainda faltam conferir a visibilidade das notificações, o acesso em cada janela
e o ensaio integral; essas etapas não estão declaradas como já concluídas.

### Contas e separação de papéis

Prefira um banco separado de demonstração e identidades claramente sintéticas.
Se usar o banco atual, prepare registros de demonstração sem apagar o histórico,
redefinir contas existentes ou ampliar o acesso do administrador.

| Papel | Capacidade inicial relevante | O que mostrar / explicar |
| --- | --- | --- |
| Administrador | Identidades, grupos, papéis, associações e templates | Não recebe funções de negócio automaticamente; mostrar o catálogo de permissões |
| Gestor | Supervisionar, importar, reprocessar, gerar/exportar relatórios, decidir aprovações e triar feedback | Conta principal da segunda metade do vídeo |
| Analista | Investigar, consultar artefatos e auditoria e exportar conteúdo autorizado | Não importa, reprocessa, gera relatórios nem decide aprovações por padrão |
| Operador | Importar, acompanhar processamento, consultar e submeter pendências | Conta principal do percurso operacional |
| Consulta | Indicadores, resultados operacionais e leitura de relatórios | Sem importação, reprocessamento, exportação de relatórios ou decisão |

Todos têm perfil e gestão das próprias sessões. O Agente de qualidade exige
`execution.read`: gestor, analista, operador e consulta o recebem inicialmente;
o administrador isolado não. O feedback próprio exige autenticação e vínculo
com **uma única organização**, inclusive para um administrador. Concessões
globais, sozinhas, não estabelecem esse vínculo.

Prepare operador e gestor como **pessoas diferentes na mesma organização
sintética**. O gestor deve ser elegível à política revisora `gestor` e ter as
permissões de aprovação no escopo correto. A atribuição usa o UUID interno do
responsável: deixe-o anotado para colar no formulário.

O código de organização observado numa planilha não substitui o vínculo IAM.
Confira a organização autorizada na importação e nos filtros, independentemente
do texto presente na coluna `organization_code` do arquivo sintético.

Use perfis separados do navegador para operador, gestor, administrador e
consulta. Várias abas do mesmo perfil compartilham o cookie de sessão; não
garantem identidades independentes. Faça os logins antes de começar a captura,
sem gravar a digitação de senhas. Para mostrar outro papel, alterne para a janela
identificada, sem simular que uma única pessoa possui todos os acessos.

### Massa e cenas a deixar prontas

Use somente arquivos sintéticos. Não selecione planilhas de `docs/files/` para
esta gravação. Os arquivos abaixo existem no repositório e são usados pela
jornada E2E versionada:

| Uso | Arquivo | Preparação |
| --- | --- | --- |
| Dados de planejamento | `data/synthetic/fixtures/minimal-comprehensive/n-fp.xlsx` | Importar antes, como N-FP; conferir autorização da aba `Synthetic` no ambiente de demonstração |
| Seriais e qualidade | `data/synthetic/fixtures/minimal-comprehensive/gmes-oqc.csv` | Importar antes, como GMES/OQC; conferir os resultados e as pendências geradas |
| Envio ao vivo | `data/synthetic/ingestion-v1/wo-composite.xlsx` | Selecionar WO Status; inclui linhas deliberadamente problemáticas |
| Família adicional | `data/synthetic/ingestion-v1/td-edge.xlsx` | Selecionar Total Decision; pode ficar previamente importado como exemplo de processamento parcial |

Os identificadores sintéticos `SYN-WO-000001`, `SYN-LOT-000001` e
`SYN-SER-00000001` estão nas massas de planejamento/qualidade. Confirme quais
resultados ficaram disponíveis e anote a execução e a organização certas antes
da filmagem. As fontes não devem ser apresentadas como automaticamente fundidas
em uma mesma execução quando foram importadas separadamente.

Prepare este conjunto mínimo:

- uma execução concluída ou concluída com erros, acessível às contas do vídeo;
- uma execução com registros normalizados, classificação e evidências visíveis;
- duas pendências abertas para reservar uma ao ensaio e outra à gravação;
- um relatório concluído de reserva e o UUID da execução para gerar outro;
- uma notificação interna visível ao operador;
- uma justificativa curta para submissão, atribuição e decisão;
- um título e uma descrição de feedback sintético, prontos para digitar ou colar;
- uma revisão publicada de template com prévia disponível ao administrador;
- URLs de reserva para execução, Workorder, pendência e relatório.

Uma aprovação terminal não deve ser reutilizada como se estivesse aberta. Uma
pendência reservada para o ensaio evita descobrir essa limitação durante o take.

O arquivo de envio ao vivo pode já ter sido importado durante o ensaio. Nesse
caso, a mensagem **Arquivo já importado** é o comportamento idempotente esperado:
use a fala alternativa do bloco 4 e abra o resultado existente. Renomear o
arquivo não muda o hash do conteúdo. Não apague registros ou volumes para
conseguir outra gravação.

Os fixtures têm datas históricas. Ajuste filtros para incluir os registros
preparados; nos relatórios, confirme que o instante de referência é posterior
aos dados que deseja mostrar. Não altere o relógio para produzir indicadores.

### Agente e condições de captura

- Abra `http://localhost:4200/ai/quality` com uma conta que tenha `execution.read`.
- Confira o nome **Agente de qualidade** e a ausência da comparação com baseline.
- Confirme a disponibilidade do modelo e o botão **Gerar explicação** habilitado.
- O backend deve estar no host com `SYNERGIA_AI_QUALITY_MODEL_ENABLED=true` e
  acesso ao Ollama no próprio loopback. O Compose padrão não fornece esse runtime.
- O contrato exige Ollama `0.40.12` e `qwen3:4b-instruct`, com o digest fixado em
  [ai-quality-ui.md](ai-quality-ui.md). Não troque o modelo para a gravação.
- Reserve **duas gerações**: `QE-A02` e `QE-A01`. A cota padrão é de três
  solicitações a cada 300 segundos; aguarde a janela após ensaios recentes.
- O cenário sem ocorrências não exige geração e não consome uma tentativa.
- Confira áudio em uma amostra de 20 segundos, janela legível em 1920 × 1080
  quando disponível, zoom consistente e cursor fácil de acompanhar.
- Feche avisos pessoais, preenchimento automático e abas alheias à apresentação.
  Prefira mostrar os arquivos já selecionados, sem filmar pastas privadas.
- Teste a retomada das janelas e a saída do Modo TV. Não confunda o botão de tela
  cheia com uma garantia de que a gravação continuará capturando a mesma região.

Os roteiros antigos de reconstrução e os bootstraps E2E não devem ser executados
indiscriminadamente no banco atual: alguns removem volumes ou redefinem contas
de teste. Este vídeo não precisa desse tipo de reconstrução.

## 3. Roteiro narrado de 19 minutos

### Bloco 1 — 00:00–00:45 — Abertura

**Tela:** operador, Visão geral, com dados sintéticos já disponíveis.

**Ações:** segure a imagem inicial, aponte o menu e os indicadores sem abrir
várias telas. Evite começar por um formulário de login.

**Narração sugerida:**

> Neste vídeo vou apresentar a versão atual do SYNERGIA e percorrer suas
> principais funções, desde a entrada de planilhas até a investigação dos
> resultados e a decisão humana. Também veremos como os papéis organizam o
> acesso e como a informação pode ser acompanhada e compartilhada. Na parte
> final, vou destacar o Agente de qualidade, nossa prova de conceito de
> explicação assistida por inteligência artificial. Toda a demonstração utiliza
> dados sintéticos.

**Ponto de saída:** o público entende o percurso e sabe que o agente terá um
bloco próprio, sem interpretar a tela como dados de produção.

### Bloco 2 — 00:45–02:00 — Papéis e administração

**Tela:** janela do administrador, `/admin`.

**Ações:** mostre a lista de usuários, abra uma identidade sintética e exiba seus
vínculos; passe pelas listas de grupos e papéis e abra as permissões de um papel.
Nos últimos segundos, abra o catálogo de templates e a prévia de uma revisão.
Não publique ou desative configurações durante esta passagem.

**Narração sugerida:**

> O sistema distribui as responsabilidades entre cinco papéis iniciais.
> O administrador cuida das identidades, dos grupos, dos papéis e dos escopos
> organizacionais. O gestor supervisiona a operação e possui ações como
> reprocessamento, geração de relatórios e decisão de aprovações. O analista
> investiga resultados e pode exportar conteúdo autorizado. O operador realiza
> a importação e acompanha o processamento. O perfil de consulta acessa as
> informações de leitura permitidas.
>
> As permissões efetivas dependem também da organização e dos vínculos de cada
> pessoa. O administrador não ganha acesso a todas as funções de negócio apenas
> pelo nome do papel. A administração também oferece versões de templates de
> notificação. Esta prévia permite conferir o conteúdo antes de uma publicação;
> abrir a prévia não envia uma mensagem.

**Ponto de saída:** os cinco papéis foram apresentados e a separação entre
administração de acesso e operação ficou visível.

### Bloco 3 — 02:00–03:00 — Perfil e experiência por usuário

**Tela:** janela da conta de consulta, `/profile`.

**Ações:** mostre o menu dessa conta, as preferências de idioma, fuso horário,
aparência e notificações. Alterne brevemente para inglês e retorne a português.
Mostre a lista de sessões próprias; apenas aponte as ações de encerramento.

**Narração sugerida:**

> Nesta conta de consulta, o menu acompanha os acessos permitidos. As funções
> de importação e administração não aparecem. Cada pessoa também possui um
> perfil com idioma, fuso horário e preferências de apresentação e notificações.
> Vou alternar o idioma para mostrar que os rótulos acompanham essa escolha.
>
> O perfil reúne ainda as sessões da própria pessoa e permite encerrar outra
> sessão ou as demais sessões. Durante esta gravação vou manter as conexões
> necessárias abertas. Essas preferências personalizam a experiência sem
> conceder novas permissões.

**Ponto de saída:** a conta continua autenticada e o idioma foi devolvido a pt-BR.

### Bloco 4 — 03:00–05:00 — Entrada de dados e validação

**Tela:** operador, `/imports/new`.

**Ações:** mostre as fontes disponíveis e os limites informados pela tela.
Selecione **WO Status**, escolha `wo-composite.xlsx` e envie. Abra o resultado e
aponte estado, linhas lidas, registros válidos/rejeitados e inspeções.
Mencione N-FP, OWM, TMS, GMES/OQC e Total Decision conforme o catálogo exibido;
não tente importar todas as famílias ao vivo.

**Narração sugerida:**

> A jornada começa com uma entrada controlada. Primeiro escolhemos a fonte,
> porque cada família possui um contrato de leitura e validação. O sistema
> informa os formatos aceitos e os limites antes do envio. Aqui vou usar uma
> planilha sintética da família WO Status. A aplicação também possui suporte
> às demais fontes apresentadas neste catálogo, incluindo Total Decision.
>
> Após o envio, o SYNERGIA inspeciona o arquivo, valida sua estrutura e os
> registros, normaliza os dados e executa o processamento. Esta massa contém
> problemas intencionais para tornar os controles visíveis. O processamento
> parcial preserva os resultados válidos e evidencia os registros rejeitados,
> em vez de esconder a qualidade da entrada.
>
> Agora podemos conferir as contagens e o estado obtido, além das inspeções.
> Esse registro identifica a execução correspondente e permite continuar a
> investigação sem depender de reabrir manualmente a planilha.

**Se aparecer “Arquivo já importado”, substitua a explicação do novo envio por:**

> Este conteúdo já foi registrado no ensaio. O sistema reconheceu a duplicidade
> pelo conteúdo e não iniciou outro processamento. Vou abrir o resultado
> existente para continuar. Assim também podemos observar a proteção contra
> importações duplicadas.

**Ponto de saída:** uma execução concreta está aberta. Se usar a alternativa,
não a descreva como uma importação recém-executada.

### Bloco 5 — 05:00–06:45 — Execuções e investigação operacional

**Tela:** operador, `/executions` e detalhe da execução.

**Ações:** filtre pela execução, abra o detalhe e passe pelas abas de resumo,
histórico, divergências, classificações e evidências que tiverem conteúdo.
Depois abra **Consulta operacional**, busque `DEMO-VIDEO-WO-001` e siga um vínculo
para lote ou serial previamente conferido. Volte pelo controle da própria tela.

**Narração sugerida:**

> O monitor reúne as execuções e permite localizar um processamento específico.
> Ao abrir seu detalhe, conseguimos acompanhar o estado, as contagens e o
> histórico. As abas organizam as informações necessárias à investigação,
> incluindo classificações, divergências e evidências disponíveis.
>
> A consulta operacional oferece outra entrada para os resultados persistidos.
> Vou buscar uma Workorder sintética que deixamos preparada e seguir seus
> relacionamentos com lote ou serial. Os vínculos ajudam a preservar o contexto
> entre o dado consultado, a execução e uma eventual pendência.
>
> A leitura também conserva a origem e a qualidade da informação. Uma
> quantidade ausente precisa continuar identificada como ausente. Acesso e
> escopo organizacional são verificados pelo servidor em cada consulta.
> O gestor também pode solicitar reprocessamento autorizado, preservando a
> rastreabilidade entre as tentativas; não executaremos essa ação neste percurso.

**Ponto de saída:** o público viu tanto a investigação por execução quanto a
consulta por identificador. Não misture entidades de execuções diferentes como
se fossem uma única consolidação.

### Bloco 6 — 06:45–08:45 — Pendência e decisão humana

**Tela:** operador, `/pending-items`, e depois gestor na mesma pendência.

**Ações:** filtre a pendência reservada, abra motivo, regra, prioridade e
proveniência. Submeta com a justificativa preparada. Na janela do gestor,
recarregue, atribua a solicitação ao gestor elegível, registre a justificativa
de decisão, marque o consentimento e aprove. Mostre o histórico final.

Textos sintéticos possíveis:

- Submissão: “Demonstração: encaminho a ocorrência para conferência das evidências.”
- Atribuição: “Demonstração: análise atribuída ao gestor responsável pela organização.”
- Decisão: “Demonstração: evidências sintéticas conferidas para registrar a decisão.”

**Narração sugerida:**

> As pendências tornam as ocorrências acionáveis. A fila permite organizar a
> investigação por prioridade, categoria e outros filtros. No detalhe,
> encontramos o motivo, a regra aplicada e as evidências que sustentam o
> resultado. Quando há necessidade de decisão humana, o usuário autorizado
> encaminha a pendência com uma justificativa.
>
> Vou alternar para uma segunda pessoa, com papel de gestor na mesma
> organização. A política exige que solicitante e decisor sejam diferentes.
> A solicitação precisa ser atribuída a um responsável elegível antes da
> decisão. Aqui registro a justificativa e o consentimento explícito.
>
> A aprovação fica no histórico, com seus participantes, horários e transições.
> O fluxo também suporta rejeição e devolução para correção, seguidas de reenvio
> quando aplicável. Neste vídeo vou concluir apenas o caminho de aprovação.
> A classificação automática permanece identificada, e a decisão humana possui
> seu próprio registro. Esse evento não comprova, por si só, uma liberação em
> sistemas externos.

**Ponto de saída:** estado aprovado e histórico visíveis. Se o botão de decisão
não aparecer, confira responsável atribuído, usuário, organização e estado;
não amplie papéis nem tente autoaprovar para salvar o take.

### Bloco 7 — 08:45–10:00 — Indicadores e Modo TV

**Tela:** gestor, `/dashboard`, depois `/tv`.

**Ações:** mostre organização/período, indicadores, quantidades e estados.
Abra um vínculo para os registros de origem. Entre no Modo TV pelo cabeçalho,
mostre os painéis de execuções e fontes e saia pelo botão da tela.

**Narração sugerida:**

> A visão geral reúne os indicadores produzidos a partir dos dados persistidos.
> Os filtros permitem delimitar a leitura e os vínculos conduzem aos registros
> relacionados, mantendo um caminho de investigação a partir do número exibido.
>
> Para acompanhamento em um monitor, o Modo TV oferece uma apresentação própria,
> com atualização periódica, estados das execuções e comparação entre fontes.
> A indicação de atualização ajuda a interpretar a referência temporal do painel.
> As informações continuam sujeitas às permissões da conta utilizada. Vou
> retornar à interface de trabalho para mostrar os relatórios.

**Ponto de saída:** saiu do Modo TV; não espere um ciclo automático completo se
isso consumir o tempo. Use os seletores dos painéis.

### Bloco 8 — 10:00–11:20 — Relatórios

**Tela:** gestor, `/reports`.

**Ações:** abra **Gerar relatório**, selecione **Workorders consolidadas** ou
**Resumo OQC**, escolha a organização e cole o UUID da execução preparada.
Confira o instante de referência, gere, abra a versão e exporte CSV. Deixe o
arquivo baixado aparecer na lista de downloads; não abra uma planilha externa
se isso atrapalhar a captura.

**Narração sugerida:**

> Os relatórios transformam resultados persistidos em snapshots consultáveis.
> A geração registra a execução, a organização e a referência temporal, além
> do tipo e dos filtros escolhidos. Podemos consultar Workorders consolidadas
> ou um resumo OQC, conforme a necessidade.
>
> Nesta versão conseguimos verificar o conteúdo, sua identificação e a
> indicação de completude. Uma execução com erros pode produzir um relatório
> parcial, preservando essa informação. O arquivo pode ser exportado nos
> formatos permitidos, de acordo com a permissão da pessoa. O analista também
> pode exportar relatórios autorizados; o perfil de consulta possui acesso de
> leitura, sem essa exportação por padrão.

**Ponto de saída:** uma versão concluída e um download. Se a geração demorar,
abra o relatório de reserva e diga que ele foi gerado previamente. Não prometa
uma ação web de criar nova versão se ela não estiver na tela: esse contrato
existe na API, mas a ação explícita na interface permanece pendente.

### Bloco 9 — 11:20–12:05 — Notificações

**Tela:** operador, caixa de notificações pelo cabeçalho.

**Ações:** abra uma notificação preparada, mostre seu conteúdo, marque como lida
e siga o vínculo quando ele existir. Aponte as preferências, sem desativar o
canal durante a demonstração.

**Narração sugerida:**

> As notificações internas comunicam eventos relevantes, como conclusão de
> execução, pendências e resultados de relatórios. A caixa pertence à pessoa
> autenticada e respeita tanto suas preferências quanto o acesso ao recurso.
> Aqui podemos registrar a leitura e seguir para o contexto relacionado.
>
> O sistema também possui um canal de e-mail configurável. Sua utilização depende
> do transporte e da configuração do ambiente; esta demonstração está mostrando
> a caixa interna, sem prometer um envio externo.

**Ponto de saída:** uma notificação realmente visível. Não espere um aviso
instantâneo sobre uma operação que não gerou evento novo, como upload duplicado.

### Bloco 10 — 12:05–13:15 — Feedback e triagem

**Tela:** operador, **Enviar feedback**; depois gestor, **Triagem de feedback**.

**Ações:** envie uma sugestão sintética, abra o protocolo e, no gestor, filtre o
mesmo registro, mude para **Em análise** e salve. Volte à janela do autor e
recarregue o detalhe para mostrar o histórico.

Texto preparado:

- Tipo: Sugestão de melhoria.
- Título: “[DEMO] Salvar filtros favoritos”.
- Descrição: “Registro sintético da demonstração: oferecer uma opção para guardar combinações de filtros utilizadas com frequência.”
- Justificativa da triagem: “Demonstração: sugestão encaminhada para análise.”

**Narração sugerida:**

> A versão atual também oferece um canal de feedback dentro da aplicação.
> A pessoa pode registrar um bug ou uma sugestão de melhoria e recebe um
> protocolo para acompanhar o registro. O conteúdo e o histórico ficam
> vinculados ao autor e ao escopo organizacional definido pelo sistema.
>
> Na conta do gestor, a triagem permite avaliar o feedback e registrar sua
> evolução. Vou colocar esta sugestão demonstrativa em análise e mostrar a
> atualização ao autor. O histórico preserva as transições e justificativas.
> Registrar um feedback aqui não cria automaticamente uma issue no GitHub.

**Ponto de saída:** protocolo e estado atualizado. Se a política informar vínculo
organizacional ausente ou ambíguo, ajuste as contas no preparo, não no take.

### Bloco 11 — 13:15–17:35 — Destaque: Agente de qualidade

**Tela:** gestor, `/ai/quality`. Faça este bloco com calma: ele é o destaque.

#### 13:15–14:00 — Apresentar propósito e separar os cenários

**Ações:** abra o módulo e aponte nome, indicação experimental, seletor e fatos.

**Narração sugerida:**

> Agora chegamos ao Agente de qualidade. A proposta desta prova de conceito é
> oferecer uma explicação textual orientada pelas evidências de qualidade e
> indicar verificações que uma pessoa pode realizar. A geração é feita
> localmente pelo Qwen3 de quatro bilhões de parâmetros, acessado pelo backend.
>
> Esta área usa cenários sintéticos próprios e controlados. Ela ainda não está
> conectada automaticamente aos dados da importação que acabamos de mostrar.
> Os fatos, códigos e localizações vêm de uma projeção determinística; a
> participação do modelo ocorre na explicação apresentada ao lado.

#### 14:00–15:15 — Mesmo código em duas posições

**Ações:** selecione **Mesmo código em duas posições** (`QE-A02`). Antes de gerar,
mostre as duas ocorrências, suas posições e o único diagnóstico agrupado.
Clique uma vez em **Gerar explicação**. Durante a espera, narre os controles.
Depois leia uma frase curta da resposta realmente obtida.

**Narração sugerida:**

> Neste primeiro exemplo, há ocorrências do mesmo código em posições diferentes.
> Elas permanecem agrupadas e suas evidências continuam visíveis. Vou solicitar
> a explicação. A resposta precisa respeitar um contrato e uma política factual
> restrita antes de ser apresentada como texto do modelo.
>
> Enquanto aguardamos, vale observar que o modelo não pode alterar o código,
> a severidade ou os valores da evidência. Também não recebe autorização para
> inventar uma causa. Ao terminar, a interface identifica a origem do texto,
> o estado da validação e o tempo observado. As verificações humanas aparecem
> junto à explicação para orientar a conferência da fonte.

**Frase de leitura:** cite somente o que apareceu. Se o resultado for fallback,
use a fala de contingência abaixo, sem chamá-lo de resposta aceita do Qwen.

#### 15:15–16:30 — Valor ausente e limite do conhecimento

**Ações:** selecione **Serial ausente na coluna B** (`QE-A01`). Mostre o estado de
valor desconhecido antes da segunda geração. Solicite a explicação e aponte a
abstenção quando a resposta terminar.

**Narração sugerida:**

> O segundo cenário trata de um serial ausente. A coluna B informa a posição
> do problema; ela não revela o serial que deveria estar preenchido. Esse limite
> precisa ser mantido na explicação.
>
> Vou gerar a resposta e conferir o que ela permite afirmar. A ausência continua
> explícita, e o texto informa que o valor não pode ser determinado pelas
> evidências disponíveis. A proposta é apoiar a leitura do problema com uma
> resposta controlada e verificações humanas. Descobrir ou preencher o valor
> correto continua dependendo da fonte e das pessoas responsáveis.

#### 16:30–17:00 — Cenário sem ocorrências

**Ações:** selecione **Arquivo sem ocorrências** (`QD3-E01`). Mostre a mensagem e
o botão de geração desabilitado; não tente uma terceira geração.

**Narração sugerida:**

> Neste cenário não há ocorrências detectadas. O sistema informa essa condição
> e não chama o modelo. Assim, a apresentação acompanha os fatos disponíveis,
> sem produzir uma explicação para um problema que não foi identificado.

#### 17:00–17:35 — Resumo honesto da PoC

**Ações:** mantenha o módulo aberto; use o último resultado apenas se for preciso
retornar a uma evidência. Não gere novamente para buscar uma resposta melhor.

**Narração sugerida:**

> Esta PoC já reúne geração local, validação e tratamento de falhas dentro da
> interface. Se a geração exceder o prazo ou não passar pela validação, o
> sistema apresenta um texto determinístico, identificado como fallback.
> A utilidade adicional do modelo ainda precisa de avaliação humana; não
> estamos afirmando um ganho de produtividade comprovado. A responsabilidade
> pela análise e pela decisão continua com as pessoas.

**Ponto de saída:** duas tentativas reais, estados corretamente identificados e
nenhuma promessa de decisão, correção automática ou integração com dados reais.

### Bloco 12 — 17:35–18:35 — Sustentação técnica

**Tela:** cartão de apoio com os termos abaixo ou o módulo ainda aberto.
Não abra terminais com ambiente, tokens ou conexões no meio da gravação.

Cartão sugerido:

```text
Interface Angular → API FastAPI → PostgreSQL e arquivos controlados
Permissões e organização → rastreabilidade → relatórios e auditoria
Operação: saúde dos serviços, logs estruturados, atualização e recuperação
IA experimental: Ollama local + Qwen fixado + validação + fallback
```

**Narração sugerida:**

> Por trás dessas jornadas, a interface Angular utiliza a API FastAPI, e o
> PostgreSQL mantém o estado persistente da aplicação. Os controles de acesso
> são aplicados no servidor. A solução também possui registros de auditoria,
> sinais de saúde e logs estruturados para apoio à operação.
>
> A consulta e exportação consolidadas de auditoria estão disponíveis na API;
> uma tela Angular específica ainda não faz parte desta versão. A operação
> também conta com procedimentos de backup e automação de atualização,
> verificação e rollback da aplicação, respeitando a compatibilidade do banco.
> Integrações corporativas e automações externas dependem de configuração e
> homologação próprias.

**Ponto de saída:** recursos técnicos foram contextualizados sem apresentá-los
como botões inexistentes nem afirmar implantação corporativa concluída.

### Bloco 13 — 18:35–19:00 — Encerramento

**Tela:** volte à Visão geral ou mantenha o título Agente de qualidade.

**Narração sugerida:**

> Percorremos a entrada controlada de dados, a investigação dos resultados,
> as decisões humanas, os indicadores, relatórios, notificações e feedbacks.
> Vimos os papéis de acesso e o Agente de qualidade experimental. Esse conjunto
> resume o estágio atual do SYNERGIA e os próximos passos de avaliação com
> os usuários.

## 4. Contingências durante a gravação

| Situação | Ação e fala fiel ao comportamento |
| --- | --- |
| Arquivo duplicado | Abrir o resultado existente. “O conteúdo já foi registrado; a duplicidade foi reconhecida e não houve novo processamento.” |
| Execução com erros | Mostrar as contagens e os motivos. “A execução preservou os registros aceitos e sinalizou as rejeições.” |
| Não há uma pendência elegível | Usar a segunda pendência preparada ou reagendar esse trecho. Não criar uma decisão fictícia. |
| Aprovação já terminal | Mostrar seu histórico como exemplo previamente registrado; usar outra pendência para uma transição ao vivo. |
| Relatório demorando | Abrir a versão de reserva e identificá-la como previamente gerada. Não declarar que o clique atual terminou. |
| Modelo indisponível antes da gravação | Corrigir o preparo antes do take. Se o trecho for mantido, mostrar a indisponibilidade real e explicar a dependência do runtime. |
| Fallback durante geração | “Nesta tentativa a resposta não ficou disponível ou não foi aceita. O sistema apresentou o texto determinístico e informou o motivo.” Ler o motivo efetivo da tela. |
| Geração demorando | Narrar evidências e controles enquanto o carregamento aparece. O prazo interativo total é 30 s por cenário; respeite o resultado observado. |
| Cota atingida | Aguardar a janela indicada e regravar o trecho. Não desativar a proteção nem repetir cliques. |
| Sessão expirada | Pausar a captura, autenticar novamente sem filmar senha e retomar com transição clara. |
| Feedback bloqueado por organização | Corrigir a preparação de vínculos. Não alterar permissões ou forjar uma organização no conteúdo enviado. |
| Pouco tempo disponível | Aplicar os cortes da seção seguinte. Preserve o bloco do agente e a separação entre classificação e decisão humana. |

Falas e cenários alternativos não devem ser montados para esconder um resultado
negativo. Se gravar em blocos, mantenha a coerência entre identificadores,
estados e histórico. Não acelere uma inferência e preserve a indicação do tempo
observado; uma edição de espera deve ser identificada.

## 5. Ajustes de duração

### Versão compacta — 15 minutos

Parta do roteiro de 19 minutos e faça estes cortes, que somam 4 minutos:

| Corte | Economia |
| --- | --- |
| Administração: mostrar papéis e uma identidade, sem percorrer grupos/templates | 30 s |
| Perfil: citar idioma, fuso e sessões, sem alterar preferências ao vivo | 30 s |
| Importação: mostrar fonte/arquivo e o resultado preparado, identificando-o como prévio | 45 s |
| Execuções/consulta: abrir apenas Workorder, citando lote e serial | 30 s |
| Aprovação: mostrar o histórico previamente realizado com duas pessoas, sem repetir a transição | 45 s |
| Relatórios: abrir o snapshot pronto e exportar, sem preencher o modal | 30 s |
| Sustentação técnica: usar apenas uma frase sobre arquitetura e auditoria | 30 s |

O bloco do agente continua com 4 min 20 s. Os demais módulos permanecem
representados; os trechos reduzidos passam a mostrar resultados previamente
preparados, sem serem apresentados como ações ao vivo.

### Versão estendida — até 20 minutos

Acrescente até 45 segundos ao roteiro principal para entrar com uma conta de
analista e mostrar a leitura/exportação de um relatório, sem acesso a importação
ou geração por padrão. Deixe os 15 segundos restantes como margem. Prepare essa
conta antes; não use a conta de consulta como se fosse analista.

Se a latência real já aproximar o vídeo de 20 minutos, não inclua esse adicional.

## 6. Cartão rápido do apresentador

```text
00:00  Propósito e percurso — dados sintéticos.
00:45  Admin — usuários, grupos, papéis; cinco responsabilidades; prévia de template.
02:00  Consulta — menu restrito, preferências e sessões próprias.
03:00  Operador — fonte, arquivo, inspeção e contagens; duplicidade é comportamento esperado.
05:00  Execução → histórico/evidências → Workorder/lote/serial.
06:45  Pendência → operador solicita → gestor atribui e decide → histórico.
08:45  Dashboard → origem dos números → Modo TV → sair.
10:00  Gestor — relatório → snapshot → exportar.
11:20  Operador — notificação → leitura → vínculo.
12:05  Feedback → protocolo → gestor tria → autor acompanha.
13:15  AGENTE — cenário sintético próprio; Qwen local; não usa a importação anterior.
14:00  Mesmo código em duas posições → gerar 1 → origem e validação.
15:15  Serial ausente → gerar 2 → limite do conhecimento.
16:30  Sem ocorrências → botão desabilitado → nenhuma chamada.
17:00  PoC, fallback identificado, utilidade ainda em avaliação.
17:35  Arquitetura, auditoria na API e operação — sem terminal nem segredos.
18:35  Recapitular e encerrar.
19:00  Fim planejado.
```

## 7. Checklist de liberação do take

- [ ] Revisão do código e ajustes locais usados no vídeo identificados.
- [ ] Contas sintéticas conferidas e sessões isoladas por perfil de navegador.
- [ ] Operador e gestor são pessoas diferentes no mesmo escopo.
- [ ] Idioma pt-BR, fuso e filtros adequados nas janelas principais.
- [ ] Arquivos sintéticos e acesso às abas/formato corretos.
- [ ] Execução, entidades relacionadas e duas pendências conferidas.
- [ ] UUID do gestor e justificativas disponíveis para colar.
- [ ] Relatório e notificação de reserva acessíveis às contas certas.
- [ ] Feedback com vínculo organizacional único e triagem autorizada.
- [ ] Agente com nome atual, comparação oculta e geração disponível.
- [ ] Duas tentativas de IA reservadas e cota livre após o ensaio.
- [ ] Áudio, captura, troca de janelas e saída do Modo TV ensaiados.
- [ ] Uma execução cronometrada completa ficou entre 15 e 20 minutos.
- [ ] Esperas, cortes e exemplos previamente preparados estão descritos com clareza.
- [ ] Nenhuma tela expõe credenciais, informação pessoal ou planilha real.

## 8. Referências verificadas

- [Mapa das rotas e exposição das capacidades](web-route-map.json).
- [Matriz de papéis e permissões](access-control-matrix.md).
- [Decisão humana e segregação](human-approvals.md).
- [Relatórios e limites de versionamento](reports.md).
- [Notificações internas](notifications.md).
- [Administração de templates e prévia sem envio](notification-template-administration.md).
- [Feedback, vínculo organizacional e triagem](product-feedback.md).
- [Agente de qualidade, modelo fixado e cotas](ai-quality-ui.md).
- [Auditoria disponível na API](audit-export.md).
- [Automação de atualização e recuperação](deploy-automation.md).
- [Jornada E2E operacional](../web/e2e/operational-flow.spec.ts).
- [Jornada E2E de feedback](../web/e2e/feedback.spec.ts).
- [Jornada E2E do agente](../web/e2e/ai-quality.spec.ts).

O código e os testes confirmam os percursos previstos. O diagnóstico desta
rodada confirmou a disponibilidade básica dos serviços e as lacunas da massa
local. A preparação dos dados e o ensaio integral do roteiro continuam sendo
etapas anteriores à gravação, não validações já concluídas por este documento.
