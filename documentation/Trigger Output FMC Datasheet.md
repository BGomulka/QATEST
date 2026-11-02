# Trigger Output FMC Datasheet Draft
## Board Overview
The Trigger Output FMC board is a standard VITA 57.1 FMC HPC form factor board. [^1]
The board provides 2 independent Skyworks Solutions Si5394 Jitter Cleaners that recieve clocks though the FMC's M2C clock lines. Each Si5394 then outputs 4 copies of the recovered clock; 1 to the FMC's MGT clock, 1 to a FMC's C2M clock and 2 to SMA test ports on the board. The board has sixteen 50 ohm drive TTL-compatible digital outputs designed for low jitter. The outputs are provided as MMCX coaxial connectors.

[^1]:  The board can be used in a VITA 57.1 FMC LPC application but is limited to a single clock/timing domain. 
## Key components

- Skyworks Solutions Si5394 Jitter Attenuator
	- Ultra-low phase jitter of 100 fs RMS
	- Input frequency range - 8 kHz to 750 MHz
	- Output frequency range - 100 Hz to 1028 MHz
- Texas Instruments TLV3601 High-Speed Comparator
	- 4 ps RMS Jitter over 10Hz – 50MHz
- Texas Instruments SN74LVC2G126 Dual Bus Buffer Gate With 3-State Outputs
	- Can drive 50 ohm back-terminated TTL loads [^2]

[^2]:  See PubMed Central article PMC8342968 [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC8342968/)
## Board Architecture
![[BlockDiagram.png|501]]

## Technical Specifications
### Nominal Performance
Channel-to-Channel Output Jitter: < 20pSec RMS
Event Clock Frequency: 50MHz - 250MHz;
16x SMA connectors; 50Ω drive capable; LVTTL

### Absolute Performance
Ambient Temperature: 0°C - 40°C
Digital Output drive current: 100mA max
Event Clock Rate: 50MHz - 250MHz
Event Bitrate: 1Gbps - 5Gbps
Number of user-configurable events: 255

## To include at a later date
- Nominal Testing data
- ? Theory of Operation for Output trigger
- ? Specifications for on-board power switcher and LDOs