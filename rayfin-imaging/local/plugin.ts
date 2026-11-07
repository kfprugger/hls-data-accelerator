/**
 * Vite plugin for local mode (`npm run dev:local`). The dev server stands in for everything Fabric provides:
 *
 *   /local-api/getCohort, getPatient, getDataMap   the Rayfin functions, run with DuckDB (local/api.ts)
 *   /local-api/notes                               tumour board notes, kept in work/local/notes.json
 *   /local-files/<silo>/<path>                     the silos' Files areas (slides, volumes, PDFs) from work/
 */
import { randomUUID } from 'crypto';
import { createReadStream, existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'fs';
import type { IncomingMessage, ServerResponse } from 'http';
import { dirname, resolve, sep } from 'path';

import type { Connect, Plugin } from 'vite';

import { createLocalApi, fileRoots } from './api';

export const LOCAL_USER = { id: 'local-user', name: 'Local user' };

const TYPES: Record<string, string> = {
  '.json': 'application/json',
  '.dzi': 'application/xml',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.pdf': 'application/pdf',
};
const PATIENT_ID = /^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}$/;

type Note = {
  id: string;
  patientId: string;
  body: string;
  createdBy: string;
  authorName: string;
  createdAt: string;
  eventId?: string;
};

/** Notes in one JSON file, seeded on first use with the illustrative notes from pipeline/tumour_board_notes.json. */
function notesStore(file: string, seedFile: string) {
  const read = (): Note[] => {
    if (existsSync(file)) return JSON.parse(readFileSync(file, 'utf8')) as Note[];
    const notes: Note[] = [];
    if (existsSync(seedFile)) {
      const seed = JSON.parse(readFileSync(seedFile, 'utf8')) as { author: string; notes: Record<string, string> };
      const createdAt = new Date().toISOString();
      for (const [patientId, body] of Object.entries(seed.notes)) {
        notes.push({ id: randomUUID(), patientId, body, createdBy: LOCAL_USER.id, authorName: seed.author, createdAt });
      }
    }
    write(notes);
    return notes;
  };
  const write = (notes: Note[]) => {
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(`${file}.tmp`, JSON.stringify(notes, null, 2));
    renameSync(`${file}.tmp`, file);
  };
  return {
    list: (patientId: string) =>
      read()
        .filter((n) => n.patientId === patientId)
        .sort((a, b) => a.createdAt.localeCompare(b.createdAt)),
    create: (input: { patientId: string; body: string; authorName?: string; eventId?: string }): Note => {
      const note: Note = {
        id: randomUUID(),
        patientId: input.patientId,
        body: input.body.slice(0, 1000),
        createdBy: LOCAL_USER.id,
        authorName: (input.authorName || LOCAL_USER.name).slice(0, 128),
        createdAt: new Date().toISOString(),
        ...(input.eventId ? { eventId: input.eventId.slice(0, 200) } : {}),
      };
      write([...read(), note]);
      return note;
    },
    remove: (id: string) => write(read().filter((n) => n.id !== id || n.createdBy !== LOCAL_USER.id)),
  };
}

async function body(req: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  const text = Buffer.concat(chunks).toString('utf8');
  return text ? (JSON.parse(text) as Record<string, unknown>) : {};
}

function send(res: ServerResponse, status: number, value?: unknown) {
  res.statusCode = status;
  if (value === undefined) return res.end();
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(value));
}

export function localMode(projectRoot: string): Plugin {
  const work = resolve(projectRoot, 'work');
  const api = createLocalApi(work);
  const roots = fileRoots(work);
  const notes = notesStore(resolve(work, 'local', 'notes.json'), resolve(projectRoot, 'pipeline', 'tumour_board_notes.json'));

  const mount = (middlewares: Connect.Server, logError: (msg: string) => void) => {
    middlewares.use('/local-api', (req, res) => {
      void (async () => {
        const url = new URL(req.url ?? '/', 'http://local');
        const origin = `http://${req.headers.host}`;
        const [, name, id] = url.pathname.split('/');
        try {
          if (name === 'getCohort') return send(res, 200, await api.getCohort(origin));
          if (name === 'getPatient') return send(res, 200, await api.getPatient(url.searchParams.get('patientId') ?? '', origin));
          if (name === 'getDataMap') return send(res, 200, await api.getDataMap());
          if (name === 'getWardFlowCohort') return send(res, 200, await api.getWardFlowCohort());
          if (name === 'getAlertStopwatch') return send(res, 200, await api.getAlertStopwatch(url.searchParams.get('patientId') ?? undefined));
          if (name === 'notes' && req.method === 'GET') {
            const patientId = url.searchParams.get('patientId') ?? '';
            if (!PATIENT_ID.test(patientId)) return send(res, 400, { error: 'Invalid patient id' });
            return send(res, 200, notes.list(patientId));
          }
          if (name === 'notes' && req.method === 'POST') {
            const input = await body(req);
            const patientId = String(input.patientId ?? '');
            const text = String(input.body ?? '').trim();
            if (!PATIENT_ID.test(patientId) || !text) return send(res, 400, { error: 'A patient id and a note are required' });
            const eventId = typeof input.eventId === 'string' ? input.eventId : undefined;
            return send(res, 201, notes.create({ patientId, body: text, authorName: String(input.authorName ?? ''), eventId }));
          }
          if (name === 'notes' && req.method === 'DELETE' && id) {
            notes.remove(decodeURIComponent(id));
            return send(res, 204);
          }
          return send(res, 404, { error: `Unknown local API ${req.method} ${url.pathname}` });
        } catch (error) {
          logError(`[local-api] ${url.pathname}: ${error instanceof Error ? error.stack : String(error)}`);
          return send(res, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      })();
    });

    // Files are sent as stored, so `.nii.gz` volumes reach NiiVue still gzipped (no Content-Encoding), as from OneLake.
    middlewares.use('/local-files', (req, res, next) => {
      const path = decodeURIComponent((req.url ?? '').split('?')[0]);
      const [, silo, top, ...rest] = path.split('/');
      const root = roots[silo as keyof typeof roots]?.[top];
      if (!root) return next();
      const file = resolve(root, ...rest);
      if (!file.startsWith(root + sep)) return send(res, 403);
      let size: number;
      try {
        const st = statSync(file);
        if (!st.isFile()) throw new Error('not a file');
        size = st.size;
      } catch {
        return send(res, 404);
      }
      const ext = Object.keys(TYPES).find((e) => file.toLowerCase().endsWith(e));
      res.setHeader('Content-Type', ext ? TYPES[ext] : 'application/octet-stream');
      res.setHeader('Content-Length', String(size));
      res.setHeader('Cache-Control', 'public, max-age=3600');
      createReadStream(file).pipe(res);
    });
  };

  return {
    name: 'patient360-local-mode',
    configureServer(server) {
      mount(server.middlewares, (msg) => server.config.logger.error(msg));
    },
    // `npm run preview:local`: the production build of the app, still served from work/.
    configurePreviewServer(server) {
      mount(server.middlewares, (msg) => server.config.logger.error(msg));
    },
  };
}
