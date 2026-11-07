import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { LOCAL_DATA } from '@/lib/localMode';
import { setActivePersona, type Persona } from '@/lib/api';

export type { Persona };
export type SecurityTier = 'full' | 'deidentified';

export interface PersonaDetails {
  id: Persona;
  email: string;
  label: string;
  badgeLabel: string;
  tier: SecurityTier;
  tierDescription: string;
  badgeColor: 'green' | 'purple';
}

export const PERSONAS: Record<Persona, PersonaDetails> = {
  nurse: {
    id: 'nurse',
    email: 'joey@jbatl.dev',
    label: 'Nurse Persona',
    badgeLabel: 'Nurse Persona (Full Clinical PHI)',
    tier: 'full',
    tierDescription: 'Full Clinical PHI (Identified)',
    badgeColor: 'green',
  },
  researcher: {
    id: 'researcher',
    email: 'researcher-demo@jbatl.dev',
    label: 'Researcher Persona',
    badgeLabel: 'Researcher Persona (De-identified - HIPAA Safe)',
    tier: 'deidentified',
    tierDescription: 'De-identified Research Tier (HIPAA Safe)',
    badgeColor: 'purple',
  },
};

interface PersonaContextValue {
  persona: Persona;
  details: PersonaDetails;
  isNurse: boolean;
  isResearcher: boolean;
  setPersona: (p: Persona) => void;
  togglePersona: () => void;
}

const PersonaContext = createContext<PersonaContextValue | undefined>(undefined);

const STORAGE_KEY = 'rayfin_active_persona';

export function PersonaProvider({ children }: { children: ReactNode }) {
  const [persona, setPersonaState] = useState<Persona>(() => {
    if (typeof window !== 'undefined') {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored === 'researcher' || stored === 'nurse') return stored;
      } catch {
        // Fall back to default
      }
    }
    return 'nurse';
  });

  const setPersona = useCallback((newPersona: Persona) => {
    setPersonaState(newPersona);
    setActivePersona(newPersona);
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(STORAGE_KEY, newPersona);
      } catch {
        // Ignore storage errors
      }
    }
    if (LOCAL_DATA) {
      void fetch('/local-api/persona', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona: newPersona }),
      }).catch(() => undefined);
    }
  }, []);

  const togglePersona = useCallback(() => {
    setPersona(persona === 'nurse' ? 'researcher' : 'nurse');
  }, [persona, setPersona]);

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

  const value: PersonaContextValue = {
    persona,
    details: PERSONAS[persona],
    isNurse: persona === 'nurse',
    isResearcher: persona === 'researcher',
    setPersona,
    togglePersona,
  };

  return <PersonaContext.Provider value={value}>{children}</PersonaContext.Provider>;
}

export function usePersona(): PersonaContextValue {
  const ctx = useContext(PersonaContext);
  if (!ctx) {
    return {
      persona: 'nurse',
      details: PERSONAS.nurse,
      isNurse: true,
      isResearcher: false,
      setPersona: () => undefined,
      togglePersona: () => undefined,
    };
  }
  return ctx;
}
