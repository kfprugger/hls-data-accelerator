import { type RayfinRuntimeConfig } from '@microsoft/rayfin-client';

import { LOCAL_DATA } from '@/lib/localMode';

import { IAuthService } from './interfaces/IAuthService';
import { LocalDataAuthService } from './local/LocalDataAuthService';
import { MockAuthService } from './mock/MockAuthService';
import { RayfinAuthService } from './rayfin/RayfinAuthService';
import { RayfinClientService } from './rayfin/RayfinClientService';

function isLocalBackend(url: string): boolean {
  try {
    const { hostname } = new URL(url);
    return hostname === 'localhost' || hostname === '127.0.0.1';
  } catch {
    return false;
  }
}

export class ServiceContainer {
  private static instance: ServiceContainer | null = null;

  public readonly authService: IAuthService;

  private constructor(authService: IAuthService) {
    this.authService = authService;
  }

  static async create(): Promise<ServiceContainer> {
    if (!ServiceContainer.instance && LOCAL_DATA) {
      // Local mode never talks to a Rayfin backend, so no client is created.
      ServiceContainer.instance = new ServiceContainer(new LocalDataAuthService());
    }
    if (!ServiceContainer.instance) {
      const apiUrl =
        import.meta.env.VITE_RAYFIN_API_URL || 'http://localhost:5168';
      const localDev = isLocalBackend(apiUrl);

      const publishableKey = import.meta.env.VITE_RAYFIN_PUBLISHABLE_KEY;

      if (!publishableKey && !localDev) {
        throw new Error(
          'VITE_RAYFIN_PUBLISHABLE_KEY environment variable is required'
        );
      }

      const projectId = import.meta.env.VITE_FABRIC_ITEM_ID;

      const rayfinClientService = RayfinClientService.getInstance();
      await rayfinClientService.initialize(
        apiUrl.endsWith('/') ? apiUrl : `${apiUrl}/`,
        publishableKey ?? 'local-dev-key',
        projectId,
        {
          workspaceId: import.meta.env.VITE_FABRIC_WORKSPACE_ID,
          itemId: import.meta.env.VITE_FABRIC_ITEM_ID,
          portalUrl: import.meta.env.VITE_FABRIC_PORTAL_URL,
        }
      );

      let authService: IAuthService;

      if (localDev) {
        authService = new MockAuthService();
      } else {
        const resolved = rayfinClientService.getClient().runtimeConfig ?? {};

        authService = new RayfinAuthService({
          workspaceId: resolved.workspaceId || '',
          projectId: resolved.itemId || '',
          fabricPortalUrl: resolved.portalUrl || '',
        });
      }

      ServiceContainer.instance = new ServiceContainer(authService);
    }

    return ServiceContainer.instance;
  }

  static getInstance(): ServiceContainer {
    if (!ServiceContainer.instance) {
      throw new Error('ServiceContainer not initialized. Call create() first.');
    }
    return ServiceContainer.instance;
  }

  /**
   * Fabric coordinates resolved during {@link create}, falling back to
   * build-time `VITE_FABRIC_*` values when not yet resolved (e.g. local dev,
   * where Fabric coordinates are never resolved). Used by consumers (e.g.
   * the slide viewer) that build Fabric portal links, so they match the same
   * deployment stage as the API/auth wiring above instead of the stage the
   * bundle was built in.
   */
  static getFabricConfig(): RayfinRuntimeConfig {
    return (
      RayfinClientService.getInstance().getClient().runtimeConfig ?? {
        workspaceId: import.meta.env.VITE_FABRIC_WORKSPACE_ID,
        itemId: import.meta.env.VITE_FABRIC_ITEM_ID,
        portalUrl: import.meta.env.VITE_FABRIC_PORTAL_URL,
      }
    );
  }

  static reset(): void {
    ServiceContainer.instance = null;
    RayfinClientService.reset();
  }
}
