ALTER TABLE synergia.source_files
    ADD COLUMN source text;

UPDATE synergia.source_files sf
SET source = e.source
FROM synergia.executions e
WHERE e.id = sf.execution_id;

ALTER TABLE synergia.source_files
    ADD CONSTRAINT source_files_source_check
        CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS'));

CREATE INDEX idx_source_files_execution_source
    ON synergia.source_files (execution_id, source);

COMMENT ON COLUMN synergia.source_files.source IS
    'Fonte do arquivo dentro de uma execução que pode reunir múltiplas fontes';
