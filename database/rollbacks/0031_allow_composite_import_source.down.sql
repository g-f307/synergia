DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM synergia.executions WHERE source = 'WO Status')
        OR EXISTS (SELECT 1 FROM synergia.source_files WHERE source = 'WO Status')
        OR EXISTS (
            SELECT 1 FROM synergia.file_inspections WHERE source = 'WO Status'
        )
    THEN
        RAISE EXCEPTION
            'Existem execuções, arquivos ou inspeções da fonte WO Status';
    END IF;
END
$$;

ALTER TABLE synergia.file_inspections
    DROP CONSTRAINT file_inspections_source_check,
    ADD CONSTRAINT file_inspections_source_check
        CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS'));

ALTER TABLE synergia.source_files
    DROP CONSTRAINT source_files_source_check,
    ADD CONSTRAINT source_files_source_check
        CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS'));

ALTER TABLE synergia.executions
    DROP CONSTRAINT executions_source_check,
    ADD CONSTRAINT executions_source_check
        CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS'));
