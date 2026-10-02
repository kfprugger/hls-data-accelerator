import { PublishedSnapshot } from './PublishedSnapshot.js';
import { SyncRun } from './SyncRun.js';
import { SnapshotWriter } from './SnapshotWriter.js';
import { KpiSnapshot } from './KpiSnapshot.js';
import { SeriesPoint } from './SeriesPoint.js';
import { WorklistRow } from './WorklistRow.js';

export type AppSchema = {
    PublishedSnapshot: PublishedSnapshot;
    SyncRun: SyncRun;
    SnapshotWriter: SnapshotWriter;
    /** Retained read-only legacy tables; the dashboard never reads them. */
    KpiSnapshot: KpiSnapshot;
    SeriesPoint: SeriesPoint;
    WorklistRow: WorklistRow;
};
