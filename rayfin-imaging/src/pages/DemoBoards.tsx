import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

/** The demo film's 1920x1080 boards, shipped as static files under public/demo/boards. */
const BOARDS = [
  { file: '01-bedside-alert.html', beat: 'Beat 1: Bedside Crisis', title: 'Bed 04 at 02:14 AM: Marcus Vance (TCGA-G6-A8L6)' },
  { file: '02-silos-patient.html', beat: 'Beat 2: Silo Convergence', title: 'Collapsing six disconnected hospital silos into OneLake' },
  { file: '03-alert-stopwatch.html', beat: 'Beat 3: Measured Latency', title: '20.5-second end-to-end real-time alert stopwatch' },
  { file: '04-multimodal-oncology.html', beat: 'Beat 4: Multimodal Oncology', title: 'Marcus Vance: genomics, 3D CT, and pathology' },
  { file: '05-wardflow-cardiology.html', beat: 'Beat 5: Governed Triage', title: 'WardFlow Cardiology: hemodynamic cohort and Beat 4 gate' },
  { file: '06-clinician-signoff.html', beat: 'Beat 6: Clinician Governance', title: 'Clinician sign-off with verified Fabric audit trail' },
  { file: '07-endcard.html', beat: 'Beat 7: Architecture Payoff', title: 'From bedside waveform to boardroom confidence' },
];

const BOARD_W = 1920;
const BOARD_H = 1080;

export function DemoBoards() {
  const [params, setParams] = useSearchParams();
  const requested = Number(params.get('board'));
  const index = Number.isInteger(requested) && requested >= 1 && requested <= BOARDS.length ? requested - 1 : 0;
  const board = BOARDS[index];
  const src = `${import.meta.env.BASE_URL}demo/boards/${board.file}`;

  const frameRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.5);

  useEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    const fit = () => setScale(Math.min(el.clientWidth / BOARD_W, el.clientHeight / BOARD_H));
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const go = (next: number) => setParams({ board: String(next + 1) }, { replace: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === 'ArrowRight' && index < BOARDS.length - 1) go(index + 1);
      if (e.key === 'ArrowLeft' && index > 0) go(index - 1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [index, setParams]);

  const select = (i: number) => setParams({ board: String(i + 1) }, { replace: true });

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex flex-wrap items-end justify-between gap-4 px-8 pb-4 pt-6">
        <div>
          <div className="t-label">Demo boards · {index + 1} of {BOARDS.length}</div>
          <h1 className="t-display mt-1 text-[28px]">{board.beat}</h1>
          <p className="t-muted mt-1 text-[14px]">{board.title}</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn" onClick={() => select(index - 1)} disabled={index === 0}>
            Previous
          </button>
          <button type="button" className="btn" onClick={() => select(index + 1)} disabled={index === BOARDS.length - 1}>
            Next
          </button>
          <a className="btn" href={src} target="_blank" rel="noreferrer">
            Open full size
          </a>
        </div>
      </div>

      <div ref={frameRef} className="relative min-h-0 flex-1 px-8">
        <div
          className="hair absolute left-1/2 top-0 origin-top overflow-hidden border"
          style={{ width: BOARD_W, height: BOARD_H, transform: `translateX(-50%) scale(${scale})` }}
        >
          <iframe key={board.file} title={board.beat} src={src} width={BOARD_W} height={BOARD_H} className="block border-0" />
        </div>
      </div>

      <nav aria-label="Boards" className="hair flex gap-2 overflow-x-auto border-t px-8 py-3">
        {BOARDS.map((b, i) => (
          <button
            key={b.file}
            type="button"
            onClick={() => select(i)}
            aria-current={i === index ? 'true' : undefined}
            className={`btn shrink-0 text-[12px] ${i === index ? 'btn-ink' : ''}`}
          >
            {i + 1}. {b.beat.replace(/^Beat \d+: /, '')}
          </button>
        ))}
      </nav>
    </div>
  );
}
