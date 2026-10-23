-- A planilha WO Status reúne abas de várias fontes lógicas. O arquivo, a
-- inspeção e a execução registram a fonte composta; os registros normalizados
-- continuam usando apenas N-FP, OWM, GMES/OQC e TMS.

ALTER TABLE synergia.executions
    DROP CONSTRAINT executions_source_check,
    ADD CONSTRAINT executions_source_check
        CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS', 'WO Status'));

ALTER TABLE synergia.source_files
    DROP CONSTRAINT source_files_source_check,
    ADD CONSTRAINT source_files_source_check
        CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS', 'WO Status'));

ALTER TABLE synergia.file_inspections
    DROP CONSTRAINT file_inspections_source_check,
    ADD CONSTRAINT file_inspections_source_check
        CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS', 'WO Status'));
