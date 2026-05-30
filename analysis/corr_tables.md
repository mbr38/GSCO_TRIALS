# Correlation tables & divergence cases

### Part A — activity (vs ODIAC point, log10)

| regime | CH4–ODIAC Pearson | CH4–ODIAC Spearman | n | VIIRS–ODIAC Pearson | VIIRS–ODIAC Spearman | n |
|---|---|---|---|---|---|---|
| Urban | 0.44 | 0.2 | 4 | 0.66 | 0.7 | 5 |
| Oil/Gas | -0.72 | -0.5 | 5 | 0.42 | 0.5 | 5 |
| Coal | -0.15 | -0.1 | 5 | 0.03 | 0.7 | 5 |
| Landfill | -0.63 | -0.6 | 4 | -0.12 | -0.1 | 5 |
| Rural | None | None | 5 | None | None | 5 |
| ALL | -0.0 | -0.01 | 23 | 0.38 | 0.7 | 25 |

### Part B — concentration (vs XCO2 delta)

| regime | VIIRS–XCO2 Pearson | VIIRS–XCO2 Spearman | n | CH4–XCO2 Pearson | CH4–XCO2 Spearman | n |
|---|---|---|---|---|---|---|
| Urban | -0.18 | -0.3 | 5 | -0.1 | 0.2 | 4 |
| Oil/Gas | -0.57 | -0.1 | 5 | -0.4 | -0.2 | 5 |
| Coal | 0.74 | 1.0 | 5 | 0.71 | 0.8 | 5 |
| Landfill | 0.32 | 0.2 | 5 | 0.1 | -0.4 | 4 |
| Rural | 0.29 | 0.4 | 4 | -0.95 | -0.8 | 4 |
| ALL | -0.17 | -0.0 | 24 | -0.06 | -0.12 | 22 |

### Divergence cases (CH4 anomaly z firing, threshold z>1.5)

- **Urban** — fired: (none); did not fire: ['London', 'Mexico City', 'Mumbai', 'Seoul']
- **Oil/Gas** — fired: (none); did not fire: ['Permian Basin', 'Bakken', 'Hassi Messaoud', 'Tengiz', 'Comodoro']
- **Coal** — fired: ['Mpumalanga']; did not fire: ['Belchatow', 'Tuoketuo', 'Vindhyachal', 'Kendal']
- **Landfill** — fired: (none); did not fire: ['Sudokwon', 'Bordo Poniente', 'Apex NV', 'Puente Hills']
- **Rural** — fired: (none); did not fire: ['Patagonia', 'C. Sahara', 'C. Australia', 'Greenland Coast', 'Siberian Taiga']

### XCO2 coverage (Part B)

- **Urban** — usable XCO2 delta: ['London', 'Mexico City', 'Mumbai', 'Lagos', 'Seoul']
- **Oil/Gas** — usable XCO2 delta: ['Permian Basin', 'Bakken', 'Hassi Messaoud', 'Tengiz', 'Comodoro']
- **Coal** — usable XCO2 delta: ['Belchatow', 'Tuoketuo', 'Vindhyachal', 'Mpumalanga', 'Kendal']
- **Landfill** — usable XCO2 delta: ['Sudokwon', 'Bordo Poniente', 'Apex NV', 'Puente Hills', 'Olusosun']
- **Rural** — usable XCO2 delta: ['Patagonia', 'C. Sahara', 'C. Australia', 'Greenland Coast']
