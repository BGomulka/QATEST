# Trigger Output FMC Quality Assurance Procedure

## Purpose

The purpose of this document is to have a consistent unified way each Board is tested before deployment. This procedure will be updated periodically to improve QA of the boards.

## Equipment Needed

* 2 x MMCX to SMA Cables
* 2 x SMA to BNC adapters
* 1 x SMA to SMA Cable
* Multimeter (Fluke 115 or better)
* Triple output Benchtop Power Supply
* 2 x FMC Power breakout module [link](https://www.iamelectronic.com/shop/produkt/fpga-mezzanine-card-fmc-power-module/)
* Marble Testing Chassis
* PC to run IOC and Phoebus

---

## Procedure

### QA Metadata

* **Board Serial Number:**
* **PCB Revision:**

### Visual Inspection

Check visual for any board defects. If the board has come back from rework look at the reworked areas carefully under magnification for any shorts etc.

Areas to check with extra scrutiny are around the clock jitter cleaner components.

* **Notes / Defects:**

- [ ] **Visual Inspection Complete**

---

### Power Testing

Next the Board will be powered up in various ways to protect other testing hardware.

### Looking for Shorts to GND

Using the multimeter check that all voltage test points have a resistance to board ground greater than 1kΩ.

| Silkscreened Label | Nominal Voltage | Measured Resistance (Ω) | Status |
| ------------------ | --------------- | ----------------------- | ------ |
| VDD3P3V            | +3.3V           |                         | [ ] Pass (>1kΩ) |
| VADJ               | +2.5V           |                         | [ ] Pass (>1kΩ) |
| 12P0V              | +12V            |                         | [ ] Pass (>1kΩ) |
| TP5                | +1.8V           |                         | [ ] Pass (>1kΩ) |
| TP6                | +3.3V           |                         | [ ] Pass (>1kΩ) |
| TP7                | +3.3V           |                         | [ ] Pass (>1kΩ) |
| TP8                | +5.45V          |                         | [ ] Pass (>1kΩ) |
| TP9                | +1.8V           |                         | [ ] Pass (>1kΩ) |

- [ ] **Resistance Check Complete**

---

### 12V/3.3V/2.5V Power Testing

One at a time inject 12V, 3.3V & 2.5V using the voltage test points found on the board. Do this with a 1.5A current limit.

Note variance from nominal current if found.

| Rail | Nominal Expected | Measured Current | Notes / Variance |
| ---- | ---------------- | ---------------- | ---------------- |
| 12V  | ~130mA           |                  |                  |
| 3.3V | ~70mA            |                  |                  |
| 2.5V | ~4mA             |                  |                  |

- [ ] **Individual Power Test Complete**

---

### FMC Breakout Power Testing

Using a 3 output power supply and two FMC Power breakout modules: Power up all input power rails (12V/3.3V/2.5V) simultaneously.

Note variance from nominal current if found.

| Rail | Nominal Expected | Measured Current | Notes / Variance |
| ---- | ---------------- | ---------------- | ---------------- |
| 12V  | ~130mA           |                  |                  |
| 3.3V | ~70mA            |                  |                  |
| 2.5V | ~4mA             |                  |                  |

- [ ] **FMC Breakout Power Test Complete**

---

### Power Up with Marble

Attach a now power tested quartz to a **powered off** marble testing chassis.

1. Power up the testing chassis.
2. Start the IOC.
3. Ensure proper readback of diagnostic signals (voltage, etc.).

- [ ] **Power Up with Marble Complete**

---

### EEPROM Programmed

Checkout the branch/revision appropriate to the PCB model to be programmed, and edit `createEEPROMs.sh` with the appropriate serial numbers.

* **Git Revision / Commit Used:**

- [ ] **EEPROM Programmed Complete**

---

### Signal Check - Clock Routing

1. Ensure the chassis under test has an EVR input at a nominal 125MHz provided by another chassis.
2. Route received 125MHz through to the first jitter cleaner (U18) using `FMC_LA_1` pin pair:
   * Ensure the System can now lock to `FMC_GBTCLK0`.
   * Using the FPGA console run `fmon` to see the clock also on `FMC_LA_0` signal pair.
3. Route received 125MHz through to the first jitter cleaner (U18) using `FMC_LA_18`:
   * Ensure the System can now lock to `FMC_GBTCLK1`.
   * Using the FPGA console run `fmon` to see the clock also on `FMC_LA_17` signal pair.
4. Ensure that each scenario locks.

- [ ] **Clock Routing Signal Check Complete**

---

### Signal Check - Digital Outputs

1. For each Digital Output set up and send an event stream turning all outputs on and off at 1Hz.
2. Force 0/1.
3. Look at each of the 16 outputs to ensure compliance.

**Channels Checked:**

| Channels 0–7 | Channels 8–15 |
| :--- | :--- |
| Ch 0: [ ] Pass | Ch 8: [ ] Pass |
| Ch 1: [ ] Pass | Ch 9: [ ] Pass |
| Ch 2: [ ] Pass | Ch 10: [ ] Pass |
| Ch 3: [ ] Pass | Ch 11: [ ] Pass |
| Ch 4: [ ] Pass | Ch 12: [ ] Pass |
| Ch 5: [ ] Pass | Ch 13: [ ] Pass |
| Ch 6: [ ] Pass | Ch 14: [ ] Pass |
| Ch 7: [ ] Pass | Ch 15: [ ] Pass |

- [ ] **Digital Outputs Signal Check Complete**

---

## Start/Completion Validation

* **Tests Performed By:**
* **Date Initiated:**
* **Date Completed:**

### Final Result

Indicate a Pass/Fail if this was performed with no deviations or waivers:

- [ ] **Final Result: Pass**

* **Deviations / Waivers / Comments:**
* **QA Procedure Git Commit:**
