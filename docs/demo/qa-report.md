# board-sync QA report

Timing source: whisper word_timestamps (words.json)
Boards: 7, clean 7, with findings 0.

## Verdicts

- 01 01-bedside-alert.html: Clean
- 02 02-silos-patient.html: Clean
- 03 03-alert-stopwatch.html: Clean
- 04 04-multimodal-oncology.html: Clean
- 05 05-wardflow-cardiology.html: Clean
- 06 06-clinician-signoff.html: Clean
- 07 07-endcard.html: Findings: fonts under 28px: [26]

## Detailed Board Findings

### 01 · 01-bedside-alert.html
Window: 0.00s – 12.66s (duration 12.66s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 02 · 02-silos-patient.html
Window: 12.66s – 23.34s (duration 10.68s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 03 · 03-alert-stopwatch.html
Window: 23.34s – 30.78s (duration 7.44s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 04 · 04-multimodal-oncology.html
Window: 30.78s – 39.80s (duration 9.02s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 05 · 05-wardflow-cardiology.html
Window: 39.80s – 51.42s (duration 11.62s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 06 · 06-clinician-signoff.html
Window: 51.42s – 58.88s (duration 7.46s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 07 · 07-endcard.html
Window: 58.88s – 63.48s (duration 4.60s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

