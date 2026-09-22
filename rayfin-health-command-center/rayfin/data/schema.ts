import { KpiSnapshot } from './KpiSnapshot.js';
import { SeriesPoint } from './SeriesPoint.js';
import { WorklistRow } from './WorklistRow.js';
import { SyncRun } from './SyncRun.js';

export type AppSchema = {
    KpiSnapshot: KpiSnapshot;
    SeriesPoint: SeriesPoint;
    WorklistRow: WorklistRow;
    SyncRun: SyncRun;
};
