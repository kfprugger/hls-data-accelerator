/**
 * Microsoft Fabric Architectural & Clinical Glossary
 * 7 foundational Microsoft Fabric terms defined for clinical and IT stakeholders.
 */

export const GLOSSARY = {
  OneLake:
    'Single, unified SaaS data lake for the entire organization — all data stored once in open Delta-Parquet format without data duplication.',
  shortcut:
    'Zero-copy virtualization link connecting data across lakes and external storage without moving or duplicating a single byte.',
  'Direct Lake':
    'Ultra-fast Power BI query mode that reads Delta Parquet files directly from OneLake storage in memory without importing or duplicating data.',
  Eventhouse:
    'Real-Time Intelligence database engine optimized for fast streaming telemetry, high-throughput append, and millisecond KQL queries.',
  Activator:
    'Action engine that monitors real-time streaming data for specific clinical patterns or threshold breaches and triggers automated alerts.',
  'Data Agent':
    'Fabric AI agent combining domain ontology, ground truth schemas, and LLM reasoning to answer natural-language healthcare queries.',
  Ontology:
    'Healthcare semantic graph (Ontology v2 / TMDL) defining clinical relationships, entities, and business definitions across disparate silos.',
} as const;

export type GlossaryTerm = keyof typeof GLOSSARY;

export const GLOSSARY_TERMS = Object.keys(GLOSSARY) as GlossaryTerm[];

/**
 * Normalizes term lookup (case-insensitive and tolerant of plurals like "shortcuts").
 */
export function normalizeGlossaryTerm(term: string): GlossaryTerm | undefined {
  const clean = term.trim();
  if (clean in GLOSSARY) return clean as GlossaryTerm;

  const lower = clean.toLowerCase();
  for (const key of GLOSSARY_TERMS) {
    if (key.toLowerCase() === lower) return key;
  }

  // Handle common plural / variant forms
  if (lower === 'shortcuts') return 'shortcut';
  if (lower === 'data agents' || lower === 'dataagent') return 'Data Agent';
  if (lower === 'eventhouses') return 'Eventhouse';
  if (lower === 'directlake') return 'Direct Lake';
  if (lower === 'onelakes') return 'OneLake';
  if (lower === 'ontologies') return 'Ontology';

  return undefined;
}

export function getGlossaryDefinition(term: string): string | undefined {
  const key = normalizeGlossaryTerm(term);
  return key ? GLOSSARY[key] : undefined;
}

export function hasGlossaryTerm(term: string): boolean {
  return normalizeGlossaryTerm(term) !== undefined;
}
