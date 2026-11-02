# Osprey EVR FMC Design Goals

## High level specifications
### Jitter Cleaner
- 2+ LVDS outputs
- Controlled by 2.5V logic from the FPGA (to avoid level shifting)
- Frequencies of interest are 100MHz-250MHz

### Digital I/O
- 16+ outputs with a couple of inputs
- Some/all outputs can drive 50ohm
- Better than 20ps of jitter on clocked digital outputs

# Osprey EVR FMC Part Selection

## Clock Jitter Cleaner Selection
#### We have settled on using the Skyworks Si5394, but the below parts were considered:

### Skyworks Parts
#### Si5315/16/17/19 - 300pS jitter
- These parts are quite simple and similar
- 3rd Gen DSPLL
- They have a PPL Bypass mode which could be nice for testing.
- CON - these parts seem optimized to operate at fixed tables of frequencies, but will work at 125MHz
Out of this bunch the Si5317A/B seems like it best matches our needs. has 125MHz +/-5MHz options.
These are available form Mouser and Digikey for $15-$20

#### Si5342-45 - 90pS jitter
- 4th Gen DSPLL
- Recommended DSPLLs for Line Card by Skyworks: [link](https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/application-notes/an1077-selecting-clocks-for-timing-synchronization.pdf)
 - Con - may need level shifting for SPI bus
Out of this bunch the Si5342B seems like it best matches our needs.
These are available form Mouser and Digikey for $26
#### Si5392-95 - 75pS jitter
- This part was used by Paul B. in another similar role but is a clock gen
- 4th Gen DSPLL
- A slightly updated Si534* part with similar combabilities (Drop-in compatible) but options for integrated XTAL
Either Si5392 or Si5394 with a A or B speed grade
These are available form Mouser and Digikey for $35-40
### TI Parts
#### LMK04100 family ~ 200pS jitter [datasheet](https://www.ti.com/lit/ds/symlink/lmk04111.pdf?ts=1769610888824)
- Simple, cheap ($<10), not readily in stock
- require external loop filter (a bit harder to design board for)
- LMK04131
#### LMK04000 family ~ 150pS jitter [datasheet](https://www.ti.com/lit/ds/symlink/lmk04033.pdf?ts=1769572954419)
- require external loop filter (a bit harder to design board for)
- LMK04033 seems like an ok part
### Analog Parts
 - Parts with dedicated jitter cleaning available are quite complicated, and try to integrate more than just jitter cleaning.

## Directly Clocked outputs
There was an idea to clock the Digital I/O directly from the jitter cleaner rather than feeding it back to the FPGA.

- Thinking through this option controlling phase of the clock (from IC) and data (from FPGA) may be an issue.
		- Not sure if this an issue as it could be calibrated out in a consistent way
		- It may be harder to sync outputs from 2 nodes


## Skyworks SI5394 Info and Design
- [datasheet](https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/data-sheets/si5395-94-92-a-datasheet.pdf)
- [Si5395/94/92 Any-Frequency, Any-Output, Jitter-Attenuators/Clock Multipliers Family Reference Manual](https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/reference-manuals/si5395-94-92-family.pdf)
- [Recommended Crystal, XO, TCXO, and OCXO Reference Manual for High-Performance Jitter Attenuators and Clock Generators](https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/reference-manuals/si534x-8x-9x-recommended-crystals-rm.pdf)

### Choosing a XTAL
- Looked at high initial tolerance (10ppm or below) parts at 48MHZ from the chart
- Selected Kyocera CX3225SB48000D0F PJC1 based on availability

### Power Supplies for SI5394
- Section 14 in reference manual mentions a few things
	- It is recommended to use a 1 μF 0402 ceramic capacitor on each VDD for optimal performance. It is also suggested to include an optional, single 0603 (resistor/ferrite) bead in series with each supply to enable additional filtering if needed

	- Four classes of supply voltages exist on the Si5395/94/92:
		- VDD = 1.8 V (Core digital supply)
		- VDDA = 3.3 V (Analog supply)
		- VDDOx = 1.8/2.5/3.3 V ± 5% (Clock output supply)
		- VDDS = 1.8/3.3 V ± 5% (Digital I/O supply)
	- I will level shifter for VDDS based IO to FPGA?

- M2C avoid because it goes through mux
- check for CM requirements of output of chip to input of fpga line (both GBT and CC)
	- .3 - 1.5V CM

- A clean 3.3V is preferred (for the analog core) over the 3.3V provided from Marble
	- 1st approach is 12V -> ~5.4V via switcher ->(LDO) 3.3V
		- Switcher was choosen as a TPS563200 for its simplicity and aviablilty while meeting the required load requirements
		- 3.3V LDO was choosen as a TLV75733 for its simplicity and aviablilty while meeting the required load requirement
			- The expected draw on this part is 130mA, 280mW dissipation which results in an expected 28C above ambient operation

# Digital Outputs
## Goals 
 - Drive 50 ohm cable and 50 ohm receiver termination
 - TTL compatible (>2V, target at least 2.4V), 
 - low jitter
 - no ringing into high-z via 50 ohm cable
 - short circuit tolerant 

## FPGA Output jitter
Currently using FPGA GPIO / LVCMOS
 - Kintex7 switching datasheet [link](https://docs.amd.com/v/u/en-US/ds182_Kintex_7_Data_Sheet)
	 - Table 20?
- Use weak-drive LVCMOS outputs to appox 50ohm drive pg. 46 [UG483](https://docs.amd.com/v/u/en-US/ug483_7Series_PCB)
- potential issues/sources of jitter with SE
	- FPGA supply noise coupling into GPIO threshold
	- Receiver threshold noise
	- Ground bounce on single-ended outputs (*more a problem with clocks than our pulses)
- Using LVDS/diff outputs should improve jitter these at the cost of complexity
## Topology Options with Approximate Jitter & Rise Time:

Jitter and rise-time are estimates (edge-slope * noise; slew/tPD) except F (ADCMP580 datasheet-spec'd) 

- A. FPGA LVCMOS => Digital Bus TXCVR => 50 ohm TTL
	- ~10-15 ps jitter, ~2-3 ns rise time
- B. FPGA LVDS => LVDS TXCVR => Digital Bus TXCVR => 50 ohm TTL
		- ~8-12 ps jitter, ~2-3 ns rise time
- C. FPGA LVDS => LVDS TXCVR => OpAmp => 50 ohm TTL
	- ~7-11 ps jitter, ~1-1.5 ns rise time
- D. FPGA LVDS => Comparator => Digital Bus TXCVR => 50 ohm TTL
	- ~4-7 ps jitter, ~2-3 ns rise time
- E. FPGA LVDS => Comparator => OpAmp => 50 ohm TTL
	- ~3-5 ps jitter, ~1-1.5 ns rise time
- F. FPGA LVDS => Clock Buffer => 50 ohm TTL
	- ~1-2 ps jitter, ~150 ps rise time 
	- (wildcard, must verify experimentally)
- G. FPGA LVDS => Comparator(CML) => Differential CML
	- ~1-2 ps jitter, ~40 ps rise time

Other Thoughts:
- H. FPGA LVDS => Connector/Cable/Front Panel Board (HDMI/ mini-SAS/ FireFly?) => Driver B-G? => 50 ohm TTL, or CML for G (flexible front panel board)
- I. FPGA LVDS => Delay Tuning (IC ex:NB6L295) => B-G (tweak channel delays)


Part Options:

**Digital Bus TXCVR:**
[LVCH8T245](https://www.ti.com/product/SN74LVCH8T245) (4 gates in parallel)
SN74LVC3G34: 3.2ns tpd, non-inverting
SN74LVC3G17: 4.1ns tpd, non-inverting, schmitt-trigger
SN74LVC3G04: 3.2ns tpd, inverting 
SN74LVC3G14: 5.0ns tpd, inverting, schmitt-trigger
SN74LVC**2G**34-EP: 5.2ns tpd, non-inverting
SN74LVC**2G**04-EP: 4.0ns tpd, inverting
SN74LVC**2GU**04: 2.9ns tpd, inverting
SN74LVC**2G**126: 3.2ns tpd, non-inverting; output enables
SN74LVC**2G**241: 4.0ns tpd, non-inverting; complementary output enables

**LVDS TXCVR:**
$1.60 [DS90LV048](https://www.ti.com/product/DS90LV028A0) 

**OpAmp:**
$3.80 AD8009
ADA4311
LT6200
BUF602
OPA695

**Comparator:**
 $3.00 [TLV3601](https://www.ti.com/product/TLV3601)
 $3.60 [LTC6752](https://www.analog.com/en/products/ltc6752.html) 
LTC6957-3 

**Clock Buffer:**
$2.30 [SiT92113](https://www.sitime.com/products/clock-buffers/high-performance-buffers/sit92113)
IDT8L3010I Clock buffer (10 parallel outputs)
[LMK00105](https://www.ti.com/product/LMK00105) (Won’t drive 50ohm)

**Comparator - CML:**
ADCMP580 
LMH7220

**LVDS Repeater (option H):**
DS90LV004
DS25BR440
DS15BR401
DS15BR400
DS10BR254
SCAN90004

**Delay Tuning (option I):**
$19.33 NB6L295


### ** Going with Option D - Comparator to fast CMOS buffer:**

Si5394 cleaner jitter: 0.09 ps (datasheet)
Kintex-7 LVDS jitter: ~4-6 ps (estimate, might get closer with Vivado clocking report)
TLV3601 jitter: ~4 ps (likely 2-3 ps w/LVDS drive, datasheet 4 ps @100 mVpp/100MHz)
SN74LVC2G126 jitter: ~1-2 ps (estimate, supply-noise dominated)
Quadrature total jitter: ~6 ps RMS (best estimate, dominated by FPGA then comparator)

**TLV3601 at 5V:**
Using 5V makes the slope steeper for better jitter performance.
Bypassing is important, use datasheet 100pF/10nF/1uF at power pin, maybe preceded by ferrite (PSRR is 80 dB at DC, will be less at high frequency).

LVDS with 100 ohm termination at comparator pins IN+/- (LVDS CM at 1.2V).
Keep differential traces matched-length and away from outputs.

**SN74LVC2G126 at 5V (w/OE):**
Ron = ~12 ohm typical (8 to 22 ohm range, 22/(~1.3 process * ~1.4 temperature)=12)
Z_source_ideal = (Ron + R_series) / 2 = 50 ohm
R_series = 2 × 50 ohm − 12 ohm = 88 ohm, 88.7 or 86.6 ohm (E96)
Z_source = (12 + 88.7) / 2 = 50.4 ohm
Γ_source_typical = (Z_source − Z₀)/(Z_source + Z₀) = (50.4 − 50)/(50.4 + 50) = +0.003
Γ_source_range = -0.017 to +0.051 (-2% to +5% reflection, 48.4 to 55.4.5 impedance)
I_gate_terminated = (5 V / (50.4 + 50 ohm)) / 2 = 24.9 mA per gate into 50 ohm
R_power_normal = 88.7 ohm * (24.9 mA)^2 = 0.055 W (⅛ W ok)
R_power_short = 88.7 ohm * (49.7 mA)^2 = 0.22 W (¼ W needed)
50 ohm Term: 5V * 50 ohm / (50.4 + 50 ohm) = 2.49V TTL/3.3V-CMOS compatible

High-Z: Clean edge to 5 V (no ringing, 50 ohm series termination absorbs reflection)

Short-Circuit: 5 V / 50.4 ohm = 99 mA total (100 mA abs max power pin so transient survivable) and 99 mA / 2 = 50 mA per gate (50 mA abs max per gate so transient survivable)

Notes: Power fluctuations modulate the delay (fig 6-2 in datasheet, ~350 ps/V) which drives jitter so clean power with a ferrite, bulk bypass, and local bypass (0.1uF/0.01uF at power pin) is important.

**SN74LVC3G34 at 5V:**

Ron = ~12 ohm typical (8 to 22 ohm range, 22/(~1.3 process * ~1.4 temperature)=12)
Z_source_ideal = (Ron + R_series) / 3 = 50 ohm
R_series = 3 × 50 ohm − 12 ohm = 138 ohm, 137 or 140 ohm (E96)
Z_source = (12 + 137) / 3 = 49.7 ohm
Γ_source_typical = (Z_source − Z₀)/(Z_source + Z₀) = (49.7 − 50)/(49.7 + 50) = -0.003
Γ_source_range = -0.02 to 0.03 (-2% to +3% reflection for 48 to 53.5 impedance range)
I_gate_terminated = (5 V / (49.7 + 50 ohm)) / 3 = 16.7 mA per gate into 50 ohm
R_power_normal = 137 ohm * (16.7 mA)^2 = 0.04 W (⅛ W ok)
R_power_short = 137 ohm * (33.5 mA)^2 = 0.15 W (¼ W needed)

50 ohm Termination: 5V * 50 ohm / (49.7 + 50 ohm) = 2.5V TTL compatible (< 3.3V)

High-Z: Clean edge to 5 V (no ringing, 50 ohm series termination absorbs reflection)

Short-Circuit: 5 V / 50 ohm = 100 mA total (100 mA power pin abs max so transient survivable) and 100 mA / 3 = 33 mA per gate (50 mA abs max per gate so good)

Notes: Power fluctuations modulate the delay (fig 3 in datasheet, ~350 ps/V) which drives jitter so clean power with a ferrite, bulk bypass, and local bypass (0.1uF/0.01uF at power pin) is important.

**Osprey TTL-IO:** ~10-15 ps estimated RMS jitter (edge slope * noise), ~2-3 ns estimated rise time into 50 ohm (from slew/tPD specs), 3.3V VCC, 3 parallel gates of SN74LVC3G34, 10 ohm series resistors per gate.  Good performance into 50 ohm terminated loads.  Heavily under-matched with Z_source = 7.5 ohms, so rings significantly into high-z receivers (reflection coefficient of -0.74, peak ~5.7V could damage receiver). Not short circuit tolerant (147 mA per gate > 50 mA abs max, 440 mA power pin > 100 mA abs max).  Ringing could be improved by making the parallel resistors higher (closer to 50 ohm match) but need to ensure >2V into 50 ohms.  The best compromise targeting 2.4V into 50 ohm termination:

V_load = Vcc × R_load / (Z_source + R_load)
2.4 V = 3.3 V × 50 ohm / (Z_source + 50 ohm)
Z_source = 3.3 V × 50 ohm / 2.4 V - 50 ohm = 18.75 ohm
Z_source = (Ron + R_series) / 3 = 18.75 ohm
R_series = 3 × 18.75 ohm − 13 ohm = 43.25 ohm; 43 ohm (E12)
Γ_source = (Z_source − Z₀)/(Z_source + Z₀) = (18.75 − 50)/(18.75 + 50) = −0.45
High-Z: Signal will peak ~4.8V then ring down to 3.3V after ~4-5 bounces

Not Short-Circuit Tolerant: 3.3 V / 18.75 ohm = 176 mA total > 100 mA power pin abs max, and 59 mA per gate > 50 mA abs max 

**SN74LVCH8T245 Option:** ~10-15 ps estimated RMS jitter (edge slope * noise), ~2-3 ns estimated rise time into 50 ohm (from slew/tPD specs), converts from 2.5V LVCMOS FPGA pin to 5V (VCCA=2.5V, VCCB=5V), 4 parallel gates of SN74LVCH8T245, each gate has a series resistor to give 50 ohm parallel impedance and limit short-circuit current.  Good 50 ohm performance (2.5V), good high-z performance (5V no ringing, Z_source matched to 50 ohms).  Bus-hold inputs eliminate need for pulldown resistors.  Sustained short-circuit tolerant.

Z_source = (Ron + R_series) / 4 = 50 ohm
R_series = 4 × 50 − 13 = 187 ohm; use 187 (E96)
V_load = Vcc × R_load / (Z_source + R_load) = 5 × 50 / (50 + 50) = 2.5V (>2V TTL)
I_load = 5 / (50 + 50) = 50 mA total, 12.5 mA per gate 
Γ_source = (50 − 50)/(50 + 50) = 0 (matched, no re-reflection) 
High-Z: Signal peaks at 5V and stays there, no ringing due to 50 ohm matched source

Short-Circuit Tolerant: 5 V / 50 ohm = 100 mA total < 200 mA power pins abs max (two 100 mA power pins), and 25 mA per gate < 50 mA abs max

**Renesas IDT8L3010I Clock Buffer:** Clock buffers have wonderful jitter specs but do not specify continuous drive capabilities as they are intended to go into high-z loads on a PCB, not drive 50 ohm cables with 50 ohm terminations.  Maybe paralleling 10 outputs from a Renesas 8L3010I with 173.5 ohm series resistors would work (4.8 mA per output, 18 mA per output into a short).  We would need to stress test on the bench and contact the manufacturer.  (others to consider: 8L30210, NB3F8L3010C, NB3F8L3005C, LMK00105, SiT92113)

## Other app notes on high speed triggers
Oscilloscope trigger with high-speed comparators - [https://www.ti.com/lit/an/snoa984/snoa984.pdf](https://www.ti.com/lit/an/snoa984/snoa984.pdf)

SRS use of laser driver to achieve 1ps cmos trigger pg137 - [https://www.thinksrs.com/downloads/pdfs/manuals/CG635m.pdf](https://www.thinksrs.com/downloads/pdfs/manuals/CG635m.pdf)

PubMed Central article PMC8342968

Horowitz & Hill 12.10 pg 858

### Powering Digital Outputs
Have a separate switched rail to power this
- 1 output needs 99.4mA if shorted; 49.8mA under normal conditions
- Split power into 2x 8Ch sections
- Possibly isolate the comparators too.

Low dropout LDO options
- qualities
	- 1A output
	- fixed (ideal)
	- low dropout of less than 500mV
	- Available on Digikey/Mouser 
-Looked at
- TPS737
- TPS7A91
- TPS7A94
- TPS7A80
- TPS759P
- TLV796
- TLV759
- LP3855

Decided to use LP3855 as other other parts were in hard to probe VSON packages
# Physical Board Stackup

![[Board stackup.png]]
## Layer usage
F - Distributed LVDS Clocks
1 - GND
2 - LVDS trigger outputs
3 - GND
4 - Power Planes
5 - MISC low speed signals & Power Planes
6 - GND
B - MISC low speed signals

### Impedance Controlled Traces
External Layers
	- .21mm Trace/.2 Width for 100 ohm differential pair
		- Gives 106 on Kicad with Zeven 68
		- Gives 94 on Saturn with Zeven 63; Zo 54
	- .26mm for 50ohm single ended signals 
Internal Layers
- .15mm Trace/.25 Width
	- - Gives 94.5 on Saturn with Zeven 54; Zo 50.5

