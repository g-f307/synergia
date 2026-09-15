-- Consolidados filtram uma Workorder e uma execução, ordenando por id.
-- O índice anterior (execution_id, rule_id, result) não cobre esse acesso.
CREATE INDEX idx_rule_evaluations_workorder_execution_id
    ON synergia.rule_evaluations (workorder_id, execution_id, id);

COMMENT ON INDEX synergia.idx_rule_evaluations_workorder_execution_id IS
    'Acesso seletivo e ordenado às avaliações de regras do consolidado por Workorder/execução';
