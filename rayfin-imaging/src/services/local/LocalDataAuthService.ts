import { LOCAL_USER } from '@/lib/localMode';

import { AuthUser, IAuthService } from '../interfaces/IAuthService';

/** Local mode: no sign-in. The app opens straight away as "Local user"; there is no backend to sign in to. */
export class LocalDataAuthService implements IAuthService {
  get fabricAuthEnabled(): boolean {
    return true;
  }

  async signOut(): Promise<void> {}

  async getCurrentUser(): Promise<AuthUser | null> {
    return LOCAL_USER;
  }

  async isAuthenticated(): Promise<boolean> {
    return true;
  }

  async initEmbeddedAuth(): Promise<AuthUser | null> {
    return LOCAL_USER;
  }

  async initiateFabricLogin(): Promise<void> {}

  async ensureSignedInWithFabric(): Promise<AuthUser> {
    return LOCAL_USER;
  }
}
