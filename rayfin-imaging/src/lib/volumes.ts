import type { AppFunctionsSchema } from '../../rayfin/functions/src/types';
import { getRayfinClient } from '@/services/rayfin/RayfinClientService';

export type VolumeCatalog = AppFunctionsSchema['getVolumeCatalog']['output'];
export type VolumeStudy = VolumeCatalog['studies'][number];
export type VolumeLayer = VolumeStudy['layers'][number];
export type FolderAccess = VolumeCatalog['access'];

export async function fetchVolumeCatalog(): Promise<VolumeCatalog> {
  return getRayfinClient().functions.getVolumeCatalog.invoke(undefined, { timeoutMs: 60_000 });
}

/** App route for a study. */
export function studyPath(study: Pick<VolumeStudy, 'id'>): string {
  return `/volumes?study=${encodeURIComponent(study.id)}`;
}

/** URL for a file under Files/volumes, signed with the catalog's read-only SAS. */
export function volumeUrl(access: FolderAccess, path: string): string {
  return `${access.baseUrl}/${path}?${access.query}`;
}

/** The file a layer shows for the current timeline frame (or its static file). */
export function layerFile(study: VolumeStudy, layer: VolumeLayer, frameIndex: number): string | undefined {
  if (layer.file) return layer.file;
  const frame = study.timeline?.frames[frameIndex];
  return layer.frameKey && frame ? frame.layers[layer.frameKey] : undefined;
}

export function frameBytes(study: VolumeStudy, frameIndex: number): number {
  const frame = study.timeline?.frames[frameIndex];
  return frame && frame.bytes ? frame.bytes : study.sizeBytes;
}

export function formatMb(bytes: number): string {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : `${(bytes / 1e6).toFixed(1)} MB`;
}
