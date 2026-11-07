/**
 * Plain-language explanations for non-clinical viewers: what each image shows, what each control does,
 * and the vocabulary used in the app. Shown in the Guide tab, in each workspace's "In plain words" panel
 * and as tooltips. Slide, study, layer and marker keys are the catalog ids; add an entry when the
 * catalog grows (anything without one falls back to its catalog description).
 */

export interface Term {
  term: string;
  text: string;
}

export interface ImageNote {
  plain: string;
  lookFor: string[];
  /** Per-layer explanations, keyed by layer id (volume studies). */
  layers?: Record<string, string>;
}

export const SLIDE_NOTES: Record<string, ImageNote> = {
  'brain-gbm': {
    plain:
      'A slice of glioblastoma, the most common and most aggressive cancer that starts in the brain in adults. Like almost every pathology slide it is stained with two dyes: haematoxylin turns cell nuclei (the part of each cell that holds its DNA) purple, and eosin turns everything else pink. Healthy brain has small, evenly spaced nuclei; here they are crowded, large and irregular.',
    lookFor: [
      'Zoom to 20× and compare the crowded, dark, misshapen nuclei with calmer areas nearby.',
      'Bright red patches are fresh bleeding (haemorrhage), common in this fast-growing tumour.',
      'Pale pink zones with few nuclei, where you find them, are dead tissue (necrosis), one of the features pathologists use to diagnose glioblastoma.',
    ],
  },
  'lung-luad': {
    plain:
      'Lung adenocarcinoma, the most common type of lung cancer, including in people who have never smoked. It grows from the cells that line the lung’s tiny air sacs. Normal lung looks like lace: thin walls around empty air spaces. The cancer fills those spaces with solid clusters and gland-like rings of cells.',
    lookFor: [
      'Find an edge where lacy, open lung meets dense purple tumour.',
      'At 20× to 40×, look for rings of tumour cells (glands), the feature that gives adenocarcinoma its name.',
      'The thin white cracks are artefacts from cutting the tissue, not disease.',
    ],
  },
  'lung-lusc': {
    plain:
      'Squamous cell carcinoma of the lung, a cancer strongly linked to smoking. It grows from the flat cells that line the airways and forms solid nests of large cells with plenty of pink cytoplasm (the body of the cell around its nucleus).',
    lookFor: [
      'Look for islands of pink tumour cells surrounded by paler supporting tissue.',
      'Swirls of glassy, bright pink material, where present, are keratin: the protein in skin and nails, and a tell-tale sign of squamous cancer.',
      'Compare with the lung adenocarcinoma slide: nests here, glands there.',
    ],
  },
  'kidney-kirc': {
    plain:
      'Clear cell renal cell carcinoma, the most common kidney cancer in adults. Its cells are packed with fat and sugar stores that dissolve when the tissue is processed, so they look empty or clear. A fine net of small blood vessels runs between them; this tumour is known for building a rich blood supply.',
    lookFor: [
      'At 10×, notice the pale, almost empty-looking cells grouped in nests.',
      'The thin red lines around each nest are tiny blood vessels, often described as chicken wire.',
      'Press Tour to fly through the most cell-dense areas.',
    ],
  },
  'colon-coad': {
    plain:
      'Colon adenocarcinoma, cancer of the large bowel. Most cases start as a polyp in the bowel lining. Healthy lining is made of crypts: tubes of cells standing side by side like test tubes in a rack. Cancer builds irregular, crowded glands that push deeper into the bowel wall.',
    lookFor: [
      'Along one edge, find the neat, evenly spaced normal crypts.',
      'Move inward to where the glands become irregular, branched and packed back to back.',
      'Debris inside tumour glands is common in bowel cancer.',
    ],
  },
  'breast-brca': {
    plain:
      'Invasive breast carcinoma, the most common cancer in women. Invasive means the cancer has broken out of the milk ducts or lobules where it began and is growing into the surrounding tissue. The large white spaces are fat cells: fat dissolves during processing and leaves empty outlines.',
    lookFor: [
      'Start at 1.25× to see purple tumour spreading between the white fat.',
      'Zoom to 40× at the edge, where single tumour cells creep between fat cells.',
      'Pin a region, then open the slide in another browser to show that pins are shared.',
    ],
  },
  'rectum-read': {
    plain:
      'Rectal adenocarcinoma, cancer of the last part of the large bowel, which behaves much like colon cancer. The tumour glands here are complex and sieve-like (cribriform), set in scar-like tissue (desmoplastic stroma) that the body lays down around invading cancer.',
    lookFor: [
      'Look for glands with several holes in them, like a sieve.',
      'The paler, wavy pink tissue around them is the scar-like reaction to the tumour.',
    ],
  },
  'skin-skcm': {
    plain:
      'Cutaneous melanoma, a cancer of melanocytes, the cells that make skin pigment. It is the most dangerous common skin cancer because it can spread early. The outer layer of skin (epidermis) runs along one edge and the tumour grows down into the layer beneath (dermis). How deep it reaches, in millimetres, is the most important single measure for staging it.',
    lookFor: [
      'Find the thin purple band of epidermis along the edge of the tissue.',
      'Follow the tumour cells down into the deeper tissue; the scale bar shows how far that is.',
      'Brown granules, where present, are melanin pigment.',
    ],
  },
  'stomach-stad': {
    plain:
      'Gastric adenocarcinoma, cancer of the stomach lining. Two pieces of tissue are joined by tumour, with some remaining normal stomach lining (mucosa) at the surface.',
    lookFor: [
      'Compare the orderly normal lining at the surface with the disorganised tumour beneath it.',
      'Look for small groups of tumour cells pushing into the stomach wall.',
    ],
  },
  'thyroid-thca': {
    plain:
      'Papillary thyroid carcinoma, the most common thyroid cancer and usually very treatable. It grows as finger-like projections (papillae), each with a thin core of tissue and blood vessels covered by tumour cells. Pathologists diagnose it mostly from the nuclei, which are pale, overlapping and often grooved.',
    lookFor: [
      'At 5× to 10×, look for branching, finger-like papillae.',
      'At 40×, look at the nuclei: pale and empty-looking rather than dark purple.',
    ],
  },
  'prostate-prad': {
    plain:
      'Prostate adenocarcinoma, one of the most common cancers in men. Normal prostate glands are large with wavy edges; cancer forms small, crowded glands that squeeze in between them. Pathologists grade how disorganised these glands are with the Gleason score, which guides treatment.',
    lookFor: [
      'Find the large, wavy benign glands, then the small, round, crowded tumour glands beside them.',
      'The more the small glands fuse together or lose their round shape, the higher the grade.',
    ],
  },
  'pancreas-paad': {
    plain:
      'Pancreatic ductal adenocarcinoma, one of the most aggressive cancers. Tumour cells form irregular ducts scattered through dense, scar-like tissue, which is one reason it is hard to treat. Fat and congested blood vessels lie alongside.',
    lookFor: [
      'Look for scattered, irregular ducts in pale pink fibrous tissue.',
      'Compare the dense scar-like tissue with the white fat next to it.',
    ],
  },
  'ovary-ov': {
    plain:
      'High-grade serous carcinoma, the most common type of ovarian cancer. It is densely packed with cells, has slit-like spaces and finger-like fronds, and its nuclei vary widely in size and shape.',
    lookFor: [
      'At 20× to 40×, compare neighbouring nuclei: large, very variable nuclei mean a high grade.',
      'Look for slit-like spaces between clusters of tumour cells.',
    ],
  },
  'colon-cycif': {
    plain:
      'The same kind of bowel cancer as the colon H&E slide, imaged a different way. Instead of two dyes, the tissue was stained in rounds with antibodies, each of which sticks to one protein and carries a fluorescent tag. The microscope photographed every protein separately, 36 in all. Each one is a marker, shown here in its own colour on black and switched on or off like layers on a map.',
    lookFor: [
      'Switch everything off except DNA: each blue dot is the nucleus of one cell.',
      'Add Pan-cytokeratin (yellow) to see the tumour glands, then SMA (pink) for the muscle and support tissue around them.',
      'Add CD8a (magenta) to find killer T cells. Whether they get inside the tumour or stay at its edge matters for treatment.',
    ],
  },
};

const HE_FALLBACK: ImageNote = {
  plain:
    'A thin slice of tissue stained with haematoxylin and eosin: cell nuclei are purple and everything else is pink. Pathologists diagnose cancer from how the cells and their nuclei look and how they are arranged.',
  lookFor: ['Start at 1.25× for the overall pattern, then zoom to 20× or 40× to see individual cells.'],
};

const FLUORESCENCE_FALLBACK: ImageNote = {
  plain:
    'Tissue stained with fluorescent antibodies, each sticking to one protein. Each marker is shown in its own colour and can be switched on and off.',
  lookFor: ['Switch markers on one at a time to see which cells carry each protein.'],
};

export function slideNote(id: string, kind?: string): ImageNote {
  return SLIDE_NOTES[id] ?? (kind === 'fluorescence' ? FLUORESCENCE_FALLBACK : HE_FALLBACK);
}

/** Multiplex immunofluorescence markers, keyed by channel id. */
export const MARKER_NOTES: Record<string, { name: string; shows: string; why: string }> = {
  dna: {
    name: 'DNA',
    shows: 'The nucleus of every cell, stained with a DNA dye (Hoechst).',
    why: 'Shows where all the cells are, so the other markers have context.',
  },
  'pan-cytokeratin': {
    name: 'Pan-cytokeratin',
    shows: 'Keratin proteins in epithelial cells, the cells that line organs and glands.',
    why: 'Bowel cancer grows from this lining, so it outlines the tumour glands and any normal lining.',
  },
  'aortic-smooth-muscle-actin': {
    name: 'SMA (smooth muscle actin)',
    shows: 'Smooth muscle actin (SMA): muscle in the bowel wall and blood vessels, and activated support cells.',
    why: 'Shows the muscle and the supporting tissue (stroma) the tumour grows into.',
  },
  cd45: {
    name: 'CD45',
    shows: 'A protein on the surface of every white blood cell.',
    why: 'Shows all the immune cells and how many have reached the tumour.',
  },
  cd8a: {
    name: 'CD8a',
    shows: 'Cytotoxic, or killer, T cells.',
    why: 'They attack cancer cells directly. In bowel cancer, more of them inside the tumour usually means a better outlook; many immunotherapies aim to unleash them.',
  },
  cd68: {
    name: 'CD68',
    shows: 'Macrophages, large immune cells that swallow debris and germs.',
    why: 'In tumours they can either fight the cancer or help it grow, depending on their state.',
  },
  'antigen-ki67': {
    name: 'Ki-67',
    shows: 'Ki-67, a protein found in cells that are growing and dividing, but not in resting cells.',
    why: 'A high share of Ki-67-positive cells means a fast-growing tumour.',
  },
  cd31: {
    name: 'CD31',
    shows: 'The cells that line blood vessels (endothelium).',
    why: 'Shows the tumour’s blood supply.',
  },
};

export const MULTIPLEX_BASICS =
  'A marker is one protein made visible. The tissue is treated with an antibody that sticks only to that protein and carries a dye that glows under a particular light. Cyclic immunofluorescence (CyCIF) repeats this in rounds, photographing a few markers at a time and then bleaching them, until dozens of proteins have been recorded on the same slice. 36-plex means 36 proteins were measured; eight of the most informative are shown here. Each marker chip switches one protein on or off, so you can see which cells are tumour, which are immune cells, and where they meet.';

export const STUDY_NOTES: Record<string, ImageNote> = {
  'petct-whole-body': {
    plain:
      'Two scans taken together on one machine. The CT is a 3D X-ray that shows anatomy, with bone brightest. For the PET, the patient was injected with a tiny amount of radioactive sugar (FDG). Cells that burn a lot of sugar collect more of it and glow: many cancers do, but so do the brain and heart, and the kidneys and bladder glow because they clear the tracer from the body. Doctors look for glowing spots where there should not be any.',
    lookFor: [
      'Press Spin: hotspots in the chest and abdomen, away from the heart, kidneys and bladder, are tumour deposits.',
      'Switch to MIP. This rotating, film-negative view is how PET is usually read: darker means more sugar uptake.',
      'Turn on Expert lesion masks in Details › Controls to see what specialists outlined as tumour.',
    ],
    layers: {
      ct: 'The CT scan: anatomy and bone.',
      pet: 'Sugar uptake measured in SUV (standardised uptake value), adjusted for the dose and the patient’s weight. Brighter means more.',
      lesions: 'Tumours outlined by specialists for the research collection.',
    },
  },
  'totalseg-ct-angio': {
    plain:
      'A CT scan taken after a contrast dye was injected into the blood, which makes blood vessels show up brightly (angiography). Every major organ, vessel, bone and muscle, 107 structures in all, has been outlined and given its own colour, so you can explore the body like an anatomy textbook.',
    lookFor: [
      'Untick CT in Details › Controls to see only the coloured anatomy.',
      'Turn on Clip and drag the slider to cut through the body from the front.',
      'Open MIP to see the contrast-filled vessels with the bones removed.',
    ],
    layers: {
      ct: 'The CT scan.',
      structures: 'Coloured outlines of 107 organs, vessels, bones and muscles. Arteries are red, veins blue.',
    },
  },
  'visible-human-body': {
    plain:
      'Real colour, not a scan. In the 1990s a donated body was frozen, shaved away a third of a millimetre at a time, and every newly exposed surface was photographed. Stacked back together, the 5,186 photographs form a 3D body in true colour: yellow fat, red muscle, white bone and the grey-white of the brain.',
    lookFor: [
      'Drag the clip slider to move the cut through the body.',
      'Switch the cut to Side or Top to slice in other directions.',
    ],
    layers: { rgb: 'The stacked colour photographs.' },
  },
  'visible-human-head': {
    plain:
      'The head and neck of the same donor in 1 mm detail, cut down the middle. You can see the brain, the cerebellum at the back, the tongue, airway and spinal cord in their natural colours.',
    lookFor: [
      'Drag the clip slider slowly to travel through the head from one side to the other.',
      'Switch the cut to Front or Top to slice in other directions.',
    ],
    layers: { rgb: 'The stacked colour photographs.' },
  },
  'lung-4dct': {
    plain:
      'A CT scan of a lung cancer patient taken across a whole breath: ten volumes from breathing in to breathing out. Radiotherapy teams use it to see how far the tumour moves as the patient breathes, so the radiation beam covers it at every moment while sparing healthy lung. The lungs are drawn as translucent glass so you can see what moves inside them.',
    lookFor: [
      'Press Play and watch the lungs fill and empty by about 843 ml, a little under a litre.',
      'Orange is the tumour, light blue the airway, dark red the heart and ivory the spine.',
      'Press Spin while it breathes.',
    ],
    layers: {
      ct: 'The CT scan. In 3D, the Lungs (glass) colour setting shows air-filled lung as translucent pink.',
      anatomy: 'Structures outlined by the radiotherapy team: tumour, airway, heart, oesophagus, spine and lymph nodes.',
    },
  },
  'brain-tractography': {
    plain:
      'A map of the brain’s wiring. Diffusion MRI tracks how water moves; inside nerve fibres water can only travel along the fibre, so a computer can follow those paths and draw them as lines. This map averages 1,065 healthy young adults. Colour shows direction: red runs left to right, green front to back, blue top to bottom.',
    lookFor: [
      'Spin the brain and find the red bridge across the middle: the corpus callosum, which joins the two halves.',
      'Untick fibre groups in Details › Controls to isolate one family of pathways.',
      'Turn on the T1 template and use MPR to see where the fibres run.',
    ],
    layers: {
      t1: 'An average brain MRI, used as a background map.',
      association: 'Connect regions within the same half of the brain, such as the language areas.',
      projection: 'Run between the brain’s surface and the brainstem and spinal cord, carrying movement and sensation.',
      commissural: 'Cross between the two halves of the brain.',
      cerebellum: 'Connect the cerebellum, which coordinates movement and balance.',
      'cranial-nerve': 'Nerves that leave the brain directly, for example to the eyes and face.',
    },
  },
  'fetal-face-atlas': {
    plain:
      'A baby’s face before birth, rebuilt in 3D from MRI. Fetal MRI is taken through the mother’s abdomen and uses no X-rays. The baby moves during the scan, so software corrects each image for the movement and stacks them into a 3D volume. This atlas averages 12 healthy fetuses, so it shows a typical face rather than one baby’s. The skin-tone colouring imitates the 3D ultrasound pictures parents are often given.',
    lookFor: [
      'Press Spin to turn the head.',
      'Turn on Clip and choose Side to cut down the middle: you will see the brain, the eye sockets, the tongue and the airway.',
      'Turn on Facial landmarks to see the 45 points specialists measure between to check how the face and skull are developing, such as the size of the jaw.',
    ],
    layers: {
      t2: 'The MRI of the head. In 3D, Skin tone shows the surface; Solid shows crisp cut faces.',
      landmarks: 'Points on the skull and face, such as the tip of the nose, the chin and the ears.',
    },
  },
  'fetal-body-atlas': {
    plain:
      'The chest and belly of a baby before birth, averaged from MRI of 106 healthy pregnancies: one 3D volume for each week from 22 to 38. Each organ has its own colour. Before birth the lungs are filled with fluid rather than air, so on this kind of MRI they look bright; they grow about seven-fold over these weeks, getting ready for the first breath.',
    lookFor: [
      'Press Play: the organs grow week by week.',
      'Move the clip slider to cut through the body at different depths.',
      'Untick T2 MRI to see the coloured organs on their own, then press Spin to look around them.',
    ],
    layers: {
      t2: 'The MRI of the trunk. Fluid is bright, so the fluid-filled lungs, stomach and bladder stand out.',
      organs: 'Lungs pink, liver brown, stomach blue, kidneys purple, bladder yellow; also the thymus (an immune gland behind the breastbone), spleen and gallbladder.',
    },
  },
  'fetal-brain-atlas': {
    plain:
      'An average of MRI scans from 187 healthy pregnancies: one 3D brain for each week from 21 to 36 weeks. On this kind of MRI (T2-weighted) fluid is bright white, so the fluid around the brain and in its central cavities (ventricles) stands out. Early on the brain’s surface is almost smooth; over these weeks it folds into ridges (gyri) and grooves (sulci), a key sign of healthy development.',
    lookFor: [
      'Press Play and watch the brain grow more than six-fold and fold.',
      'Turn on Tissue labels to colour the cortex, white matter, ventricles and deeper structures.',
      'Move the clip slider to cut through the brain at different depths.',
    ],
    layers: {
      t2: 'The MRI. Fluid is white, brain tissue grey.',
      tissue: 'Each tissue type in its own colour.',
    },
  },
};

export function studyNote(id: string, description: string): ImageNote {
  return STUDY_NOTES[id] ?? { plain: description, lookFor: [] };
}

export const PATHOLOGY_BASICS = [
  'A whole-slide image is a glass microscope slide scanned at very high resolution: often billions of pixels, so large that it is cut into small tiles and only the tiles you look at are downloaded.',
  'Almost every slide here is stained with haematoxylin and eosin (H&E). Haematoxylin turns cell nuclei purple or blue; eosin turns the rest of the cell and the tissue between cells pink. White spaces are usually fat, which dissolves when the tissue is processed, or natural gaps such as air spaces and the inside of glands.',
  'Pathologists recognise cancer by its pattern. Cancer cells tend to be crowded, with large, dark, irregular nuclei, and they lose the orderly arrangement of the tissue they came from, invading places they do not belong.',
  'Magnification works like the lenses on a microscope: about 1.25× shows the whole piece of tissue, 5× to 10× shows how cells are arranged, and 20× to 40× shows individual cells and their nuclei.',
];

export const PATHOLOGY_CONTROLS: Term[] = [
  { term: 'Slide list', text: 'Every slide in the Lakehouse. The small text gives the organ, the scanner’s lens power (20× or 40×) and the image size in gigapixels (billions of pixels). Type to search by organ or diagnosis. The ‹ button folds the list into a slim strip to give the image more room; click the strip to bring it back.' },
  { term: '1.25× to 40×', text: 'Jump to what a microscope lens of that power would show. The live magnification is shown at the bottom left.' },
  { term: 'Tour', text: 'Flies automatically through the most cell-dense areas of the slide, found by the image pipeline. Dense areas are usually tumour.' },
  { term: 'Fit', text: 'Shows the whole slide again.' },
  { term: 'Copy link', text: 'Copies a link to exactly this slide, position and zoom, to send to someone else.' },
  { term: 'Full screen', text: 'Fills the window with the viewer and its controls, and the whole screen where the browser allows it. Press Esc or Exit full screen to leave.' },
  { term: 'Details panel', text: 'The panel on the right has two tabs. About tells the story of the slide in plain words, with specimen facts and where the files are stored. Controls holds the marker switches (fluorescence slides) and shared pins. The › button folds it into a strip; In plain words under the title opens it on About.' },
  { term: 'Markers', text: 'Fluorescence slides only. Each chip is one protein in its own colour; click it to switch it on or off. All shows every marker; reset returns to the starting set.' },
  { term: 'Minimap', text: 'The small picture in the corner shows the whole slide; the orange box is the part you are looking at. Click it to jump.' },
  { term: 'Scale bar', text: 'A real-world ruler for the current zoom. 100 µm is 0.1 mm, about the width of a human hair.' },
  { term: 'Tiles loaded', text: 'How many image tiles have been streamed from OneLake so far, and how quickly the first one arrived.' },
  { term: 'Pins', text: 'Name the current view and save it. Pins are stored in the app’s database and every signed-in user sees them; only the person who made a pin can remove it.' },
  { term: 'Specimen facts', text: 'Project and case are research identifiers. Resolution is how many micrometres one pixel covers. Pyramid levels are the same image saved at successively halved sizes, so zoomed-out views load quickly.' },
];

export const VIEW_TERMS: Term[] = [
  { term: '3D', text: 'A three-dimensional picture built from the whole stack of slices (volume rendering). Drag to rotate, scroll to zoom.' },
  { term: 'MIP', text: 'Maximum intensity projection. For every line of sight through the body only the brightest point is kept, so bright things such as PET hotspots or contrast-filled arteries stand out, as on an X-ray. It rotates; drag sideways to turn it.' },
  { term: 'MPR', text: 'Multi-planar reconstruction. Three flat slices at right angles (axial, coronal and sagittal) plus the 3D view, all linked: click a point in one and the others jump to it.' },
  { term: 'Axial', text: 'Horizontal slices, as if the body were a loaf sliced from head to toe. By convention you look up from the feet, so the patient’s right is on the left of the screen.' },
  { term: 'Coronal', text: 'Vertical slices from front to back, as if facing the person.' },
  { term: 'Sagittal', text: 'Vertical slices from side to side: a profile view.' },
];

export const VOLUME_CONTROLS: Term[] = [
  { term: 'Colour (3D)', text: 'Chooses which tissues appear in 3D and in what colour, based on density for CT or signal for MRI. Radiologists call this a transfer function. The options are listed below.' },
  { term: 'Window (2D)', text: 'CT measures density on a scale from air (−1000) to dense bone (above +1000): far more shades than the eye can tell apart. A window picks the part of that range to spread from black to white.' },
  { term: 'Clip', text: 'Cuts away part of the volume so you can see inside. Front, Side and Top set the direction of the cut; the slider moves it through the body.' },
  { term: 'Spin', text: 'Rotates the 3D view automatically.' },
  { term: 'Reset', text: 'Returns to the starting viewpoint and zoom.' },
  { term: 'Save image', text: 'Downloads a picture of the current view.' },
  { term: 'Full screen', text: 'Fills the window with the viewer and its controls, and the whole screen where the browser allows it. Press Esc or Exit full screen to leave.' },
  { term: 'Study list', text: 'Every study on the tab, grouped by body area. The ‹ button folds the list into a slim strip; click the strip to bring it back.' },
  { term: 'Details panel', text: 'The panel on the right has two tabs. About explains the study in plain words, with its facts, source, licence and storage. Controls holds the layers and a summary of the current view. The › button folds it into a strip; In plain words under the title opens it on About.' },
  { term: 'Play and timeline', text: 'For studies that change over time: a heartbeat, a breath or weeks of pregnancy. Play runs through them; drag the slider or click a number to pick one moment.' },
  { term: 'Layers', text: 'In Details › Controls. A study can stack several images, such as a CT with PET or coloured outlines on top. The tick box shows or hides each one, the slider makes it more or less see-through, and the legend names the colours.' },
  { term: 'PET colour map', text: 'Hot, Inferno, Plasma, GE colour and Turbo are different colour scales for the same numbers: dark for low uptake, bright for high.' },
  { term: 'Status bar', text: 'Voxels are 3D pixels; the size in millimetres is how much of the body each voxel covers. The megabytes show how much was streamed from OneLake and how long it took. In 2D views, the readout shows the position under the cursor and its value.' },
];

/** Colour presets in the 3D view, keyed by preset id. */
export const RENDER_PRESET_NOTES: Record<string, string> = {
  bone: 'Shows only dense tissue: the skeleton.',
  lungs: 'Shows air-filled lung tissue as translucent pink glass, so structures inside stay visible.',
  contrast: 'Shows contrast-filled blood vessels together with bone.',
  artery: 'Emphasises arteries filled with contrast dye.',
  muscle: 'Shows soft tissue and muscle.',
  skin: 'Shows the surface of the body.',
  gray: 'Translucent greyscale: shows depth, but cut surfaces look soft.',
  solid: 'Opaque greyscale: gives crisp cut surfaces when clipping.',
  sepia: 'Warm skin tones with lighting, like the 3D ultrasound pictures parents are shown.',
};

/** Greyscale windows in 2D views, keyed by preset id. */
export const WINDOW_NOTES: Record<string, string> = {
  soft: 'Soft tissue: tuned for organs and muscle.',
  lung: 'Lung: tuned for the fine detail of air-filled lung.',
  bonew: 'Bone: tuned for the inside of bones.',
  gray: 'Greyscale: the full range of the MRI signal.',
};

export const RENDER_PRESET_LABELS: Record<string, string> = {
  bone: 'Bone',
  lungs: 'Lungs (glass)',
  contrast: 'Vessels and bone',
  artery: 'Arteries',
  muscle: 'Muscle',
  skin: 'Skin',
  gray: 'Translucent (MRI)',
  solid: 'Solid (MRI)',
  sepia: 'Skin tone (MRI)',
};

export const MIP_COLOUR_NOTES: Term[] = [
  { term: 'Inverted grey', text: 'Dark means high: how nuclear medicine doctors usually read PET.' },
  { term: 'Grey', text: 'Bright means high, like an X-ray.' },
  { term: 'Hot and Inferno', text: 'Colour scales from dark red to yellow-white for the same values.' },
];

export const LICENCE_TERMS: Term[] = [
  { term: 'No data in the repository', text: 'The code repository contains no images. Each dataset is downloaded from its original publisher by the setup pipeline and stored in your own Fabric Lakehouse.' },
  { term: 'CC0 and public domain', text: 'Free to use for any purpose, including commercial use, without conditions.' },
  { term: 'CC BY', text: 'Free for any purpose, including commercial use, as long as the source is credited. The app credits every source.' },
  { term: 'CC BY-SA', text: 'As CC BY, and adapted versions must be shared under the same licence. Commercial use is allowed.' },
  { term: 'Not legal advice', text: 'This is a summary. Each study’s About tab and the Overview list the exact licence and a link to the source.' },
];

export const GLOSSARY: Term[] = [
  { term: 'Adenocarcinoma', text: 'Cancer that starts in gland-forming cells, such as those lining the bowel, lung, breast or prostate.' },
  { term: 'Carcinoma', text: 'Cancer that starts in the cells lining organs and surfaces (epithelium). Most common cancers are carcinomas.' },
  { term: 'H&E', text: 'Haematoxylin and eosin, the standard two-dye stain: nuclei purple, everything else pink.' },
  { term: 'Nucleus', text: 'The control centre of a cell, which holds its DNA. Cancer nuclei are often larger, darker and irregular.' },
  { term: 'Cytoplasm', text: 'The body of the cell around the nucleus.' },
  { term: 'Stroma', text: 'The supporting tissue between cells and glands: fibres, blood vessels and immune cells.' },
  { term: 'Necrosis', text: 'Dead tissue, often seen in fast-growing tumours that outgrow their blood supply.' },
  { term: 'Grade', text: 'How abnormal cancer cells look under the microscope. Higher grades tend to grow faster.' },
  { term: 'Immunofluorescence', text: 'Staining with antibodies that carry glowing dyes, so individual proteins can be seen.' },
  { term: 'µm (micrometre)', text: 'One thousandth of a millimetre. A typical cell is 10 to 20 µm across.' },
  { term: 'Gigapixel', text: 'A billion pixels, roughly 80 photos from a 12-megapixel phone camera.' },
  { term: 'CT', text: 'Computed tomography: X-rays taken from many angles and combined into slices. Bone is bright, air is black.' },
  { term: 'Contrast and angiography', text: 'A dye injected into the blood to make vessels show up brightly. Imaging vessels this way is angiography.' },
  { term: 'Hounsfield unit (HU)', text: 'CT’s density scale: water is 0, air −1000 and dense bone above +1000.' },
  { term: 'MRI', text: 'Magnetic resonance imaging: uses a strong magnet and radio waves, no X-rays. Excellent for soft tissue such as the brain and heart.' },
  { term: 'T1 and T2', text: 'Two common MRI settings. On T2, fluid is bright; on T1, fat is bright and fluid dark.' },
  { term: 'PET', text: 'Positron emission tomography: images a small dose of radioactive tracer to show what the body is doing, not just its shape.' },
  { term: 'FDG', text: 'A radioactive form of glucose (sugar), the most common PET tracer. Busy cells, including many cancers, take up more.' },
  { term: 'SUV', text: 'Standardised uptake value: how much tracer a spot holds, adjusted for dose and body weight. Higher means more active.' },
  { term: 'Fusion', text: 'Overlaying two scans, such as PET on CT, so activity can be placed on the anatomy.' },
  { term: 'Segmentation, labels', text: 'Outlines that mark which voxels belong to which organ or tumour, each shown in its own colour.' },
  { term: 'Voxel', text: 'A 3D pixel: the smallest block of a scan.' },
  { term: 'Volume rendering', text: 'Drawing a 3D picture directly from the stack of slices, choosing how see-through each tissue is.' },
  { term: '4D', text: 'A 3D scan repeated over time, such as a heartbeat, a breath or weeks of growth.' },
  { term: 'Atlas', text: 'An average of many people’s scans, used as a reference for what is typical.' },
  { term: 'Embryo and fetus', text: 'Until about eight weeks after conception (ten weeks of pregnancy) the developing baby is called an embryo; from then until birth, a fetus.' },
  { term: 'Ultrasound', text: 'Imaging with high-frequency sound waves that bounce back from tissue. Safe, quick and used in every pregnancy, but less sharp than MRI.' },
  { term: 'Gestational age', text: 'How far a pregnancy has progressed, counted in weeks from the first day of the last menstrual period. A pregnancy counts as term from 37 weeks.' },
  { term: 'Gyri and sulci', text: 'The ridges and grooves of the brain’s folded surface.' },
  { term: 'Diffusion MRI, tractography', text: 'MRI that measures how water moves, and the technique of tracing nerve fibre pathways from it.' },
  { term: 'Radiotherapy planning', text: 'Working out where and how to aim radiation so it hits the tumour and spares healthy tissue.' },
  { term: 'DICOM, NIfTI, SVS', text: 'File formats: DICOM is the hospital standard for scans, NIfTI a research format for 3D volumes, and SVS a scanner format for slides.' },
];

/** Short hover text for toolbar controls. */
export const TIPS = {
  magnification: (m: number) => `Show what a ${m}× microscope lens would show`,
  tour: 'Fly automatically through the most cell-dense areas',
  fit: 'Show the whole slide',
  copyLink: 'Copy a link to this exact slide, position and zoom',
  fullScreen: 'Fill the screen with the viewer and its controls',
  exitFullScreen: 'Back to the normal layout (or press Esc)',
  markersAll: 'Show every marker',
  markersReset: 'Back to the starting set of markers',
  clip: 'Cut away part of the volume to see inside',
  clipFace: 'Direction of the cut',
  clipDepth: 'Move the cut through the body',
  spin: 'Rotate automatically',
  reset: 'Back to the starting view',
  saveImage: 'Download a picture of this view',
  play: 'Play through the timeline',
  views: Object.fromEntries(VIEW_TERMS.map((t) => [t.term, t.text])) as Record<string, string>,
};
