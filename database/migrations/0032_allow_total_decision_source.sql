-- Physical workbook family; canonical records retain the GMES/OQC source.
ALTER TABLE synergia.executions
    DROP CONSTRAINT executions_source_check,
    ADD CONSTRAINT executions_source_check
        CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS', 'WO Status', 'Total Decision'));
ALTER TABLE synergia.source_files
    DROP CONSTRAINT source_files_source_check,
    ADD CONSTRAINT source_files_source_check
        CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS', 'WO Status', 'Total Decision'));
ALTER TABLE synergia.file_inspections
    DROP CONSTRAINT file_inspections_source_check,
    ADD CONSTRAINT file_inspections_source_check
        CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS', 'WO Status', 'Total Decision'));
