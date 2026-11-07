import { useState } from 'react';
import { askDataAgent, type AskDataAgentResponse } from '@/lib/api';

const PRESET_QUERIES = [
  "Show Marcus Vance's vital signs and cancer stage",
  'Which devices have SpO2 alerts right now?',
  'Show cohort cancer distribution',
  'List all patients with respiratory conditions',
];

function CodeBlock({ code, language }: { code: string; language: string }) {
  const lines = code.trim().split('\n');
  return (
    <div className="hair border rounded overflow-hidden my-3 bg-neutral-900 text-neutral-100">
      <div className="flex items-center justify-between px-3 py-1.5 bg-neutral-800 border-b border-neutral-700 text-xs">
        <span className="font-semibold uppercase tracking-wider text-neutral-300">{language}</span>
        <span className="text-neutral-400">{lines.length} lines</span>
      </div>
      <div className="p-3 overflow-x-auto text-[13px] font-mono leading-relaxed">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, idx) => (
              <tr key={idx} className="hover:bg-neutral-800/50">
                <td className="pr-4 text-right select-none text-neutral-500 w-8 align-top text-xs">
                  {idx + 1}
                </td>
                <td className="whitespace-pre text-neutral-200">
                  {line || ' '}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AskDataAgent() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskDataAgentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isWarmingUp, setIsWarmingUp] = useState(false);
  const [showQueries, setShowQueries] = useState(false);

  const length = question.length;
  const isTooLong = length > 500;
  const isWhitespaceOnly = length > 0 && !question.trim();
  const isEmpty = !question.trim();
  const isSubmitDisabled = isTooLong || isEmpty || loading;

  const execute = async (qText: string) => {
    const trimmed = qText.trim();
    if (!trimmed || qText.length > 500 || loading) return;

    setLoading(true);
    setError(null);
    setIsWarmingUp(false);

    try {
      const data = await askDataAgent(qText);
      setResult(data);
    } catch (err: unknown) {
      setResult(null);
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('503') || msg.toLowerCase().includes('warming up')) {
        setIsWarmingUp(true);
        setError('Data Agent is temporarily warming up. Please retry in a few seconds.');
      } else if (msg.includes('403') || msg.toLowerCase().includes('forbidden')) {
        setError('User lacks permissions to query source tables');
      } else if (msg.includes('401') || msg.toLowerCase().includes('unauthorized')) {
        setError('Invalid or expired delegated token. Please re-authenticate.');
      } else {
        setError(msg || 'An unexpected error occurred while querying the Data Agent.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleChipClick = (preset: string) => {
    setQuestion(preset);
    void execute(preset);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isSubmitDisabled) {
      void execute(question);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isSubmitDisabled) {
        void execute(question);
      }
    }
  };

  // Split generated query into SQL and KQL sections if mixed
  const sqlQuery = result?.generatedQuery.includes('SELECT')
    ? result.generatedQuery.split('-- Eventhouse KQL Query:')[0].trim()
    : null;
  const kqlQuery = result?.generatedQuery.includes('TelemetryRaw')
    ? (result.generatedQuery.includes('-- Eventhouse KQL Query:')
        ? '-- Eventhouse KQL Query:\n' + result.generatedQuery.split('-- Eventhouse KQL Query:')[1].trim()
        : result.generatedQuery)
    : null;

  return (
    <div className="w-full max-w-full overflow-x-hidden p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="max-w-4xl mx-auto">
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[var(--foreground)]">
          Ask Data Agent
        </h1>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">
          Plain-language Q&amp;A over unified FHIR clinical records and Masimo real-time telemetry powered by Fabric Patient 360 Data Agent.
        </p>
      </div>

      {/* Search Input Box */}
      <div className="max-w-4xl mx-auto">
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="relative">
            <label htmlFor="agent-question-input" className="sr-only">
              Ask a question about patients or telemetry
            </label>
            <textarea
              id="agent-question-input"
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question (e.g. Show Marcus Vance's vital signs and cancer stage)..."
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] p-3.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-[var(--primary)] text-[var(--card-foreground)] resize-none"
              aria-label="Ask a question about patients or telemetry"
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2">
              {isTooLong && (
                <span className="text-red-500 font-medium">
                  Question exceeds 500 character limit
                </span>
              )}
              {isWhitespaceOnly && (
                <span className="text-amber-600 dark:text-amber-400 font-medium">
                  Please enter a question
                </span>
              )}
            </div>
            <div className={`font-mono text-xs ${isTooLong ? 'text-red-500 font-semibold' : 'text-[var(--muted-foreground)]'}`}>
              {length} / 500
            </div>
          </div>

          {/* Quick-start preset query chips */}
          <div className="space-y-1.5 pt-1">
            <div className="text-xs font-medium text-[var(--muted-foreground)]">Sample queries:</div>
            <div className="flex flex-wrap gap-2">
              {PRESET_QUERIES.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => handleChipClick(preset)}
                  className="inline-flex items-center min-h-[44px] px-3.5 py-1.5 rounded-full text-xs font-medium bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:bg-[var(--accent)] hover:text-[var(--accent-foreground)] border border-[var(--border)] transition-colors cursor-pointer text-left"
                >
                  {preset}
                </button>
              ))}
            </div>
          </div>

          {/* Submit button */}
          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={isSubmitDisabled}
              aria-disabled={isSubmitDisabled ? 'true' : 'false'}
              className="inline-flex items-center justify-center min-h-[44px] px-5 py-2.5 rounded-lg text-sm font-medium bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all cursor-pointer"
            >
              {loading ? 'Querying Data Agent...' : 'Ask Data Agent'}
            </button>
          </div>
        </form>
      </div>

      {/* Warming-up / Error Banner */}
      {isWarmingUp && (
        <div className="max-w-4xl mx-auto rounded-lg border border-amber-500/50 bg-amber-50 dark:bg-amber-950/30 p-4 text-sm text-amber-800 dark:text-amber-200">
          <p className="font-medium">Data Agent is temporarily warming up. Please retry in a few seconds.</p>
        </div>
      )}

      {error && !isWarmingUp && (
        <div className="max-w-4xl mx-auto rounded-lg border border-red-500/50 bg-red-50 dark:bg-red-950/30 p-4 text-sm text-red-800 dark:text-red-200">
          <p className="font-medium">{error}</p>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading && (
        <div className="max-w-4xl mx-auto p-6 rounded-lg border border-[var(--border)] bg-[var(--card)] space-y-4 animate-pulse" aria-busy="true">
          <div className="h-4 bg-[var(--muted)] rounded w-3/4"></div>
          <div className="h-4 bg-[var(--muted)] rounded w-5/6"></div>
          <div className="h-4 bg-[var(--muted)] rounded w-1/2"></div>
          <div className="pt-4 border-t border-[var(--border)] flex justify-between items-center">
            <div className="h-4 bg-[var(--muted)] rounded w-1/4"></div>
            <div className="h-6 bg-[var(--muted)] rounded w-16"></div>
          </div>
        </div>
      )}

      {/* Answer & Query Inspection Panels */}
      {result && !loading && (
        <div className="max-w-4xl mx-auto space-y-4">
          {/* Answer Card */}
          <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-5 sm:p-6 shadow-sm">
            <div className="flex items-center justify-between pb-3 border-b border-[var(--border)] text-xs text-[var(--muted-foreground)]">
              <span className="font-medium">Agent: {result.agentName}</span>
              <span className="font-mono">{result.executionTimeMs} ms</span>
            </div>
            <div className="mt-4 text-sm sm:text-base leading-relaxed text-[var(--card-foreground)] whitespace-pre-wrap">
              {result.answer}
            </div>
          </div>

          {/* Expandable Generated Query Card */}
          <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] overflow-hidden shadow-sm">
            <button
              type="button"
              onClick={() => setShowQueries(!showQueries)}
              className="w-full flex items-center justify-between p-4 bg-[var(--secondary)] hover:bg-[var(--accent)] text-[var(--secondary-foreground)] transition-colors min-h-[44px] cursor-pointer"
              aria-expanded={showQueries}
            >
              <div className="flex items-center gap-3">
                <span className="font-medium text-sm">Generated Query</span>
                <span className="text-xs text-[var(--muted-foreground)]">
                  ({showQueries ? 'Click to collapse' : 'Click to inspect generated SQL/KQL'})
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-[var(--primary)] text-[var(--primary-foreground)]">
                  {result.executionTimeMs} ms
                </span>
                <span className="text-xs text-[var(--muted-foreground)]">
                  {showQueries ? '▲' : '▼'}
                </span>
              </div>
            </button>

            {showQueries && (
              <div className="p-4 sm:p-5 border-t border-[var(--border)] space-y-4">
                <div className="text-xs text-[var(--muted-foreground)]">
                  Audited queries generated by {result.agentName} across Lakehouse and Eventhouse datasources:
                </div>

                {sqlQuery ? (
                  <CodeBlock code={sqlQuery} language="SQL" />
                ) : null}

                {kqlQuery ? (
                  <CodeBlock code={kqlQuery} language="KQL" />
                ) : null}

                {!sqlQuery && !kqlQuery && (
                  <CodeBlock code={result.generatedQuery} language={result.queryLanguage.toUpperCase()} />
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
export default AskDataAgent;
