# Calibração local das PoCs — issue #148

Estado: calibração encerrada, somente `development`. Configurações selecionadas
antes da primeira inferência reservada no protocolo `1.2.0-frozen`. Este documento
preserva as descobertas e tentativas; a decisão depende da avaliação final.

## Método

- Partida: prompts históricos, Qwen3 4B Q4_K_M, thinking desativado, contexto
  4096, geração 2048, temperatura zero, seeds 125/126 e aceleração automática.
- Três repetições por arquivo/caso e um aquecimento separado. Baseline executa
  exatamente os mesmos casos. Falhas e respostas rejeitadas são preservadas.
- Variar um fator por variante: prompt, thinking, perfil CPU/GPU ou modelo.
  Configurações posteriores têm novo identificador e snapshot. Não reexecutar
  tentativas para substituir uma falha ou editar rótulos após observar saídas.
- Probes limitados de capacidade devem ser identificados como tal: só sustentam
  conclusões sobre o caso e o orçamento observados, sem extrapolar F1/latência
  ao conjunto completo. Comparações de latência usam o mesmo caso/configuração.
- Comparações entre rodadas com código diferente precisam explicitar a mudança;
  a rodada final deverá congelar todos os candidatos antes de medir o reservado.
- O texto livre exige revisão factual. Schema, códigos e IDs corretos não
  demonstram ausência de alucinação ou utilidade além do baseline.

## Descobertas durante a primeira rodada

O primeiro teste completo usa os prompts históricos. No desenvolvimento de
qualidade, uma saída de `QD3-D02.csv` passou no contrato e nos códigos esperados,
mas descreveu `8.0` como quantidade inválida. Esse valor pertence ao registro
normalizado da linha 3, enquanto a ocorrência `invalid_quantity` aponta à linha
2. O contexto não fornece o valor inválido da linha 2; não é lícito substituí-lo
pelo valor válido de outra linha. O artefato original será preservado.

Outra limitação observada: o modelo produziu `completed` e nenhuma pergunta
para códigos desconhecidos ou referência ausente, apesar de categorias e
confiança baixas corretas. O validador recusou essas respostas como
`unsupported_certainty`; elas não contam como sucesso nem são reparadas.

Essas observações justificam uma variante de prompt que explicite o vínculo por
posição e a regra de abstenção, sem inserir rótulos dos casos nem executar a
classificação no lugar do modelo. Thinking e alternativa maior serão fatores
separados caso a alteração de prompt seja insuficiente.

## Evidências

Artefatos brutos locais: `.test-tmp/issue-148/block3/` (ignorado pelo Git).
Os resumos sanitizados e hashes serão registrados no checkpoint do bloco.
Não há dados reais, acesso a serviços corporativos ou integração com o produto.

O primeiro ciclo de qualidade terminou com 12/24 respostas aceitas e 12 recusas
`unsupported_certainty`; schema válido em todas, F1 estrutural aceito 0,5714.
No operacional inicial foram observadas consultas repetidas, filtros que omitem
pendência crítica e ausência de resposta final. Os tokens de entrada medidos
nessas tentativas ficaram abaixo do contexto 4096 e não houve violação de
recursos. Isso motiva primeiro revisar prompt/terminação; não prova que um
modelo maior resolverá o ciclo nem que hardware é o fator causal principal.

## Descoberta de variante e compatibilidade

Em 29/10/2026, o digest instalado `359d7dd4bcda...` da tag genérica `qwen3:4b`
corresponde também a `qwen3:4b-thinking-2507-q4_K_M` na
[lista oficial de tags](https://ollama.com/library/qwen3/tags). A
[ficha do publicador](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507) declara
suporte apenas a thinking. As duas primeiras rodadas usaram `think=false`, como
previsto no ponto inicial do protocolo, e são controles de configuração
incompatível com o modo recomendado pelo publicador. Seus resultados continuam
registrados, mas não sustentam rejeição geral do modelo Thinking nem promoção
dessa combinação para a avaliação final.

Foi adicionado um bloqueio de seleção final para modos incompatíveis registrados
no protocolo. Desenvolvimento continua permitindo reproduzir o controle negativo.
A alternativa explícita
[`qwen3:4b-instruct-2507-q4_K_M`](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M)
tem cerca de 2,5 GB, Q4_K_M e Apache-2.0. Sua
[ficha oficial](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) especifica modo
sem thinking. A comparação de pesos/variante será registrada separadamente da
alteração de prompt. Não se aumenta o contexto para 256K: permanece 4096.

## Probe de CPU versus aceleração

Mesmo caso `development/QD3-D02.csv`, pesos/digest, prompt histórico, temperatura,
seed, contexto e orçamento. Foram feitos um aquecimento e três chamadas medidas
por perfil, descarregando apenas o modelo desta PoC antes de cada perfil.
Ollama confirmou `size_vram=0` no perfil CPU e `2727346175` bytes no automático.
Chamadas aquecidas: CPU 31,392 / 31,255 / 31,310 s; automático 10,968 / 10,992 /
11,110 s. Nenhum limite de recurso foi ultrapassado.

Esse probe mede capacidade/latência pontuais da configuração original, incluindo
o controle com thinking desligado. Não é uma avaliação completa de qualidade,
uma garantia para outros modelos/casos ou repetição do notebook anterior. Os
resultados não serão usados como prova de fidelidade do texto. Os downloads
maiores começaram somente após a conclusão dos dois perfis.

## Preparação dos modelos públicos

A instalação normal pelo Ollama falhou na conexão IPv6 do serviço com o endpoint
de pesos (`connect: permission denied`), embora o manifesto fosse acessível.
O teste IPv4 obteve HTTP 206 para os primeiros 16 bytes do mesmo blob público.
A alternativa baixa blobs do registro oficial por IPv4, verifica tamanho e
SHA-256, envia-os pela [API de blobs documentada](https://github.com/ollama/ollama/blob/main/docs/api.md#push-a-blob)
e conclui o pull do manifesto oficial. A instalação só é aceita se o digest
local do manifesto coincide com o SHA-256 do manifesto oficial baixado.

Não foi alterada configuração global de rede ou do serviço. URLs temporárias
assinadas não são registradas. Somente os arquivos temporários criados pelo
procedimento são removidos depois da importação verificada. Os logs de instalação
são locais e sanitizados. A referência Qwen2.5 3B continua restrita à pesquisa;
esta preparação não aprova sua licença para uso produtivo.

## Rodada exploratória com pesos compatíveis

As configurações `*-instruct-control-development` preservam os prompts históricos;
`*-instruct-prompt-development` mudam somente o prompt na mesma variante Instruct.
Ambas usam uma passagem completa do desenvolvimento (8 arquivos de qualidade e
4 casos operacionais), com um aquecimento separado. Essa passagem exploratória
não permite medir consistência de três repetições: a métrica fica indisponível,
sem converter ausência de repetições em zero ou 100%. A rodada reservada continua
exigindo pelo menos três repetições para cada configuração selecionada.

A referência `*-historical-control-development` usa o Qwen2.5 3B e os prompts
históricos nesta máquina e no runtime atual, nos mesmos casos de desenvolvimento.
Não é uma reprodução exata do experimento antigo: datasets e runtime diferem.
Controles do 4B Thinking com modo desligado ficam identificados separadamente.
As métricas não são misturadas para fabricar uma média favorável.

O download do histórico 3B ainda estava em andamento quando começou a rodada
exploratória do Instruct. Essa concorrência é registrada como possível influência
sobre carga/latência/telemetria; não se usa essa rodada para alegar causalidade
isolada de desempenho entre pesos. Qualidade e seleção de ferramentas continuam
avaliadas em todos os casos. A comparação pontual CPU/GPU anterior foi concluída
antes dos downloads grandes, e a rodada final deverá ocorrer sem concorrência.

## Interrupção e nova condição isolada

A rodada exploratória concorrente foi interrompida pelo limite global de swap:
referência de 1,3 MB e pico de 295,7 MB, superior ao crescimento permitido de
256 MiB. A execução operacional permaneceu incompleta (3/4 casos medidos), com
uma falha de recurso retida. Não foi relaxado limite ou substituído resultado.
O cgroup do serviço não tinha teto de RAM e registrou swap próprio zero na
inspeção posterior; esse dado não permite atribuir a variação global ao modelo.

A condição seguinte iniciou um protocolo de calibração 1.1.0, sem downloads ou
testes concorrentes, com configurações identificadas e todos os casos novamente
previstos. Não é um retry seletivo do caso que falhou; a rodada anterior continua
incompleta nas evidências. Versões anteriores do protocolo foram arquivadas e
conferidas contra seus hashes congelados. Novos snapshots incorporam o corpo
inteiro do protocolo e usam seu orçamento congelado em todas as tentativas.

O prompt `quality-v3.1.txt` torna explícita a diferença entre `occurrence_code`
literal e `category`, sem inserir IDs, dados ou respostas do reservado. O Instruct
passou no contrato em 8/8 arquivos, com F1 de códigos/categorias 1,0, mas só 6/8
casos integralmente corretos: persistiu abstenção indevida no cenário com campos
inválidos. O texto consultado já não atribuiu o valor 8.0 da linha válida ao erro.
Isso é melhora parcial, não meta integral atingida. O operacional Instruct
completou 4/4, mas a escolha correta de ferramentas ficou em 0,7083.

## Probe do modo Thinking compatível

O mesmo modelo instalado foi testado com `think=true`, prompt explícito e
orçamento inicial 2048, em `QD3-D02.csv`: aquecimento e uma tentativa medida.
Ambos consumiram todos os 2048 tokens, com `done_reason=length`, sem JSON final.
As falhas ficaram registradas como `invalid_json` e truncamento. Isso comprova
insuficiência desse orçamento observado, não incapacidade geral do modelo.
Nenhum texto de raciocínio privado foi armazenado. A avaliação do 8B está
condicionada ao probe real de memória, com os mesmos limites de recursos.

## Variante de qualidade com política guiada

`quality_policy_guided` é uma arquitetura experimental nomeada, separada de
`free_contract`. O código deriva de ocorrências já fornecidas apenas o status
da política e os limites de `open_questions`; esses campos restringem a
decodificação JSON antes da geração. O schema exibido ao modelo corresponde ao
schema usado pelo runtime. Não há reparo posterior, fallback ou acesso ao gold.
Uma resposta que viola o schema restrito é recusada e permanece como falha.

Classificação, códigos, confiança, escolha de evidências, explicação, hipótese e
orientação humana continuam tarefas do modelo e podem falhar. As métricas mostram
`deterministic_guided_fields` e `case_correct_scope=pipeline_with_deterministic_status`.
Não se atribui ao modelo o status imposto pelo código. Precisão factual e utilidade
do texto continuam dependendo de revisão, mesmo se a saída estruturada melhorar.


## Encerramento e seleção para o reservado

A exploração foi encerrada por decisão do responsável nesta conversa. Não será
aberta outra variação de modelo/prompt a partir dos resultados reservados.
O [registro do checkpoint 3](evidence/issue-148-checkpoint-3.json) inclui **43
execuções**, inclusive baselines, rodadas incompletas e falhas, e quatro probes.
Os artefatos brutos permanecem ignorados; seus hashes constam do registro.

| Variante confirmada no desenvolvimento | Tentativas medidas | Resultado | Média / P95 |
| --- | --- | --- | --- |
| Qualidade 4B Instruct, política guiada e contexto de evidências v1 | 24, 8 arquivos de 4 cenários | aceitação, F1 estrutural e consistência estrutural 100% | 9,242 / 15,492 s |
| Operacional 8B, ferramentas nativas, término explícito e guarda contextual | 12, 4 cenários | aceitação e escolha de ferramentas 100%; igualdade integral de JSON 50% | 27,262 / 42,147 s |

O contexto de qualidade v1 remove os registros normalizados válidos e conserva
contagens/ocorrências, reduzindo confusão entre linhas. A política determina
`status` e limites de perguntas **antes da geração**; não lê o gold nem repara
respostas. O modelo ainda produz classificação, referências e prosa. Persistiu
uma hipótese de omissão intencional sem evidência, apesar da instrução contrária;
isso exige revisão textual, mesmo com acerto estrutural total.

No operacional, o modelo escolhe consultas nativas e o sinal `finish_collection`;
a resposta final é gerada uma vez a partir dos resultados consultados. A guarda
restringe status/perguntas somente após a leitura de execução parcial com todas
as contagens zeradas. Foi aplicada em 3/12 tentativas de desenvolvimento e não
é crédito de raciocínio independente do modelo. JSONs diferentes entre repetições
podem conter paráfrases; 50% de igualdade textual não demonstra, por si só,
inconsistência semântica nem autoriza declarar consistência semântica aprovada.

Foram preservadas variantes malsucedidas: ferramentas nativas com resposta final
como função, término natural seguido de JSON e término explícito sem guarda.
A rodada `wave8` falhou no despacho do executor, **antes de qualquer inferência**;
a falha foi corrigida com testes de execução completa pelas fábricas de runtime.
Esses registros são falhas de infraestrutura, sem atribuição ao modelo. Rodadas
seguintes possuem novos snapshots e não substituem os registros anteriores.

O probe do 8B confirmou execução híbrida CPU/GPU: alocação de modelo aproximada
5,99 GB, com 2,72 GB na VRAM. Na confirmação operacional, RSS somado atingiu
5,02 GB e uso total da GPU, incluindo desktop, 2,93 GB. Portanto, 4 GiB é piso
experimental observado com offload, e não garantia de residência integral ou
capacidade produtiva. Para comparar classe 7B/8B com maior margem, preferir GPU
com pelo menos 8 GiB. Não houve instalação de hardware nem integração ao produto.

A avaliação final seleciona **um candidato por proposta e seu baseline**, com
três repetições, mesmos casos e hashes. A comparação adicional de qualidade com
8B foi descartada ao encerrar a exploração: não foi executada nem será apresentada
como resultado. O histórico 3B foi medido nesta máquina, mas sua licença permanece
restrita à referência de pesquisa. O controle 1B instalado não foi avaliado.
