## ATK / VXE R1 NK

- **Sensor:** PixArt PAW3395SE
- **Buttons:** Left, right, middle, back, forward, plus one DPI button (six configurable entries). The scroll wheel is not remappable.
- **DPI:** Eight stage slots, four configured by default (400, 800, 1600, 3200). The sensor range is 200 to 18000 DPI in steps of 50 (from the vendor's sensor table; not exercised through the protocol). The mouse has no separate X/Y resolution, so both axes always hold the same value.
- **Report rate:** 125, 250, 500 or 1000 Hz. The mouse identifies itself as a 1K device on the cable, so the 2K, 4K and 8K codes that exist in the protocol are not expected to apply.
- **Lighting:** One light setting (off, breathing or steady, with three brightness steps and three speeds) and one colour per DPI stage.
- **Sensor settings:** Lift-off distance, motion sync, linear correction, ripple control, sensor sleep time and button debounce time can all be changed over the protocol.
- **Onboard storage:** Settings, DPI stages, button bindings and macros live on the mouse. It keeps more than one profile, each with its own settings and its own macros; four profiles (0 to 3) exist; switching between them works.
- **Connectivity:**
	- **Wired:** USB cable, appears as "ATK VXE R1 NK" with VID:PID `373b:124c`
	- **NearLink:** Connected using the receiver, appears as "ATK NK mouse NANO dongle" with VID:PID `373b:1216`. Other NearLink mice use the same receiver ID, so the mouse model has to be read from the mouse and cannot be taken from the USB ID.
- **Power:** Battery level (percent) and voltage can be read over the protocol. Seen on the unit: 72 % at 3952 mV and 82 % at 4038 mV.
- **Firmware:** The unit ran mouse firmware 1.0.12 and receiver firmware 1.0.17, and later 1.0.20 on the receiver. Receiver versions 1.0.12 to 1.0.19 exist; no mouse firmware is published for this USB ID.
- **Ecosystem:** The same command layer is used by other ATK and VXE NearLink and 2.4 GHz mice. This document only vouches for the R1 NK. Models that were not tested are called out as such.
