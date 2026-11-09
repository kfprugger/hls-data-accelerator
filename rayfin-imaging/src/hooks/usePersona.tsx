import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { LOCAL_DATA } from '@/lib/localMode';
import { setActivePersona, type Persona } from '@/lib/api';

export type { Persona };
export type SecurityTier = 'full' | 'deidentified';

export interface PersonaDetails {
  id: Persona;
  account: string;
  label: string;
  badgeLabel: string;
  tier: SecurityTier;
  tierDescription: string;
  badgeColor: 'green' | 'purple';
}

export const PERSONAS: Record<Persona, PersonaDetails> = {
  nurse: {
    id: 'nurse',
    account: 'Clinical user',
    label: 'Nurse Persona',
    badgeLabel: 'Nurse Persona (Full Clinical PHI)',
    tier: 'full',
    tierDescription: 'Full Clinical PHI (Identified)',
    badgeColor: 'green',
  },
  researcher: {
    id: 'researcher',
    account: 'researcher-demo',
    label: 'Researcher Persona',
    badgeLabel: 'Researcher Persona (De-identified - HIPAA Safe)',
    tier: 'deidentified',
    tierDescription: 'De-identified Research Tier (HIPAA Safe)',
    badgeColor: 'purple',
  },
};

/** Tier the server actually applied to a response; the server decides masking from the caller's token. */
export function servedPersonaOf(res: { persona?: Persona; isDeidentified?: boolean } | null | undefined): Persona | null {
  if (!res) return null;
  if (res.isDeidentified === true || res.persona === 'researcher') return 'researcher';
  if (res.isDeidentified === false || res.persona === 'nurse') return 'nurse';
  return null;
}

interface PersonaContextValue {
  /** Persona the client asks for. The server may only honour it as a downgrade to the de-identified tier. */
  persona: Persona;
  /** Tier the server last reported, or null before the first response under the current request. */
  servedPersona: Persona | null;
  /** Details of the tier shown to the user: the served tier once known. */
  details: PersonaDetails;
  isNurse: boolean;
  isResearcher: boolean;
  setPersona: (p: Persona) => void;
  togglePersona: () => void;
  reportServedPersona: (p: Persona | null) => void;
}

const PersonaContext = createContext<PersonaContextValue | undefined>(undefined);

const STORAGE_KEY = 'rayfin_active_persona';

export function PersonaProvider({ children }: { children: ReactNode }) {
  const [persona, setPersonaState] = useState<Persona>(() => {
    // Hosted mode has no persona switch: the token decides, so a stale stored choice must not leak in.
    if (LOCAL_DATA && typeof window !== 'undefined') {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored === 'researcher' || stored === 'nurse') return stored;
      } catch {
        // Fall back to default
      }
    }
    return 'nurse';
  });
  const [servedPersona, setServedPersona] = useState<Persona | null>(null);

  const setPersona = useCallback((newPersona: Persona) => {
    setPersonaState(newPersona);
    setServedPersona(null);
    setActivePersona(newPersona);
    if (LOCAL_DATA && typeof window !== 'undefined') {
      try {
        localStorage.setItem(STORAGE_KEY, newPersona);
      } catch {
        // Ignore storage errors
      }
    }
  }, []);

  const togglePersona = useCallback(() => {
    setPersona(persona === 'nurse' ? 'researcher' : 'nurse');
  }, [persona, setPersona]);

  const reportServedPersona = useCallback((p: Persona | null) => {
    if (p) setServedPersona(p);
  }, []);

  useEffect(() => {
    setActivePersona(persona);
    if (LOCAL_DATA) {
      void fetch('/local-api/persona', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona }),
      }).catch(() => undefined);
    }
  }, [persona]);

  const shown = servedPersona ?? 'nurse';
  const value: PersonaContextValue = {
    persona,
    servedPersona,
    details: PERSONAS[shown],
    isNurse: shown === 'nurse',
    isResearcher: shown === 'researcher',
    setPersona,
    togglePersona,
    reportServedPersona,
  };

  return <PersonaContext.Provider value={value}>{children}</PersonaContext.Provider>;
}

export function usePersona(): PersonaContextValue {
  const ctx = useContext(PersonaContext);
  if (!ctx) {
    return {
      persona: 'nurse',
      servedPersona: null,
      details: PERSONAS.nurse,
      isNurse: true,
      isResearcher: false,
      setPersona: () => undefined,
      togglePersona: () => undefined,
      reportServedPersona: () => undefined,
    };
  }
  return ctx;
}
