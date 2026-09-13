# Resposta a abuso e rate limiting

## Responsável e escalonamento

Segurança lidera; plataforma atua em proxy/rede e aplicação valida falso
positivo. Indício de credencial comprometida é incidente de segurança.

## Pré-condições

- operação e dimensão agregadas identificadas nas métricas;
- configuração de proxy confiável confirmada;
- hashes de sujeito, IP ou identificador não são copiados para evidências.

## Procedimento

1. Confirmar volume, rota agrupada e período do alerta.
2. Verificar implantação ou cliente legítimo que explique o aumento.
3. Revogar sessões comprometidas e aplicar controle de borda quando autorizado.
4. Ajustar limites somente por mudança revisada; nunca desabilitar globalmente
   durante um incidente.
5. Após o prazo aprovado, aplicar retenção de `security_transient`.

## Rollback

Remover bloqueios de borda temporários quando a taxa normalizar. Restaurar a
configuração versionada se o ajuste causar negação indevida, preservando os
eventos agregados.

## Validação e evidências

Confirmar queda das negações, login legítimo e isolamento entre dimensões.
Registrar regra, intervalo, decisão e correlation IDs, nunca dados de origem.
