import { describe, expect, it } from 'vitest';
import {
  GLOSSARY,
  GLOSSARY_TERMS,
  getGlossaryDefinition,
  hasGlossaryTerm,
  normalizeGlossaryTerm,
} from './glossary';

describe('Fabric Glossary', () => {
  const REQUIRED_TERMS = [
    'OneLake',
    'shortcut',
    'Direct Lake',
    'Eventhouse',
    'Activator',
    'Data Agent',
    'Ontology',
  ] as const;

  it('declares all 7 foundational Fabric terms', () => {
    expect(GLOSSARY_TERMS).toHaveLength(7);
    for (const term of REQUIRED_TERMS) {
      expect(GLOSSARY[term]).toBeDefined();
      expect(GLOSSARY[term].length).toBeGreaterThan(20);
    }
  });

  it('matches exact definitions required by FR-1', () => {
    expect(GLOSSARY.OneLake).toBe(
      'Single, unified SaaS data lake for the entire organization — all data stored once in open Delta-Parquet format without data duplication.'
    );
    expect(GLOSSARY.shortcut).toBe(
      'Zero-copy virtualization link connecting data across lakes and external storage without moving or duplicating a single byte.'
    );
    expect(GLOSSARY['Direct Lake']).toBe(
      'Ultra-fast Power BI query mode that reads Delta Parquet files directly from OneLake storage in memory without importing or duplicating data.'
    );
    expect(GLOSSARY.Eventhouse).toBe(
      'Real-Time Intelligence database engine optimized for fast streaming telemetry, high-throughput append, and millisecond KQL queries.'
    );
    expect(GLOSSARY.Activator).toBe(
      'Action engine that monitors real-time streaming data for specific clinical patterns or threshold breaches and triggers automated alerts.'
    );
    expect(GLOSSARY['Data Agent']).toBe(
      'Fabric AI agent combining domain ontology, ground truth schemas, and LLM reasoning to answer natural-language healthcare queries.'
    );
    expect(GLOSSARY.Ontology).toBe(
      'Healthcare semantic graph (Ontology v2 / TMDL) defining clinical relationships, entities, and business definitions across disparate silos.'
    );
  });

  it('normalizes terms case-insensitively and handles common variations', () => {
    expect(normalizeGlossaryTerm('onelake')).toBe('OneLake');
    expect(normalizeGlossaryTerm('SHORTCUT')).toBe('shortcut');
    expect(normalizeGlossaryTerm('shortcuts')).toBe('shortcut');
    expect(normalizeGlossaryTerm('direct lake')).toBe('Direct Lake');
    expect(normalizeGlossaryTerm('DirectLake')).toBe('Direct Lake');
    expect(normalizeGlossaryTerm('eventhouse')).toBe('Eventhouse');
    expect(normalizeGlossaryTerm('activator')).toBe('Activator');
    expect(normalizeGlossaryTerm('data agent')).toBe('Data Agent');
    expect(normalizeGlossaryTerm('DataAgent')).toBe('Data Agent');
    expect(normalizeGlossaryTerm('ontology')).toBe('Ontology');
    expect(normalizeGlossaryTerm('ontologies')).toBe('Ontology');
    expect(normalizeGlossaryTerm('unknown_term')).toBeUndefined();
  });

  it('retrieves definitions via getGlossaryDefinition', () => {
    expect(getGlossaryDefinition('OneLake')).toContain('Single, unified SaaS data lake');
    expect(getGlossaryDefinition('shortcuts')).toContain('Zero-copy virtualization link');
    expect(getGlossaryDefinition('nonexistent')).toBeUndefined();
  });

  it('checks term existence with hasGlossaryTerm', () => {
    expect(hasGlossaryTerm('OneLake')).toBe(true);
    expect(hasGlossaryTerm('Eventhouse')).toBe(true);
    expect(hasGlossaryTerm('random')).toBe(false);
  });
});
