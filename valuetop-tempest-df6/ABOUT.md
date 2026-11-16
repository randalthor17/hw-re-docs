## ValueTop Tempest DF6 Display

- **What it is:** The segmented LCD built into the ValueTop Tempest DF6 case. It shows three readings at once: CPU temperature, CPU cooler speed (RPM) and GPU temperature.
- **Digits:** Two for the CPU temperature, four for the cooler RPM and two for the GPU temperature. It does not hold a value by itself: the host must keep sending readings.
- **Input:** Nothing is read back from the display. The host sends readings and that is the whole protocol.
- **Connectivity:**
	- **Wired:** USB, appears as VID:PID `5131:2007`. It has no manufacturer or product string, so Linux names it "HID 5131:2007".
	- Full-speed USB (12 Mbit/s), one HID interface, bus powered (the descriptor asks for 100 mA). `bcdDevice` is `1.00`.
- **Protocol:** One 63-byte report on an interrupt endpoint. Three fields: CPU temperature, cooler RPM and GPU temperature. There is no handshake, no reply and no checksum that the host uses. See [PROTOCOL.md](PROTOCOL.md).
- **Quirk:** The display shows a different number from the one it is sent for every RPM value of 2560 and above unless the host pre-compensates the value it sends. Two ranges (2560–2599 and 7660–7679) cannot be shown at all. The rules are in [PROTOCOL.md](PROTOCOL.md#rpm-display-quirk).
- **Firmware:** Not examined. No firmware image or update flow was looked at. The protocol comes from a packet capture of the vendor's own software plus trial and error on the unit.
- **Ecosystem:** Nothing on a normal Linux desktop reads or writes this device, so it needs a small program that copies sensor readings to it. Which hwmon chip counts as "the CPU" or "the cooler" is a choice of that program, not something the display decides.
