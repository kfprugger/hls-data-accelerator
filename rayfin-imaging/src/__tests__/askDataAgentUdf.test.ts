import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { askDataAgentHandler } from '../../rayfin/functions/src/function_app';

describe('askDataAgent UDF Verification Tests', () => {
  let fetchCalls: { url: string; options?: RequestInit }[] = [];
  let fetchMock: Mock;

  beforeEach(() => {
    fetchCalls = [];
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : (input as Request).url;
      fetchCalls.push({ url, options: init });

      // Mock DataAgent item lookup
      if (url.includes('/items?type=DataAgent')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            value: [
              { id: 'dynamic-agent-uuid-7777', displayName: 'Patient 360', type: 'DataAgent' },
            ],
          }),
        } as unknown as Response;
      }

      // Mock Assistants API endpoints
      if (url.endsWith('/assistants?api-version=2024-05-01-preview&stage=production')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ id: 'asst_12345' }),
        } as unknown as Response;
      }

      if (url.endsWith('/threads?api-version=2024-05-01-preview&stage=production') && init?.method === 'POST') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ id: 'th_12345' }),
        } as unknown as Response;
      }

      if (url.includes('/threads/th_12345/messages') && init?.method === 'POST') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ id: 'msg_12345' }),
        } as unknown as Response;
      }

      if (url.includes('/threads/th_12345/messages') && (!init?.method || init.method === 'GET')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              {
                role: 'assistant',
                content: [
                  {
                    type: 'text',
                    text: {
                      value: 'Patient Marcus Vance has the cancer diagnosis:\n\n- **Clear cell renal cell carcinoma**',
                    },
                  },
                ],
              },
            ],
          }),
        } as unknown as Response;
      }

      if (url.endsWith('/runs?api-version=2024-05-01-preview&stage=production') && init?.method === 'POST') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ id: 'run_12345' }),
        } as unknown as Response;
      }
      if (url.includes('/runs/run_12345') && !url.includes('/steps')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ id: 'run_12345', status: 'completed' }),
        } as unknown as Response;
      }

      if (url.endsWith('/steps?api-version=2024-05-01-preview&stage=production')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              {
                id: 'step_1',
                step_details: {
                  type: 'tool_calls',
                  tool_calls: [
                    {
                      id: 'call_1',
                      type: 'function',
                      function: {
                        name: 'analyze.database.nl2code',
                        arguments: JSON.stringify({
                          code: 'SELECT DISTINCT p.idOrig AS patient_id FROM dbo.Patient p WHERE p.name_string LIKE \'%Marcus%\';',
                        }),
                      },
                    },
                  ],
                },
              },
            ],
          }),
        } as unknown as Response;
      }

      if (init?.method === 'DELETE') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ id: 'th_12345', deleted: true }),
        } as unknown as Response;
      }

      return {
        ok: true,
        status: 200,
        json: async () => ({}),
      } as unknown as Response;
    });

    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  const mockCtx = {
    Tokens: {
      Fabric: 'mock-fabric-bearer-token',
    },
  } as unknown as Parameters<typeof askDataAgentHandler>[1];

  it('Defect 1 fixed: Resolves agent dynamically by display name Patient 360 instead of using hard-coded ID', async () => {
    await askDataAgentHandler('What cancer diagnosis does the patient Marcus Vance have?', mockCtx);

    // Verify lookup was executed
    const lookupCall = fetchCalls.find((c) => c.url.includes('/items?type=DataAgent'));
    expect(lookupCall).toBeDefined();

    // Verify all subsequent agent calls use the resolved ID, never the hardcoded 9f091d45-2f69-4fa9-961e-64930a02f4b4
    const agentCalls = fetchCalls.filter((c) => !c.url.includes('/items?type=DataAgent'));
    expect(agentCalls.length).toBeGreaterThan(0);
    for (const call of agentCalls) {
      expect(call.url).toContain('dynamic-agent-uuid-7777');
      expect(call.url).not.toContain('9f091d45-2f69-4fa9-961e-64930a02f4b4');
    }
  });

  it('Defect 2 fixed: Uses 60 s AbortSignal timeout on agent calls instead of 15 s', async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, 'timeout');
    await askDataAgentHandler('What cancer diagnosis does the patient Marcus Vance have?', mockCtx);

    expect(timeoutSpy).toHaveBeenCalled();
    const timeoutCalls = timeoutSpy.mock.calls.map((args) => args[0]);
    // Must use 60_000 ms timeout for agent calls, never 15_000 ms
    expect(timeoutCalls).toContain(60_000);
    expect(timeoutCalls).not.toContain(15_000);
  });

  it('Defect 3 fixed: Extracts generatedQuery from run tool-call steps and NOT via regex parsing of answer text', async () => {
    const result = await askDataAgentHandler(
      'What cancer diagnosis does the patient Marcus Vance have?',
      mockCtx,
    );

    // Natural text answer has no ```sql fence
    expect(result.answer).toContain('Clear cell renal cell carcinoma');
    expect(result.answer).not.toContain('```sql');

    // Query is correctly extracted from run steps tool calls
    expect(result.generatedQuery).toBe(
      'SELECT DISTINCT p.idOrig AS patient_id FROM dbo.Patient p WHERE p.name_string LIKE \'%Marcus%\';',
    );
    expect(result.queryLanguage.toUpperCase()).toBe('SQL');
  });

  it('Defect 3 fixed: Does not extract fake code block from answer text when steps have no tool query', async () => {
    // Override steps endpoint to return no tool calls
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : (input as Request).url;
      if (url.includes('/items?type=DataAgent')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            value: [{ id: 'agent-1111', displayName: 'Patient 360', type: 'DataAgent' }],
          }),
        } as unknown as Response;
      }
      if (url.endsWith('/assistants?api-version=2024-05-01-preview&stage=production')) {
        return { ok: true, status: 200, json: async () => ({ id: 'asst_1' }) } as unknown as Response;
      }
      if (url.endsWith('/threads?api-version=2024-05-01-preview&stage=production') && init?.method === 'POST') {
        return { ok: true, status: 200, json: async () => ({ id: 'th_1' }) } as unknown as Response;
      }
      if (url.includes('/threads/th_1/messages') && init?.method === 'POST') {
        return { ok: true, status: 200, json: async () => ({ id: 'msg_1' }) } as unknown as Response;
      }
      if (url.includes('/threads/th_1/messages') && (!init?.method || init.method === 'GET')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              {
                role: 'assistant',
                content: [
                  {
                    type: 'text',
                    text: {
                      value: 'Here is an example query:\n```sql\nSELECT * FROM fake_table\n```',
                    },
                  },
                ],
              },
            ],
          }),
        } as unknown as Response;
      }
      if (url.endsWith('/runs?api-version=2024-05-01-preview&stage=production') && init?.method === 'POST') {
        return { ok: true, status: 200, json: async () => ({ id: 'run_1' }) } as unknown as Response;
      }
      if (url.includes('/runs/run_1') && !url.endsWith('/steps')) {
        return { ok: true, status: 200, json: async () => ({ id: 'run_1', status: 'completed' }) } as unknown as Response;
      }
      if (url.endsWith('/steps?api-version=2024-05-01-preview&stage=production')) {
        // Steps has no query tool calls
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              {
                id: 'step_non_query',
                step_details: {
                  type: 'tool_calls',
                  tool_calls: [
                    {
                      id: 'call_fewshots',
                      type: 'function',
                      function: {
                        name: 'analyze.database.fewshots.loading',
                        arguments: '{}',
                        output: 'Loaded fewshots',
                      },
                    },
                  ],
                },
              },
            ],
          }),
        } as unknown as Response;
      }
      return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
    });

    const result = await askDataAgentHandler('General question', mockCtx);
    // Answer text contains ```sql, but steps have no query.
    // Query must be empty string if none from steps (no regex parsing of the answer text).
    expect(result.generatedQuery).toBe('');
    expect(result.answer).toContain('SELECT * FROM fake_table');
  });

  it('Handles 503 warmup status appropriately', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : (input as Request).url;
      if (url.includes('/items?type=DataAgent')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            value: [{ id: 'agent-1111', displayName: 'Patient 360', type: 'DataAgent' }],
          }),
        } as unknown as Response;
      }
      return {
        ok: false,
        status: 503,
        json: async () => ({ error: 'Service Unavailable' }),
      } as unknown as Response;
    });

    await expect(askDataAgentHandler('Any question', mockCtx)).rejects.toThrow(
      'Data Agent is temporarily warming up',
    );
  });

  it('Handles 401 unauthorized status appropriately', async () => {
    fetchMock.mockImplementation(async () => ({
      ok: false,
      status: 401,
    } as unknown as Response));

    await expect(askDataAgentHandler('Any question', mockCtx)).rejects.toThrow(
      'Invalid or expired delegated token',
    );
  });

  it('Handles 403 forbidden status appropriately', async () => {
    fetchMock.mockImplementation(async () => ({
      ok: false,
      status: 403,
    } as unknown as Response));

    await expect(askDataAgentHandler('Any question', mockCtx)).rejects.toThrow(
      'User lacks permissions to query source tables',
    );
  });

  it('Validates empty and too-long input client/server-side', async () => {
    await expect(askDataAgentHandler('', mockCtx)).rejects.toThrow('empty_question');
    await expect(askDataAgentHandler('   ', mockCtx)).rejects.toThrow('empty_question');
    await expect(askDataAgentHandler('A'.repeat(505), mockCtx)).rejects.toThrow('question_too_long');
  });
});
