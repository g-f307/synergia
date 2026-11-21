-- Expands finding title/explanation grammar in ai_assistance_result_shape_valid
-- to accept fact-grounded triage findings alongside legacy 1.0.0 templates (#226).
CREATE OR REPLACE FUNCTION synergia.ai_assistance_result_shape_valid(document jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    item jsonb;
    ref jsonb;
    triage_title_re CONSTANT text :=
        '^(Pendência (aberta|registrada): (aging|container_impact|long_term_hold|missing_reason|oqc_hold|oqc_pass|oqc_pending|post_release_hold|pre_release_pending|rework|ship_block|source_divergence)|Pendência aberta em (Qualidade|Produção|Logística|Suprimentos|Governança de Dados)(: (aging|container_impact|long_term_hold|missing_reason|oqc_hold|oqc_pass|oqc_pending|post_release_hold|pre_release_pending|rework|ship_block|source_divergence))?|Divergência \((error|warning)\): (duplicate_record|empty_file|inconsistent_quantity|invalid_date|invalid_format|invalid_header|invalid_number|invalid_quantity|invalid_sheet|invalid_type|invalid_value|missing_required_column|missing_required_value|missing_sheet|quantity_mismatch|required_field|source_divergence|unknown_column)|Divergência \((error|warning)\) em (file|structure|record)|Classificação ativa: (aging|container_impact|long_term_hold|missing_reason|oqc_hold|oqc_pass|oqc_pending|post_release_hold|pre_release_pending|rework|ship_block|source_divergence)|Classificação \((active|closed)\): (aging|container_impact|long_term_hold|missing_reason|oqc_hold|oqc_pass|oqc_pending|post_release_hold|pre_release_pending|rework|ship_block|source_divergence))$';
    triage_explanation_re CONSTANT text :=
        '^((Registro|[23] registros) de pendência (open|resolved|cancelled)( na regra (aging|container_impact|long_term_hold|missing_reason|oqc_hold|oqc_pass|oqc_pending|post_release_hold|pre_release_pending|rework|ship_block|source_divergence))?( sob responsabilidade de (Qualidade|Produção|Logística|Suprimentos|Governança de Dados))?( na Workorder [A-Za-z0-9._:/-]{1,64})?( com aging( máximo)? de [0-9]{1,5} dias)?( e impacto em container)? (disponível|disponíveis) para conferência\.|(Divergência|[23] divergências) de severidade (error|warning) no escopo (file|structure|record)( com código (duplicate_record|empty_file|inconsistent_quantity|invalid_date|invalid_format|invalid_header|invalid_number|invalid_quantity|invalid_sheet|invalid_type|invalid_value|missing_required_column|missing_required_value|missing_sheet|quantity_mismatch|required_field|source_divergence|unknown_column))?( na Workorder [A-Za-z0-9._:/-]{1,64})? (disponível|disponíveis) para conferência\.|(Classificação|[23] classificações) (active|closed)( na regra (aging|container_impact|long_term_hold|missing_reason|oqc_hold|oqc_pass|oqc_pending|post_release_hold|pre_release_pending|rework|ship_block|source_divergence))?( sob responsabilidade de (Qualidade|Produção|Logística|Suprimentos|Governança de Dados))?( na Workorder [A-Za-z0-9._:/-]{1,64})?( com aging( máximo)? de [0-9]{1,5} dias)?( e impacto em container)? com qualidade de dados (complete|partial) (disponível|disponíveis) para conferência\.)$';
BEGIN
    IF document IS NULL THEN RETURN true; END IF;
    IF jsonb_typeof(document) IS DISTINCT FROM 'object'
       OR NOT (document ?& ARRAY['assistance_id','execution_id','state','summary',
           'findings','human_checks','limitations','provenance','created_at'])
       OR document - ARRAY['assistance_id','execution_id','state','summary',
           'findings','human_checks','limitations','provenance','created_at'] <> '{}'::jsonb
       OR jsonb_typeof(document->'findings') IS DISTINCT FROM 'array'
       OR jsonb_typeof(document->'human_checks') IS DISTINCT FROM 'array'
       OR jsonb_typeof(document->'limitations') IS DISTINCT FROM 'array'
       OR jsonb_typeof(document->'provenance') IS DISTINCT FROM 'object'
       OR jsonb_typeof(document->'summary') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'assistance_id') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'execution_id') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'created_at') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'state') IS DISTINCT FROM 'string'
       OR document->>'assistance_id' !~ '^[0-9a-f-]{36}$'
       OR document->>'execution_id' !~ '^[0-9a-f-]{36}$'
       OR document->>'created_at' !~ '^[0-9T:.+Z-]{20,40}$'
       OR document->>'state' NOT IN ('ready', 'insufficient_evidence', 'rejected')
       OR document::text ~* '(password|secret|bearer|token|eyJ[A-Za-z0-9_-]{10})'
    THEN RETURN false; END IF;
    IF document->>'summary' NOT IN (
        'Os fatos autorizados estão disponíveis para conferência humana.',
        'As evidências disponíveis são insuficientes.',
        'A resposta gerada foi recusada pela validação.'
    ) AND document->>'summary' !~
       '^(A execução registra|Foram registrados) [0-9]{1,19} (erro|erros), [0-9]{1,19} (aviso|avisos) e [0-9]{1,19} (pendência|pendências)\.( Referências disponíveis: (DIV|PEN|CLA|EVI|HIS)-[a-f0-9]{32}(, (DIV|PEN|CLA|EVI|HIS)-[a-f0-9]{32}){0,2}\.)?$'
    THEN RETURN false; END IF;
    IF NOT (document->'provenance' ?& ARRAY['contract_version','model','digest',
            'context_hash','prompt_hash','origin','timings'])
       OR (document->'provenance') - ARRAY['contract_version','model','digest',
            'context_hash','prompt_hash','origin','timings'] <> '{}'::jsonb
       OR jsonb_typeof(document->'provenance'->'timings') IS DISTINCT FROM 'object'
       OR NOT (document->'provenance'->'timings' ?& ARRAY['context_ms','generation_ms','total_ms'])
       OR (document->'provenance'->'timings') - ARRAY['context_ms','generation_ms','total_ms'] <> '{}'::jsonb
       OR jsonb_typeof(document->'provenance'->'model') NOT IN ('string', 'null')
       OR jsonb_typeof(document->'provenance'->'digest') NOT IN ('string', 'null')
       OR jsonb_typeof(document->'provenance'->'context_hash') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'provenance'->'prompt_hash') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'provenance'->'origin') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'provenance'->'contract_version') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'provenance'->'timings'->'context_ms') IS DISTINCT FROM 'number'
       OR jsonb_typeof(document->'provenance'->'timings'->'generation_ms') IS DISTINCT FROM 'number'
       OR jsonb_typeof(document->'provenance'->'timings'->'total_ms') IS DISTINCT FROM 'number'
       OR (document->'provenance'->>'model' IS NOT NULL AND
           document->'provenance'->>'model' !~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$')
       OR (document->'provenance'->>'digest' IS NOT NULL AND
           document->'provenance'->>'digest' !~ '^sha256:[a-f0-9]{64}$')
       OR document->'provenance'->>'context_hash' !~ '^[a-f0-9]{64}$'
       OR document->'provenance'->>'prompt_hash' !~ '^[a-f0-9]{64}$'
       OR document->'provenance'->>'contract_version' <> '1.0.0'
       OR document->'provenance'->>'origin' NOT IN ('model', 'deterministic')
    THEN RETURN false; END IF;
    FOR item IN SELECT * FROM jsonb_array_elements(document->'findings') LOOP
        IF jsonb_typeof(item) IS DISTINCT FROM 'object'
           OR NOT (item ?& ARRAY['title','explanation','evidence_refs'])
           OR item - ARRAY['title','explanation','evidence_refs'] <> '{}'::jsonb
           OR jsonb_typeof(item->'evidence_refs') IS DISTINCT FROM 'array'
           OR jsonb_typeof(item->'title') IS DISTINCT FROM 'string'
           OR jsonb_typeof(item->'explanation') IS DISTINCT FROM 'string'
           OR (
               item->>'title' NOT IN ('Registros disponíveis', 'Registros para conferência',
                   'Divergência registrada', 'Pendência registrada', 'Classificação registrada',
                   'Evidência registrada', 'Transição registrada')
               AND item->>'title' !~ triage_title_re
           )
           OR (
               item->>'explanation' NOT IN ('Há um registro disponível para conferência.',
                   'Há registros disponíveis para conferência.',
                   'Os registros estão disponíveis para conferência.')
               AND item->>'explanation' !~ triage_explanation_re
           )
        THEN RETURN false; END IF;
        IF jsonb_array_length(item->'evidence_refs') NOT BETWEEN 1 AND 3
        THEN RETURN false; END IF;
        FOR ref IN SELECT * FROM jsonb_array_elements(item->'evidence_refs') LOOP
            IF jsonb_typeof(ref) IS DISTINCT FROM 'string'
               OR (ref #>> '{}') !~ '^(DIV|PEN|CLA|EVI|HIS)-[a-f0-9]{32}$'
            THEN RETURN false; END IF;
        END LOOP;
    END LOOP;
    FOR item IN SELECT * FROM jsonb_array_elements(document->'human_checks')
                UNION ALL SELECT * FROM jsonb_array_elements(document->'limitations') LOOP
        IF jsonb_typeof(item) IS DISTINCT FROM 'string' OR (item #>> '{}') NOT IN (
            'A conferência humana das evidências é necessária.',
            'Conferência humana das referências disponíveis.',
            'Conferência humana das evidências disponíveis.',
            'O contexto possui seções truncadas.', 'A execução terminou com falha.',
            'Há dados ausentes ou indisponíveis no contexto.',
            'As evidências disponíveis são insuficientes.',
            'Assistência gerada por IA: pode conter erros. A conferência humana das evidências é necessária.'
        ) THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END $$;
