# Segurança ofensiva e portão de release

## Escopo e segurança operacional

A suíte da issue #92 é executada apenas em runner efêmero, banco descartável e
dados sintéticos. O DAST recusa destinos diferentes de HTTP em loopback; ele
nunca deve ser apontado para homologação compartilhada ou produção. Tokens,
cookies, credenciais e payloads não são gravados nos relatórios. Os artefatos
publicados contêm somente identificadores de verificações, componentes, versões,
severidade e estado.

O gate cobre XSS/reflexão, injeção no login e exposição de erro externamente. A
suíte FastAPI existente complementa essa execução com SQL parametrizado,
mass-assignment, IDOR/BOLA, isolamento horizontal e vertical, path traversal,
uploads com macro, script, HTML ou MIME divergente, fórmula perigosa, tokens
expirados/adulterados/revogados, logout, refresh replay, concorrência de sessão e
usuário desativado. SSRF permanece não aplicável enquanto não houver entrada de
URL consumida pelo servidor, conforme o modelo de ameaças.

## Dependências, imagens, segredos e SBOM

A CI executa `pip-audit` para Python, `npm audit` para Node e Trivy para sistema
de arquivos, dependências e configurações de imagens. O SBOM CycloneDX inclui as
distribuições Python efetivamente instaladas, o lockfile Node e as imagens-base
de Docker. O scanner de segredos possui detectores positivos testados e examina
o conteúdo versionável, ignorando dependências, caches e os próprios relatórios.

Achado confirmado `high` ou `critical` bloqueia a CI. Uma exceção só é válida se
estiver em `security-release-policy.json` com responsável, justificativa,
mitigação e expiração futura. Depois da correção, o achado deve ser marcado como
`fixed` e retestado; falso positivo usa a mesma decisão temporal e auditável.

## Evidências reproduzíveis

O job `Segurança ofensiva e cadeia de dependências` publica por 14 dias:

- relatório DAST sanitizado;
- resultados normalizados de dependências Python e Node;
- relatório SARIF/JSON do scanner de imagem e filesystem;
- varredura de segredos;
- SBOM CycloneDX;
- resultados JUnit da regressão ofensiva.

As versões dos scanners ficam registradas no log e nos metadados dos relatórios.
O mesmo gate pode ser reproduzido com `python scripts/security_release.py
validate`; o DAST exige uma API descartável em execução e o argumento `--target`.
