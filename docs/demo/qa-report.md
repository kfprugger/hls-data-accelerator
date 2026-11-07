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
Window: 0.00s – 9.72s (duration 9.72s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 02 · 02-silos-patient.html
Window: 9.72s – 20.44s (duration 10.72s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 03 · 03-alert-stopwatch.html
Window: 20.44s – 27.42s (duration 6.98s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 04 · 04-multimodal-oncology.html
Window: 27.42s – 36.52s (duration 9.10s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 05 · 05-wardflow-cardiology.html
Window: 36.52s – 47.94s (duration 11.42s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 06 · 06-clinician-signoff.html
Window: 47.94s – 56.38s (duration 8.44s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

### 07 · 07-endcard.html
Window: 56.38s – 61.60s (duration 5.22s)
Clean. All text elements >= 28 px. Word landing verified against whisper word timestamps.

