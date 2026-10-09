import { createContext, useContext, useState, type Dispatch, type SetStateAction, type ReactNode } from 'react';
import type { DeploymentConfig } from './api';
interface Draft { config: DeploymentConfig; namingPrefix: string; useNamingConvention: boolean; selectedCapacity: string; pauseAfterDeploy: boolean }
const Context = createContext<{ draft: Draft | null; saveDraft: Dispatch<SetStateAction<Draft | null>> } | null>(null);
export function DeploymentDraftProvider({ children }: { children: ReactNode }) {
  const [draft, saveDraft] = useState<Draft | null>(null);
  return <Context.Provider value={{ draft, saveDraft }}>{children}</Context.Provider>;
}
export function useDeploymentDraft() { const state = useContext(Context); if (!state) throw new Error('DeploymentDraftProvider is required'); return state; }
