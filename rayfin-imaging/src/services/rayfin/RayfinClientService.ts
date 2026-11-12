import {
  RayfinClient,
  resolveRayfinConfig,
  type RayfinRuntimeConfig,
} from '@microsoft/rayfin-client';
import { resolveRayfinFunctionsBaseUrl } from '@microsoft/rayfin-local-dev';

import type { AppSchema } from '../../../rayfin/data/schema';
import type { AppFunctionsSchema } from '../../../rayfin/functions/src/types';

/**
 * A singleton service that manages the RayfinClient instance
 */
export class RayfinClientService {
  private static instance: RayfinClientService | null = null;
  private _client: RayfinClient<AppSchema, AppFunctionsSchema> | null = null;

  private constructor() {}

  /**
   * Get the singleton instance of RayfinClientService
   */
  public static getInstance(): RayfinClientService {
    if (!RayfinClientService.instance) {
      RayfinClientService.instance = new RayfinClientService();
    }
    return RayfinClientService.instance;
  }

  /**
   * Initialize the RayfinClient with the provided base URL and publishable key
   *
   * @param baseUrl - The base URL of the Rayfin API
   * @param publishableKey - The publishable key for service-level authentication
   * @param projectId - Optional Rayfin project identifier (set by rayfin up)
   * @param runtimeConfig - Fabric coordinates fallback for local dev
   * @returns The initialized RayfinClient instance
   */
  public async initialize(
    baseUrl: string,
    publishableKey: string,
    projectId?: string,
    runtimeConfig?: RayfinRuntimeConfig
  ): Promise<RayfinClient<AppSchema, AppFunctionsSchema>> {
    if (!this._client) {
      console.log(`🔧 Initializing Rayfin client with baseUrl: ${baseUrl}`);

      // No default Content-Type: the SDK sets it per request, and a default one is merged with the
      // lowercase copy carried into the 401 refresh-and-retry path, producing a duplicated header (415).
      const headers: Record<string, string> = {
        Origin: window.location.origin,
      };

      const resolved = await resolveRayfinConfig({
        apiUrl: baseUrl,
        publishableKey,
        ...runtimeConfig,
        // Managed-hosting moniker (set by `rayfin up`) threads through as
        // itemId; RayfinClientBase derives the request moniker header from
        // runtimeConfig.itemId automatically.
        itemId: runtimeConfig?.itemId ?? projectId,
      });

      this._client = new RayfinClient<AppSchema, AppFunctionsSchema>({
        // resolved.baseUrl/publishableKey are always set: baseUrl/publishableKey
        // args are required strings, so the resolve step can only overlay on top of them.
        baseUrl: resolved.baseUrl!,
        publishableKey: resolved.publishableKey!,
        headers,
        authStorage: true,
        functionsBaseUrl: resolveRayfinFunctionsBaseUrl(),
        runtimeConfig: resolved.runtimeConfig,
      });

      console.log(
        `✅ Rayfin client configured for direct API calls to ${baseUrl}`
      );
    }

    return this._client;
  }

  /**
   * Get the RayfinClient instance
   * @throws Error if the client is not initialized
   */
  public getClient(): RayfinClient<AppSchema, AppFunctionsSchema> {
    if (!this._client) {
      throw new Error('RayfinClient not initialized. Call initialize() first.');
    }
    return this._client;
  }

  /**
   * Check if the client is initialized
   */
  public isInitialized(): boolean {
    return this._client !== null;
  }

  /**
   * Reset the singleton instance (useful for testing)
   */
  public static reset(): void {
    RayfinClientService.instance = null;
  }
}

/**
 * Helper function to get the RayfinClient instance
 * @throws Error if the client is not initialized
 */
export function getRayfinClient(): RayfinClient<AppSchema, AppFunctionsSchema> {
  return RayfinClientService.getInstance().getClient();
}
