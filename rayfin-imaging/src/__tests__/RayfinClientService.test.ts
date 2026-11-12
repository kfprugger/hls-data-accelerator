import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { RayfinClientService } from '../services/rayfin/RayfinClientService';

const CONFIG_PATH = '/rayfin.config.json';

function isConfigRequest(input: unknown): boolean {
  const url = typeof input === 'string' ? input : String(input);
  return url.endsWith(CONFIG_PATH);
}

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: { get: () => 'application/json' },
    text: () => Promise.resolve(JSON.stringify(body)),
    json: () => Promise.resolve(body),
  };
}

describe('RayfinClientService — promoted deployment moniker header', () => {
  // Neither ID is GUID-shaped and neither base URL contains one, so
  // ApiClient's own baseUrl-derived moniker fallback (extractLastGuid) can't
  // coincidentally mask a regression here -- only our explicit header wiring
  // is under test.
  const sourceItemId = 'source-item-id';
  const destinationItemId = 'destination-item-id';

  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    RayfinClientService.reset();

    fetchMock = vi.fn((input: unknown) => {
      if (isConfigRequest(input)) {
        // Simulates a promoted deployment: rayfin.config.json now resolves to
        // the destination item, not the build-time source item baked into
        // VITE_FABRIC_ITEM_ID at build time.
        return Promise.resolve(
          jsonResponse({
            apiUrl: 'https://destination.example.com/api/',
            publishableKey: 'pk-destination',
            itemId: destinationItemId,
            workspaceId: 'ws-destination',
            portalUrl: 'https://app.fabric.microsoft.com/destination',
          })
        );
      }
      // The actual data/API call under test -- only the request headers are
      // inspected, so the response body just needs to parse without throwing.
      return Promise.resolve(jsonResponse({ data: {} }));
    });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    RayfinClientService.reset();
  });

  it('sends the resolved destination item ID as the moniker header, not the build-time source item ID', async () => {
    const client = await RayfinClientService.getInstance().initialize(
      'https://source.example.com/api/',
      'pk-source',
      sourceItemId,
      {
        workspaceId: 'ws-source',
        itemId: sourceItemId,
        portalUrl: 'https://app.fabric.microsoft.com/source',
      }
    );

    // Sanity check: fromConfig() itself resolved the promoted runtime config.
    expect(client.runtimeConfig?.itemId).toBe(destinationItemId);

    fetchMock.mockClear();
    await client.data.SlidePin.select(['id'])
      .execute()
      .catch(() => undefined);

    const dataCall = fetchMock.mock.calls.find(
      ([input]) => !isConfigRequest(input)
    );
    expect(dataCall).toBeDefined();

    const [, requestInit] = dataCall as [unknown, RequestInit];
    const headers = new Headers(requestInit.headers);
    expect(headers.get('x-ms-workload-resource-moniker')).toBe(
      destinationItemId
    );
  });
});
