/** Clinical vocabulary for the synthetic primary-care record: readable names, panels and reference ranges. */

export type Panel =
  | 'Vital signs'
  | 'Blood count'
  | 'Metabolic panel'
  | 'Liver'
  | 'Lipids'
  | 'Diabetes'
  | 'Blood gas'
  | 'Urinalysis'
  | 'Other tests'
  | 'Screening'
  | 'Social needs'
  | 'Examination';

type Def = { re: RegExp; name: string; panel: Panel; ref?: [number, number]; order: number };

/** Typical adult reference ranges, for orientation only. */
const DEFS: Def[] = [
  { re: /^Body Height/, name: 'Height', panel: 'Vital signs', order: 1 },
  { re: /^Body Weight/, name: 'Weight', panel: 'Vital signs', order: 2 },
  { re: /^Body mass index \(BMI\) \[Ratio\]/, name: 'Body mass index', panel: 'Vital signs', ref: [18.5, 24.9], order: 3 },
  { re: /^Systolic Blood Pressure/, name: 'Systolic BP', panel: 'Vital signs', ref: [90, 129], order: 4 },
  { re: /^Diastolic Blood Pressure/, name: 'Diastolic BP', panel: 'Vital signs', ref: [60, 79], order: 5 },
  { re: /^Heart rate/, name: 'Heart rate', panel: 'Vital signs', ref: [60, 100], order: 6 },
  { re: /^Respiratory rate/, name: 'Respiratory rate', panel: 'Vital signs', ref: [12, 20], order: 7 },
  { re: /^Body temperature/, name: 'Temperature', panel: 'Vital signs', ref: [36.1, 37.5], order: 8 },
  { re: /^Oxygen saturation/, name: 'Oxygen saturation', panel: 'Vital signs', ref: [95, 100], order: 9 },
  { re: /^Pain severity/, name: 'Pain (0–10)', panel: 'Vital signs', ref: [0, 3], order: 10 },
  { re: /^Head Occipital-frontal circumference Percentile/, name: 'Head circumference percentile', panel: 'Vital signs', order: 12 },
  { re: /^Head Occipital-frontal circumference/, name: 'Head circumference', panel: 'Vital signs', order: 11 },
  { re: /^Weight-for-length Per age and sex/, name: 'Weight-for-length percentile', panel: 'Vital signs', order: 13 },
  { re: /^Body mass index \(BMI\) \[Percentile\]/, name: 'BMI percentile', panel: 'Vital signs', order: 14 },

  { re: /^Hemoglobin A1c/, name: 'HbA1c', panel: 'Diabetes', ref: [4, 5.6], order: 1 },
  { re: /^Glucose \[Mass\/volume\] in (Blood|Serum)/, name: 'Glucose', panel: 'Metabolic panel', ref: [70, 99], order: 1 },
  { re: /^Urea nitrogen/, name: 'Urea nitrogen (BUN)', panel: 'Metabolic panel', ref: [7, 20], order: 2 },
  { re: /^Creatinine/, name: 'Creatinine', panel: 'Metabolic panel', ref: [0.6, 1.3], order: 3 },
  { re: /^Glomerular filtration rate/, name: 'eGFR', panel: 'Metabolic panel', ref: [60, 200], order: 4 },
  { re: /^Sodium/, name: 'Sodium', panel: 'Metabolic panel', ref: [136, 145], order: 5 },
  { re: /^Potassium/, name: 'Potassium', panel: 'Metabolic panel', ref: [3.5, 5.1], order: 6 },
  { re: /^Chloride/, name: 'Chloride', panel: 'Metabolic panel', ref: [98, 107], order: 7 },
  { re: /^Carbon dioxide {1,2}total/, name: 'Bicarbonate', panel: 'Metabolic panel', ref: [22, 29], order: 8 },
  { re: /^Calcium/, name: 'Calcium', panel: 'Metabolic panel', ref: [8.5, 10.2], order: 9 },
  { re: /^Magnesium/, name: 'Magnesium', panel: 'Metabolic panel', ref: [1.7, 2.2], order: 10 },
  { re: /^Protein \[Mass\/volume\] in Serum/, name: 'Total protein', panel: 'Liver', ref: [6, 8.3], order: 1 },
  { re: /^Albumin \[Mass\/volume\] in Serum/, name: 'Albumin', panel: 'Liver', ref: [3.5, 5], order: 2 },
  { re: /^Bilirubin\.total/, name: 'Bilirubin', panel: 'Liver', ref: [0.1, 1.2], order: 3 },
  { re: /^Alkaline phosphatase/, name: 'Alkaline phosphatase', panel: 'Liver', ref: [44, 147], order: 4 },
  { re: /^Alanine aminotransferase/, name: 'ALT', panel: 'Liver', ref: [7, 56], order: 5 },
  { re: /^Aspartate aminotransferase/, name: 'AST', panel: 'Liver', ref: [10, 40], order: 6 },
  { re: /^Cholesterol \[Mass\/volume\]/, name: 'Total cholesterol', panel: 'Lipids', ref: [0, 199], order: 1 },
  { re: /^Cholesterol in LDL/, name: 'LDL cholesterol', panel: 'Lipids', ref: [0, 129], order: 2 },
  { re: /^Cholesterol in HDL/, name: 'HDL cholesterol', panel: 'Lipids', ref: [40, 200], order: 3 },
  { re: /^Triglyceride/, name: 'Triglycerides', panel: 'Lipids', ref: [0, 149], order: 4 },
  { re: /^Hemoglobin \[Mass\/volume\] in Blood/, name: 'Haemoglobin', panel: 'Blood count', ref: [12, 17.5], order: 1 },
  { re: /^Hematocrit/, name: 'Haematocrit', panel: 'Blood count', ref: [36, 52], order: 2 },
  { re: /^Leukocytes/, name: 'White cells', panel: 'Blood count', ref: [4, 11], order: 3 },
  { re: /^Erythrocytes \[#/, name: 'Red cells', panel: 'Blood count', ref: [4, 5.9], order: 4 },
  { re: /^Platelets \[#/, name: 'Platelets', panel: 'Blood count', ref: [150, 450], order: 5 },
  { re: /^MCV/, name: 'MCV', panel: 'Blood count', ref: [80, 100], order: 6 },
  { re: /^MCH \[/, name: 'MCH', panel: 'Blood count', ref: [27, 33], order: 7 },
  { re: /^MCHC/, name: 'MCHC', panel: 'Blood count', ref: [32, 36], order: 8 },
  { re: /^Erythrocyte \[DistWidth\]/, name: 'RDW', panel: 'Blood count', ref: [11.5, 14.5], order: 9 },
  { re: /^Platelet distribution width/, name: 'PDW', panel: 'Blood count', order: 10 },
  { re: /^Platelet \[Entitic mean volume\]/, name: 'MPV', panel: 'Blood count', ref: [7.5, 11.5], order: 11 },
  { re: /^pH of Arterial blood/, name: 'pH', panel: 'Blood gas', ref: [7.35, 7.45], order: 1 },
  { re: /^Carbon dioxide \[Partial pressure\]/, name: 'pCO₂', panel: 'Blood gas', ref: [35, 45], order: 2 },
  { re: /^Oxygen \[Partial pressure\]/, name: 'pO₂', panel: 'Blood gas', ref: [75, 100], order: 3 },
  { re: /^Bicarbonate \[Moles\/volume\] in Arterial/, name: 'HCO₃', panel: 'Blood gas', ref: [22, 26], order: 4 },

  { re: /PHQ-2\)/, name: 'PHQ-2 depression screen', panel: 'Screening', order: 1 },
  { re: /Patient Health Questionnaire-9|PHQ-9/, name: 'PHQ-9 depression score', panel: 'Screening', order: 2 },
  { re: /GAD-7/, name: 'GAD-7 anxiety score', panel: 'Screening', order: 3 },
  { re: /AUDIT-C/, name: 'AUDIT-C alcohol score', panel: 'Screening', order: 4 },
  { re: /DAST-10/, name: 'DAST-10 drug use score', panel: 'Screening', order: 5 },
  { re: /HARK/, name: 'HARK partner-violence screen', panel: 'Screening', order: 6 },
  { re: /Morse Fall Scale/, name: 'Fall risk (Morse)', panel: 'Screening', order: 7 },
  { re: /^Tobacco smoking status/, name: 'Tobacco', panel: 'Screening', order: 8 },

  { re: /^Housing status/, name: 'Housing', panel: 'Social needs', order: 1 },
  { re: /worried about losing your housing/, name: 'Worried about losing housing', panel: 'Social needs', order: 2 },
  { re: /^How many people are living/, name: 'People in household', panel: 'Social needs', order: 3 },
  { re: /^Employment status/, name: 'Employment', panel: 'Social needs', order: 4 },
  { re: /^Highest level of education/, name: 'Education', panel: 'Social needs', order: 5 },
  { re: /^Primary insurance/, name: 'Insurance', panel: 'Social needs', order: 6 },
  { re: /total income of all family members/, name: 'Household income', panel: 'Social needs', order: 7 },
  { re: /unable to get any of the following/, name: 'Unmet needs', panel: 'Social needs', order: 8 },
  { re: /lack of transportation/, name: 'Transport barrier', panel: 'Social needs', order: 9 },
  { re: /^Stress level/, name: 'Stress', panel: 'Social needs', order: 10 },
  { re: /How often do you see or talk to people/, name: 'Social contact', panel: 'Social needs', order: 11 },
  { re: /physically and emotionally safe/, name: 'Feels safe at home', panel: 'Social needs', order: 12 },
  { re: /afraid of your partner/, name: 'Afraid of partner', panel: 'Social needs', order: 13 },
  { re: /^Are you a refugee/, name: 'Refugee', panel: 'Social needs', order: 14 },
  { re: /jail {1,2}prison/, name: 'Recent incarceration', panel: 'Social needs', order: 15 },
  { re: /Armed Forces/, name: 'Veteran', panel: 'Social needs', order: 16 },
  { re: /migrant farm work/, name: 'Seasonal farm work', panel: 'Social needs', order: 17 },
];

export interface ObsDef {
  name: string;
  panel: Panel;
  ref?: [number, number];
  order: number;
}

const cache = new Map<string, ObsDef>();

export function describe(raw: string, category: string | null): ObsDef {
  const key = `${category}|${raw}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const d = DEFS.find((x) => x.re.test(raw));
  const def: ObsDef = d
    ? { name: d.name, panel: d.panel, ref: d.ref, order: d.order }
    : {
        name: raw.replace(/\s*\[[^\]]*\]/g, '').replace(/ in (Blood|Serum or Plasma|Urine).*$/, '').trim(),
        panel: /Urine/.test(raw) ? 'Urinalysis' : category === 'exam' ? 'Examination' : category === 'survey' ? 'Screening' : 'Other tests',
        order: 99,
      };
  cache.set(key, def);
  return def;
}

export function flag(value: number | null, ref?: [number, number]): 'high' | 'low' | null {
  if (value === null || !ref) return null;
  if (value > ref[1]) return 'high';
  if (value < ref[0]) return 'low';
  return null;
}

/** Plain reading of a screening score, using the usual cut-offs. */
export function interpretScore(name: string, value: number | null, sex: string | null): string | null {
  if (value === null) return null;
  if (name.startsWith('PHQ-2')) return value >= 3 ? 'positive screen' : 'negative';
  if (name.startsWith('PHQ-9')) return value >= 20 ? 'severe' : value >= 15 ? 'moderately severe' : value >= 10 ? 'moderate' : value >= 5 ? 'mild' : 'minimal';
  if (name.startsWith('GAD-7')) return value >= 15 ? 'severe' : value >= 10 ? 'moderate' : value >= 5 ? 'mild' : 'minimal';
  if (name.startsWith('AUDIT-C')) return value >= ((sex ?? '').toLowerCase().startsWith('f') ? 3 : 4) ? 'positive screen' : 'negative';
  if (name.startsWith('DAST-10')) return value >= 6 ? 'substantial' : value >= 3 ? 'moderate' : value >= 1 ? 'low' : 'none';
  if (name.startsWith('HARK')) return value >= 1 ? 'positive screen' : 'negative';
  return null;
}

/** "General examination of patient (procedure)" -> "General examination of patient". */
export function term(text: string | null | undefined): string {
  if (!text) return '';
  return text.replace(/\s*\((procedure|disorder|finding|situation|regime\/therapy|observable entity|qualifier value|person|event|morphologic abnormality|physical object)\)/gi, '').trim();
}

/** Readable medicine name: brand packs keep the brand, tablets drop the dose form. */
const tidyDrugText = (t: string) =>
  t
    .replace(/\bMG\b/g, 'mg')
    .replace(/\bML\b/g, 'mL')
    .replace(/\bUNT\b/g, 'units')
    .replace(/\/ACTUAT\b/g, ' per dose')
    // Tall-man lettering (amLODIPine) back to plain lower case.
    .replace(/\b([a-z]*[A-Z]{2,}[a-zA-Z]*)\b/g, (w) => (/[a-z]/.test(w) ? w.toLowerCase() : w))
    .replace(/\s{2,}/g, ' ')
    .trim();

const capitalise = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

/** Full prescribed product (strength and form), with RxNorm casing tidied. */
export function product(text: string | null | undefined): string {
  if (!text) return '';
  return capitalise(tidyDrugText(text.replace(/^(\d+) ACTUAT\s+/, '$1-dose ').replace(/^(\d+) HR\s+/, '$1-hour ')));
}

export function medicine(text: string | null | undefined): string {
  if (!text) return '';
  const brand = /\[([^\]]+)\]/.exec(text)?.[1];
  if (text.startsWith('{') && brand) return brand;
  let t = tidyDrugText(
    text
      .replace(/\s*\[[^\]]+\]/g, '')
      .replace(/^\d+ (HR|ML|ACTUAT)\s+/i, '')
      .replace(/\s*(Extended Release|Delayed Release|Oral Tablet|Oral Capsule|Chewable Tablet|Oral Solution|Oral Suspension|Injectable Solution|Injection|Prefilled Syringe|Auto-Injector|Dry Powder Inhaler|Metered Dose Inhaler|Inhalation Solution|Mucosal Spray|Topical Cream|Nasal Spray|Transdermal System|Ophthalmic Solution|Oral Gel|Vaginal Ring)\b/gi, '')
  );
  if (brand && t.length > 42) t = brand;
  return capitalise(t);
}

export const VISIT_CLASS: Record<string, { label: string; row: number }> = {
  wellness: { label: 'Wellness visit', row: 0 },
  ambulatory: { label: 'Office visit', row: 1 },
  outpatient: { label: 'Outpatient visit', row: 1 },
  urgentcare: { label: 'Urgent care', row: 1 },
  virtual: { label: 'Virtual visit', row: 1 },
  home: { label: 'Home visit', row: 1 },
  emergency: { label: 'Emergency department', row: 2 },
  inpatient: { label: 'Hospital admission', row: 2 },
  snf: { label: 'Skilled nursing stay', row: 2 },
  hospice: { label: 'Hospice', row: 2 },
};

const DRUG_CLASS: Record<string, 'targeted' | 'hormone' | 'immuno'> = {
  trastuzumab: 'targeted', erlotinib: 'targeted', gefitinib: 'targeted', sunitinib: 'targeted', axitinib: 'targeted',
  sorafenib: 'targeted', everolimus: 'targeted', bevacizumab: 'targeted', cetuximab: 'targeted', temsirolimus: 'targeted',
  pazopanib: 'targeted', anastrozole: 'hormone', leuprolide: 'hormone', tamoxifen: 'hormone', letrozole: 'hormone',
  'bcg solution': 'immuno', interferon: 'immuno',
};

export function drugClass(agent: string | null, type: string | null): 'chemo' | 'targeted' | 'hormone' | 'immuno' {
  const a = (agent ?? '').toLowerCase();
  const hit = Object.entries(DRUG_CLASS).find(([k]) => a.includes(k));
  if (hit) return hit[1];
  if ((type ?? '').toLowerCase().includes('hormone')) return 'hormone';
  if ((type ?? '').toLowerCase().includes('immuno')) return 'immuno';
  return 'chemo';
}

/** Body systems for conditions on the timeline; a medicine takes the system of the condition it treats. */
export type BodySystem = 'circulation' | 'metabolic' | 'respiratory' | 'urogenital' | 'mental' | 'musculoskeletal' | 'oral' | 'other';

export const SYSTEMS: Record<BodySystem, { label: string; colour: string }> = {
  circulation: { label: 'Heart and circulation', colour: 'var(--sys-circ)' },
  metabolic: { label: 'Metabolic and weight', colour: 'var(--sys-meta)' },
  respiratory: { label: 'Ear, nose, throat and lungs', colour: 'var(--sys-resp)' },
  urogenital: { label: 'Kidney, bladder and pregnancy', colour: 'var(--sys-uro)' },
  mental: { label: 'Mental health, sleep and social', colour: 'var(--sys-mind)' },
  musculoskeletal: { label: 'Bones, joints and injury', colour: 'var(--sys-msk)' },
  oral: { label: 'Mouth and teeth', colour: 'var(--sys-oral)' },
  other: { label: 'Other', colour: 'var(--sys-other)' },
};

const SYSTEM_RULES: [BodySystem, RegExp][] = [
  ['oral', /dental|gingiv|teeth|tooth|jaw|periodont/i],
  ['circulation', /hypertens|heart|cardi|myocard|mitral|aortic|atrial|coronary|stroke|vascul|thromb|embol|angina/i],
  ['metabolic', /diabet|glyc|obes|body mass|metabolic|lipid|cholesterol|triglycer|thyroid|gout/i],
  ['respiratory', /sinus|pharyng|bronch|pulmonary|lung|asthma|pneumon|otitis|throat|apnea|airway|rhinit|influenza|cough/i],
  ['urogenital', /cystitis|urinary|kidney|renal|bladder|prostat|pregnan|eclampsia|miscarriage|ovum|menopaus/i],
  ['mental', /sleep|depress|anxiety|stress|drug|alcohol|substance|employ|isolation|violence|dementia|cognit|social|housing/i],
  ['musculoskeletal', /osteo|arthrit|fracture|sprain|injury|laceration|back pain|joint|whiplash|concussion|burn/i],
];

export function bodySystem(name: string | null | undefined): BodySystem {
  if (!name) return 'other';
  return SYSTEM_RULES.find(([, re]) => re.test(name))?.[0] ?? 'other';
}

export const CLASS_STYLE = {
  chemo: { fill: 'var(--ink)', label: 'Chemotherapy' },
  targeted: { fill: 'var(--c-gen)', label: 'Targeted therapy' },
  hormone: { fill: 'var(--bg)', label: 'Hormone therapy' },
  immuno: { fill: 'var(--c-path)', label: 'Immunotherapy' },
};

