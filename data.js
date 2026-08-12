window.SYNERGIA_DATA = {
    meta: {
        synthetic: true,
        datasetLabel: 'Demonstração — dados sintéticos',
        lastUpdate: '2026-07-31T10:08:42',
        lastExecution: {
            id: 'EX-20260731-006',
            status: 'partial',
            statusLabel: 'Concluída com pendências'
        },
        duration: '08 min 42 s',
        nextExecution: '2026-07-31T16:00:00',
        scheduledTimes: ['10:00', '16:00'],
        environment: 'Demonstração'
    },

    sources: [
        { id: 'S1', name: 'GERP/OWM', status: 'available', items: 15420, lastUpdate: '2026-07-31T10:04:00', detail: 'Coleta simulada concluída' },
        { id: 'S2', name: 'N-FP', status: 'available', items: 890, lastUpdate: '2026-07-31T10:05:00', detail: 'Coleta simulada concluída' },
        { id: 'S3', name: 'WO Status', status: 'available', items: 5600, lastUpdate: '2026-07-31T10:06:00', detail: 'Arquivo sintético processado' },
        { id: 'S4', name: 'OQC', status: 'partial', items: 850, lastUpdate: '2026-07-31T10:07:00', detail: '12 registros sintéticos incompletos' },
        { id: 'S5', name: 'TMS', status: 'unavailable', items: 0, lastUpdate: '2026-07-30T16:08:00', detail: 'Fonte simulada indisponível' }
    ],

    workorders: [
        { id: 'WO-10293', lot: '4587', model: 'MOD-SYN-A55', suffix: 'AWF', plant: 'P1', line: 'L1', lotQty: 500, produced: 500, received: 500, released: 450, pendingProduction: 0, oqcPass: 480, oqcPending: 20, snOnHand: 50, hold: 20, holdReason: 'OQC Hold', oqcHold: 15, longTermHold: 0, rework: 5, shipBlock: 0, location: 'WMS-01', inventoryState: 'Good', container: 'CTN-2026-0451', source: 'GERP/OWM', evidenceDate: '2026-07-30', priority: 'critica', otd1: 1, status: 'pendente' },
        { id: 'WO-10294', lot: '4588', model: 'MOD-SYN-B65', suffix: 'BWF', plant: 'P1', line: 'L2', lotQty: 300, produced: 300, received: 300, released: 300, pendingProduction: 0, oqcPass: 300, oqcPending: 0, snOnHand: 0, hold: 0, holdReason: null, oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 0, location: 'WMS-02', inventoryState: 'Good', container: 'CTN-2026-0452', source: 'GERP/OWM', evidenceDate: '2026-07-30', priority: 'baixa', otd1: 3, status: 'concluida' },
        { id: 'WO-10295', lot: '4589', model: 'MOD-SYN-A55', suffix: 'AWF', plant: 'P1', line: 'L1', lotQty: 400, produced: 200, received: 150, released: 100, pendingProduction: 200, oqcPass: 100, oqcPending: 50, snOnHand: 50, hold: 10, holdReason: 'Rework', oqcHold: 0, longTermHold: 0, rework: 10, shipBlock: 0, location: 'PROD-01', inventoryState: 'Hold', container: null, source: 'WO Status', evidenceDate: '2026-07-31', priority: 'alta', otd1: 2, status: 'divergencia' },
        { id: 'WO-10296', lot: '4590', model: 'MOD-SYN-C65', suffix: 'CWF', plant: 'P2', line: 'L3', lotQty: 200, produced: 200, received: 200, released: 0, pendingProduction: 0, oqcPass: 0, oqcPending: 200, snOnHand: 200, hold: 200, holdReason: 'Ship Block', oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 200, location: 'WMS-03', inventoryState: 'Hold', container: 'CTN-2026-0453', source: 'GERP/OWM', evidenceDate: '2026-07-31', priority: 'media', otd1: 4, status: 'bloqueada' },
        { id: 'WO-10297', lot: '4591', model: 'MOD-SYN-B65', suffix: 'BWF', plant: 'P1', line: 'L2', lotQty: 600, produced: 0, received: 0, released: 0, pendingProduction: 600, oqcPass: 0, oqcPending: 0, snOnHand: 0, hold: 0, holdReason: null, oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 0, location: null, inventoryState: 'New', container: null, source: 'GERP/OWM', evidenceDate: '2026-07-31', priority: 'baixa', otd1: null, status: 'em_analise' },
        { id: 'WO-10298', lot: '4592', model: 'MOD-SYN-C55', suffix: 'CWF', plant: 'P2', line: 'L4', lotQty: 100, produced: 100, received: 100, released: 50, pendingProduction: 0, oqcPass: 90, oqcPending: 10, snOnHand: 50, hold: 5, holdReason: 'Long Term Hold', oqcHold: 0, longTermHold: 5, rework: 0, shipBlock: 0, location: 'WMS-04', inventoryState: 'Hold', container: 'CTN-2026-0454', source: 'N-FP', evidenceDate: '2026-07-29', priority: 'critica', otd1: 0, status: 'pendente' },
        { id: 'WO-10299', lot: '4593', model: 'MOD-SYN-D75', suffix: 'AWF', plant: 'P3', line: 'L5', lotQty: 800, produced: 800, received: 800, released: 800, pendingProduction: 0, oqcPass: 800, oqcPending: 0, snOnHand: 0, hold: 0, holdReason: null, oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 0, location: 'WMS-05', inventoryState: 'Good', container: 'CTN-2026-0455', source: 'GERP/OWM', evidenceDate: '2026-07-28', priority: 'baixa', otd1: 5, status: 'concluida' },
        { id: 'WO-10300', lot: '4594', model: 'MOD-SYN-D50', suffix: 'AWF', plant: 'P3', line: 'L6', lotQty: 450, produced: 400, received: 400, released: 350, pendingProduction: 50, oqcPass: 380, oqcPending: 20, snOnHand: 50, hold: 10, holdReason: 'Dados incompletos', oqcHold: 5, longTermHold: 0, rework: 5, shipBlock: 0, location: 'PROD-02', inventoryState: 'Hold', container: null, source: 'OQC', evidenceDate: '2026-07-31', priority: 'media', otd1: 2, status: 'divergencia' },
        { id: 'WO-10301', lot: '4595', model: 'MOD-SYN-E43', suffix: 'AWF', plant: 'P1', line: 'L1', lotQty: 1000, produced: 1000, received: 1000, released: 1000, pendingProduction: 0, oqcPass: 1000, oqcPending: 0, snOnHand: 0, hold: 0, holdReason: null, oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 0, location: 'WMS-06', inventoryState: 'Good', container: 'CTN-2026-0456', source: 'GERP/OWM', evidenceDate: '2026-07-27', priority: 'baixa', otd1: 10, status: 'concluida' },
        { id: 'WO-10302', lot: '4596', model: 'MOD-SYN-B65', suffix: 'BWF', plant: 'P1', line: 'L2', lotQty: 250, produced: 250, received: 250, released: 0, pendingProduction: 0, oqcPass: 250, oqcPending: 0, snOnHand: 250, hold: 250, holdReason: 'Ship Block', oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 250, location: 'WMS-02', inventoryState: 'Hold', container: 'CTN-2026-0457', source: 'GERP/OWM', evidenceDate: '2026-07-30', priority: 'alta', otd1: 1, status: 'bloqueada' },
        { id: 'WO-10303', lot: '4597', model: 'MOD-SYN-A55', suffix: 'AWF', plant: 'P1', line: 'L1', lotQty: 300, produced: 0, received: 0, released: 0, pendingProduction: 300, oqcPass: 0, oqcPending: 0, snOnHand: 0, hold: 0, holdReason: null, oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 0, location: null, inventoryState: 'New', container: null, source: 'GERP/OWM', evidenceDate: '2026-07-31', priority: 'media', otd1: null, status: 'em_analise' },
        { id: 'WO-10304', lot: '4598', model: 'MOD-SYN-C77', suffix: 'CWF', plant: 'P2', line: 'L3', lotQty: 50, produced: 50, received: 50, released: 45, pendingProduction: 0, oqcPass: 45, oqcPending: 5, snOnHand: 5, hold: 5, holdReason: 'OQC Hold', oqcHold: 5, longTermHold: 0, rework: 0, shipBlock: 0, location: 'OQC-01', inventoryState: 'Hold', container: 'CTN-2026-0458', source: 'GERP/OWM', evidenceDate: '2026-07-31', priority: 'critica', otd1: 0, status: 'pendente' },
        { id: 'WO-10305', lot: '4599', model: 'MOD-SYN-D75', suffix: 'AWF', plant: 'P3', line: 'L5', lotQty: 150, produced: 100, received: 80, released: 50, pendingProduction: 50, oqcPass: 70, oqcPending: 30, snOnHand: 30, hold: 15, holdReason: null, oqcHold: 0, longTermHold: 0, rework: 15, shipBlock: 0, location: 'PROD-03', inventoryState: 'Hold', container: null, source: 'WO Status', evidenceDate: '2026-07-31', priority: 'alta', otd1: 1, status: 'divergencia' },
        { id: 'WO-10306', lot: '4600', model: 'MOD-SYN-D50', suffix: 'AWF', plant: 'P3', line: 'L6', lotQty: 600, produced: 600, received: 600, released: 600, pendingProduction: 0, oqcPass: 600, oqcPending: 0, snOnHand: 0, hold: 0, holdReason: null, oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 0, location: 'WMS-07', inventoryState: 'Good', container: 'CTN-2026-0459', source: 'GERP/OWM', evidenceDate: '2026-07-29', priority: 'baixa', otd1: 6, status: 'concluida' },
        { id: 'WO-10307', lot: '4601', model: 'MOD-SYN-E43', suffix: 'AWF', plant: 'P1', line: 'L1', lotQty: 200, produced: 200, received: 200, released: 100, pendingProduction: 0, oqcPass: 180, oqcPending: 20, snOnHand: 100, hold: 50, holdReason: 'Long Term Hold', oqcHold: 0, longTermHold: 50, rework: 0, shipBlock: 0, location: 'WMS-08', inventoryState: 'Hold', container: 'CTN-2026-0460', source: 'N-FP', evidenceDate: '2026-07-30', priority: 'media', otd1: 2, status: 'pendente' }
    ],

    serials: [
        { serialNumber: 'SN-507ARLD12345', workorder: 'WO-10293', lot: '4587', model: 'MOD-SYN-A55', location: 'WMS-01', inventoryState: 'Hold', oqcApproval: 'Pending', holdReason: 'OQC Hold', oqcHold: 1, longTermHold: 0, rework: 0, shipBlock: 0, container: null, source: 'GERP/OWM', date: '2026-07-30T10:00:00' },
        { serialNumber: 'SN-507ARLD12346', workorder: 'WO-10293', lot: '4587', model: 'MOD-SYN-A55', location: 'WMS-01', inventoryState: 'Hold', oqcApproval: 'Pending', holdReason: 'OQC Hold', oqcHold: 1, longTermHold: 0, rework: 0, shipBlock: 0, container: null, source: 'GERP/OWM', date: '2026-07-30T10:01:00' },
        { serialNumber: 'SN-507ARLD12347', workorder: 'WO-10294', lot: '4588', model: 'MOD-SYN-B65', location: 'WMS-02', inventoryState: 'Good', oqcApproval: 'Pass', holdReason: null, oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 0, container: 'CTN-2026-0452', source: 'GERP/OWM', date: '2026-07-30T14:20:00' },
        { serialNumber: 'SN-507ARLD12348', workorder: 'WO-10294', lot: '4588', model: 'MOD-SYN-B65', location: 'WMS-02', inventoryState: 'Good', oqcApproval: 'Pass', holdReason: null, oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 0, container: 'CTN-2026-0452', source: 'GERP/OWM', date: '2026-07-30T14:21:00' },
        { serialNumber: 'SN-507ARLD12349', workorder: 'WO-10295', lot: '4589', model: 'MOD-SYN-A55', location: 'PROD-01', inventoryState: 'Hold', oqcApproval: 'Fail', holdReason: 'Rework', oqcHold: 0, longTermHold: 0, rework: 1, shipBlock: 0, container: null, source: 'WO Status', date: '2026-07-31T08:15:00' },
        { serialNumber: 'SN-507ARLD12350', workorder: 'WO-10296', lot: '4590', model: 'MOD-SYN-C65', location: 'WMS-03', inventoryState: 'Hold', oqcApproval: 'Pending', holdReason: 'Ship Block', oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 1, container: 'CTN-2026-0453', source: 'GERP/OWM', date: '2026-07-31T09:30:00' },
        { serialNumber: 'SN-507ARLD12351', workorder: 'WO-10298', lot: '4592', model: 'MOD-SYN-C55', location: 'WMS-04', inventoryState: 'Hold', oqcApproval: 'Pending', holdReason: 'Long Term Hold', oqcHold: 0, longTermHold: 1, rework: 0, shipBlock: 0, container: 'CTN-2026-0454', source: 'N-FP', date: '2026-07-29T11:45:00' },
        { serialNumber: 'SN-507ARLD12352', workorder: 'WO-10300', lot: '4594', model: 'MOD-SYN-D50', location: 'PROD-02', inventoryState: 'Hold', oqcApproval: 'Pending', holdReason: 'Dados incompletos', oqcHold: 1, longTermHold: 0, rework: 0, shipBlock: 0, container: null, source: 'OQC', date: '2026-07-31T07:10:00' },
        { serialNumber: 'SN-507ARLD12353', workorder: 'WO-10302', lot: '4596', model: 'MOD-SYN-B65', location: 'WMS-02', inventoryState: 'Hold', oqcApproval: 'Pass', holdReason: 'Ship Block', oqcHold: 0, longTermHold: 0, rework: 0, shipBlock: 1, container: 'CTN-2026-0457', source: 'GERP/OWM', date: '2026-07-30T16:50:00' },
        { serialNumber: 'SN-507ARLD12354', workorder: 'WO-10304', lot: '4598', model: 'MOD-SYN-C77', location: 'OQC-01', inventoryState: 'Hold', oqcApproval: 'Pending', holdReason: 'OQC Hold', oqcHold: 1, longTermHold: 0, rework: 0, shipBlock: 0, container: 'CTN-2026-0458', source: 'GERP/OWM', date: '2026-07-31T10:05:00' },
        ...Array.from({length: 22}, (_, i) => ({
            serialNumber: `SN-507ARLD${12355 + i}`,
            workorder: 'WO-10293',
            lot: '4587',
            model: 'MOD-SYN-A55',
            location: 'WMS-01',
            inventoryState: i % 2 === 0 ? 'Good' : 'Hold',
            oqcApproval: i % 2 === 0 ? 'Pass' : 'Pending',
            holdReason: i % 2 === 0 ? null : 'OQC Hold',
            oqcHold: i % 2 === 0 ? 0 : 1,
            longTermHold: 0,
            rework: 0,
            shipBlock: 0,
            container: null,
            source: 'GERP/OWM',
            date: '2026-07-30T11:00:00'
        }))
    ],

    executions: [
        { id: 'EX-20260731-006', start: '2026-07-31T10:00:00', end: '2026-07-31T10:08:42', duration: '08m 42s', type: 'automatica', result: 'parcial', attempt: 1, totalAttempts: 1, read: 22000, processed: 21988, rejected: 12, sources: [ { name: 'GERP/OWM', status: 'available', items: 15420, detail: 'Concluída' }, { name: 'OQC', status: 'partial', items: 850, detail: 'Dados parciais' }, { name: 'TMS', status: 'unavailable', items: 0, detail: 'Indisponível' } ], params: 'COLETA_COMPLETA' },
        { id: 'EX-20260731-005', start: '2026-07-31T11:20:00', end: null, duration: '-', type: 'manual', result: 'processando', attempt: 1, totalAttempts: 1, read: 5000, processed: 2500, rejected: 0, sources: [ { name: 'TMS', status: 'partial', items: 2500, detail: 'Em processamento' } ], params: 'REPROCESSAMENTO_TMS' },
        { id: 'EX-20260730-004', start: '2026-07-30T16:00:00', end: '2026-07-30T16:10:00', duration: '10m 00s', type: 'automatica', result: 'falha', attempt: 3, totalAttempts: 3, read: 0, processed: 0, rejected: 0, sources: [ { name: 'TMS', status: 'unavailable', items: 0, detail: 'Fonte indisponível' } ], params: 'COLETA_COMPLETA' },
        { id: 'EX-20260730-003', start: '2026-07-30T10:00:00', end: '2026-07-30T10:05:00', duration: '05m 00s', type: 'automatica', result: 'concluida', attempt: 1, totalAttempts: 1, read: 20000, processed: 20000, rejected: 0, sources: [ { name: 'GERP/OWM', status: 'available', items: 15000, detail: 'Concluída' } ], params: 'COLETA_COMPLETA' },
        { id: 'EX-20260729-002', start: '2026-07-29T16:00:00', end: '2026-07-29T16:06:00', duration: '06m 00s', type: 'automatica', result: 'concluida', attempt: 1, totalAttempts: 1, read: 21000, processed: 21000, rejected: 0, sources: [ { name: 'WO Status', status: 'available', items: 5500, detail: 'Concluída' } ], params: 'COLETA_COMPLETA' },
        { id: 'EX-20260729-001', start: '2026-07-29T10:00:00', end: '2026-07-29T10:05:30', duration: '05m 30s', type: 'automatica', result: 'concluida', attempt: 1, totalAttempts: 1, read: 20500, processed: 20500, rejected: 0, sources: [ { name: 'N-FP', status: 'available', items: 890, detail: 'Concluída' } ], params: 'COLETA_COMPLETA' },
        { id: 'EX-20260728-002', start: '2026-07-28T16:00:00', end: '2026-07-28T16:12:00', duration: '12m 00s', type: 'automatica', result: 'concluida', attempt: 1, totalAttempts: 1, read: 25000, processed: 25000, rejected: 0, sources: [ { name: 'Todas as fontes', status: 'available', items: 25000, detail: 'Concluída' } ], params: 'COLETA_COMPLETA' },
        { id: 'EX-20260728-001', start: '2026-07-28T10:00:00', end: '2026-07-28T10:08:00', duration: '08m 00s', type: 'automatica', result: 'concluida', attempt: 1, totalAttempts: 1, read: 22000, processed: 22000, rejected: 0, sources: [ { name: 'Todas as fontes', status: 'available', items: 22000, detail: 'Concluída' } ], params: 'COLETA_COMPLETA' },
        { id: 'EX-20260727-002', start: '2026-07-27T16:00:00', end: '2026-07-27T16:09:00', duration: '09m 00s', type: 'automatica', result: 'parcial', attempt: 1, totalAttempts: 1, read: 21500, processed: 21450, rejected: 50, sources: [ { name: 'OQC', status: 'partial', items: 100, detail: 'Dados parciais' } ], params: 'COLETA_COMPLETA' },
        { id: 'EX-20260727-001', start: '2026-07-27T10:00:00', end: '2026-07-27T10:05:00', duration: '05m 00s', type: 'automatica', result: 'concluida', attempt: 1, totalAttempts: 1, read: 20000, processed: 20000, rejected: 0, sources: [ { name: 'Todas as fontes', status: 'available', items: 20000, detail: 'Concluída' } ], params: 'COLETA_COMPLETA' }
    ],

    pendencies: [
        { id: 'P-0031', workorder: 'WO-10293', lot: '4587', model: 'MOD-SYN-A55', reason: 'Divergência de estoque', source: 'GERP/OWM', affectedQty: 20, aging: '2 dias', impact: 'alto', priority: 'alta', otd1: 1, responsible: 'Produção', container: null, status: 'aberta', datetime: '2026-07-29T10:00:00', partialData: false, description: 'Quantidade consolidada no GERP/OWM diverge da evidência física', history: [{ date: '2026-07-29T10:00:00', text: 'Pendência criada', icon: 'info' }, { date: '2026-07-30T09:00:00', text: 'Enviado para produção', icon: 'alert' }], relatedExecution: 'EX-20260729-001', estimatedRelease: '2026-08-01', sortingStatus: 'pending', evidence: null, actions: ['Investigar linha L1'] },
        { id: 'P-0032', workorder: 'WO-10295', lot: '4589', model: 'MOD-SYN-A55', reason: 'Hold sem motivo informado', source: 'WO Status', affectedQty: 10, aging: '1 dia', impact: 'critico', priority: 'critica', otd1: 2, responsible: 'Qualidade', container: null, status: 'nova', datetime: '2026-07-30T14:00:00', partialData: true, description: 'Registro de hold não possui reason code.', history: [{ date: '2026-07-30T14:00:00', text: 'Pendência identificada', icon: 'alert' }], relatedExecution: 'EX-20260730-003', estimatedRelease: null, sortingStatus: null, evidence: null, actions: ['Atualizar base WO Status'] },
        { id: 'P-0033', workorder: 'WO-10296', lot: '4590', model: 'MOD-SYN-C65', reason: 'Dados conflitantes entre fontes', source: 'GERP/OWM', affectedQty: 200, aging: '3 dias', impact: 'alto', priority: 'media', otd1: 4, responsible: 'Logística', container: 'CTN-2026-0453', status: 'em_analise', datetime: '2026-07-28T08:00:00', partialData: false, description: 'Estados divergentes entre GERP/OWM e base WO Status', history: [{ date: '2026-07-28T08:00:00', text: 'Criado', icon: 'info' }, { date: '2026-07-29T10:00:00', text: 'Em análise pela logística', icon: 'info' }], relatedExecution: null, estimatedRelease: '2026-08-02', sortingStatus: 'in_progress', evidence: 'email_log.pdf', actions: [] },
        { id: 'P-0034', workorder: 'WO-10300', lot: '4594', model: 'MOD-SYN-D50', reason: 'Serial não localizado', source: 'OQC', affectedQty: 10, aging: '4 horas', impact: 'medio', priority: 'baixa', otd1: 2, responsible: 'Produção', container: null, status: 'aberta', datetime: '2026-07-31T02:00:00', partialData: false, description: 'Seriais reportados não existem na base', history: [{ date: '2026-07-31T02:00:00', text: 'Criado', icon: 'info' }], relatedExecution: 'EX-20260731-006', estimatedRelease: '2026-07-31', sortingStatus: 'pending', evidence: null, actions: ['Re-scan'] },
        { id: 'P-0035', workorder: 'WO-10302', lot: '4596', model: 'MOD-SYN-B65', reason: 'Prazo OTD1 em risco', source: 'GERP/OWM', affectedQty: 250, aging: '5 dias', impact: 'critico', priority: 'critica', otd1: 1, responsible: 'Suprimentos', container: 'CTN-2026-0457', status: 'escalada', datetime: '2026-07-26T10:00:00', partialData: false, description: 'Carga bloqueada próximo ao vencimento.', history: [{ date: '2026-07-26T10:00:00', text: 'Aviso de prazo', icon: 'alert' }, { date: '2026-07-30T10:00:00', text: 'Escalado para gerência', icon: 'alert' }], relatedExecution: null, estimatedRelease: null, sortingStatus: 'escalated', evidence: null, actions: ['Contato com armador'] },
        { id: 'P-0036', workorder: 'WO-10304', lot: '4598', model: 'MOD-SYN-C77', reason: 'Divergência de estoque', source: 'GERP/OWM', affectedQty: 5, aging: '1 hora', impact: 'baixo', priority: 'baixa', otd1: 0, responsible: 'Qualidade', container: 'CTN-2026-0458', status: 'nova', datetime: '2026-07-31T05:00:00', partialData: false, description: 'OQC Hold incompatível.', history: [{ date: '2026-07-31T05:00:00', text: 'Identificado no GERP/OWM', icon: 'info' }], relatedExecution: 'EX-20260731-006', estimatedRelease: null, sortingStatus: null, evidence: null, actions: [] },
        { id: 'P-0037', workorder: 'WO-10298', lot: '4592', model: 'MOD-SYN-C55', reason: 'Dados conflitantes entre fontes', source: 'N-FP', affectedQty: 5, aging: '2 dias', impact: 'medio', priority: 'media', otd1: 0, responsible: 'Logística', container: 'CTN-2026-0454', status: 'resolvida', datetime: '2026-07-29T12:00:00', partialData: false, description: 'Corrigido via sistema', history: [{ date: '2026-07-29T12:00:00', text: 'Criado', icon: 'info' }, { date: '2026-07-31T06:00:00', text: 'Resolvido', icon: 'success' }], relatedExecution: null, estimatedRelease: '2026-07-31', sortingStatus: 'done', evidence: null, actions: [] },
        ...Array.from({length: 5}, (_, i) => ({
            id: `P-00${38 + i}`, workorder: 'WO-10305', lot: '4599', model: 'MOD-SYN-D75', reason: 'Timeout na conexão TMS', source: 'TMS', affectedQty: null, aging: '6 horas', impact: 'alto', priority: 'alta', otd1: null, responsible: 'TI', container: null, status: 'aberta', datetime: '2026-07-31T00:00:00', partialData: true, description: 'Fonte TMS indisponível para a coleta simulada', history: [{ date: '2026-07-31T00:00:00', text: 'Erro de conexão', icon: 'error' }], relatedExecution: 'EX-20260730-004', estimatedRelease: null, sortingStatus: 'pending', evidence: null, actions: ['Solicitar nova coleta']
        }))
    ],

    reports: [
        { id: 'REL-20260731-01', title: 'Resumo Diário de Produção', type: 'consolidado', datetime: '2026-07-31T10:12:00', execution: 'EX-20260731-006', period: '2026-07-30', dataStatus: 'parcial', status: 'gerado', needsReview: true },
        { id: 'REL-20260731-02', title: 'Status OQC', type: 'oqc_summary', datetime: '2026-07-31T10:14:00', execution: 'EX-20260730-004', period: '2026-07-30', dataStatus: 'completo', status: 'erro', needsReview: false },
        { id: 'REL-20260731-03', title: 'Pendências Abertas', type: 'pendencias', datetime: '2026-07-31T10:16:00', execution: 'EX-20260730-003', period: '2026-07-30', dataStatus: 'completo', status: 'gerado', needsReview: false },
        { id: 'REL-20260730-04', title: 'Resumo Diário de Produção', type: 'consolidado', datetime: '2026-07-30T16:12:00', execution: 'EX-20260727-002', period: '2026-07-29', dataStatus: 'parcial', status: 'gerado', needsReview: true },
        { id: 'REL-20260730-05', title: 'Status OQC', type: 'oqc_summary', datetime: '2026-07-30T16:14:00', execution: 'EX-20260728-001', period: '2026-07-29', dataStatus: 'completo', status: 'gerado', needsReview: false },
        { id: 'REL-20260731-06', title: 'Fechamento Semanal', type: 'consolidado', datetime: '2026-07-31T10:20:00', execution: null, period: 'Semana 30', dataStatus: 'parcial', status: 'pendente', needsReview: false }
    ],

    containers: [
        { id: 'CTN-2026-0451', workorder: 'WO-10293', serials: ['SN-507ARLD12345'], status: 'parcial', carrier: 'TransLog' },
        { id: 'CTN-2026-0452', workorder: 'WO-10294', serials: ['SN-507ARLD12347'], status: 'liberado', carrier: 'FastFrete' },
        { id: 'CTN-2026-0453', workorder: 'WO-10296', serials: ['SN-507ARLD12350'], status: 'bloqueado', carrier: 'Oceanic' },
        { id: 'CTN-2026-0457', workorder: 'WO-10302', serials: ['SN-507ARLD12353'], status: 'bloqueado', carrier: 'GlobalShip' },
        { id: 'CTN-2026-0458', workorder: 'WO-10304', serials: ['SN-507ARLD12354'], status: 'parcial', carrier: 'LogisMax' }
    ],

    alerts: [
        { type: 'unavailable', severity: 'error', message: 'Fonte TMS indisponível. A última coleta não foi concluída.', link: 'monitor.html', linkText: 'Ver detalhes' },
        { type: 'divergence', severity: 'alert', message: 'Divergência crítica no WO-10295 (base WO Status).', link: 'pendencias.html', linkText: 'Resolver' },
        { type: 'partial', severity: 'attention', message: 'A fonte OQC retornou 12 registros sintéticos incompletos.', link: 'monitor.html', linkText: 'Ver execução' },
        { type: 'overdue', severity: 'error', message: 'Pendência P-0035 com prazo OTD1 em risco (WO-10302).', link: 'pendencias.html', linkText: 'Verificar' }
    ]
};
