
**Note:** Tested on one ValueTop Tempest DF6 display (`5131:2007`, `bcdDevice` 1.00). The USB descriptors were read from the unit. The report layout was taken from a **packet capture of the vendor's own software** talking to the display, then confirmed by sending reports of my own and watching what the display showed. The RPM rules were found by **trial and error**: sending values and reading what the display showed. Both are implemented in a userspace program (libusb) and a kernel HID driver. Nothing here was found by decoding firmware. Each entry says how far it was checked.

Status values:

- **Verified (read)**: read from the unit while writing this document.
- **Verified (write)**: sent to the unit and the display showed the expected numbers. For the layout, it also matches the vendor software's captured traffic.
- **Derived**: worked out from a table in this document, not from the device.
- **Untested**: not tried, or not known.

The display has **one command**, an output report that carries the three readings. It is a one-way channel: the host sends, and nothing in the protocol asks the display for a reply. Each report replaces what is shown, and the display shows nothing on its own: it needs a steady stream of reports.

---

## USB Interface (`5131:2007`)

The display has a single HID interface with no report IDs.

| **Interface** | **Report ID** | **Direction**         | **Payload Size** | **Usage Page**           | **Usage**                 | **Description & Purpose**                                                              |
| ------------- | ------------- | --------------------- | ---------------- | ------------------------ | ------------------------- | -------------------------------------------------------------------------------------- |
| **0**         | none          | OUT / IN / Feature    | 64 Bytes each    | Consumer (`0x0C`)        | Consumer Control (`0x01`) | **Display data**: the output report below. The Consumer usage is a placeholder; the data is not a media key. |

| **Endpoint** | **Type**  | **Direction** | **Max Packet** | **Interval** |
| ------------ | --------- | ------------- | -------------- | ------------ |
| `0x01`       | Interrupt | OUT           | 64 Bytes       | 10 ms        |
| `0x81`       | Interrupt | IN            | 64 Bytes       | 10 ms        |

Status: **Verified (read)**.

The report descriptor, read from the unit (27 bytes):

```
05 0c            Usage Page (Consumer)
09 01            Usage (Consumer Control)
a1 01            Collection (Application)
15 00              Logical Minimum (0)
25 ff              Logical Maximum (255)
75 08              Report Size (8)
95 40              Report Count (64)
09 01              Usage (Consumer Control)
b1 02              Feature (Data, Variable, Absolute)
09 01              Usage (Consumer Control)
81 02              Input   (Data, Variable, Absolute)
09 01              Usage (Consumer Control)
91 02              Output  (Data, Variable, Absolute)
c0               End Collection
```

On Linux the kernel binds `hid-generic` and creates a `/dev/hidraw` node, root-only by default. Write to that node, or to the interrupt OUT endpoint directly.

The descriptor declares an Input and a Feature report as well. What the display puts in them, if anything, was not looked at. No driver reads them.

---

## Frame (Output Report)

Every update is one transfer of **63 bytes** on the interrupt OUT endpoint. There is no report ID on the wire. The descriptor declares 64 bytes; the working drivers send 63 and the display accepts them. Offsets are within those 63 bytes.

| **Byte Index** | **Field Name**    | **Description / Value**                                                                  | **Status**  |
| -------------- | ----------------- | ---------------------------------------------------------------------------------------- | ----------- |
| **`0`**        | Padding           | `00`                                                                                     | Verified (write) |
| **`1`**        | CPU Temperature   | One byte, whole degrees Celsius. The display has **2 digits** for it                | Verified (write) |
| **`2–4`**      | Padding           | `00`                                                                                     | Verified (write) |
| **`5–6`**      | CPU Cooler RPM    | 16-bit **big-endian**, high byte first. The display has **4 digits** for it. **Not** the number shown: see [RPM Display Quirk](#rpm-display-quirk) | Verified (write) |
| **`7–8`**      | Padding           | `00`                                                                                     | Verified (write) |
| **`9`**        | GPU Temperature   | One byte, whole degrees Celsius. The display has **2 digits** for it                | Verified (write) |
| **`10–62`**    | Padding           | `00`                                                                                     | Verified (write) |

There is no checksum and no magic byte.

**The display does not hold a value.** It shows a reading only while reports keep arriving, so a host has to send continuously. The drivers send once a second. How long the display can go without a report before it stops showing the value was not measured.

```
// One update. RPM is the value the host wants shown.
function vt_send(cpu_temp, rpm, gpu_temp):
    sent = patch_rpm(rpm)                  // see below
    buf = zeros(63)
    buf[1]  = clamp(cpu_temp, 0, 255)
    buf[5]  = sent >> 8
    buf[6]  = sent & 0xFF
    buf[9]  = clamp(gpu_temp, 0, 255)
    interrupt_out(0x01, buf)               // 1 s timeout; refresh about once a second
```

### Hosts that send a leading report-ID byte

An API that takes a numbered report (the Linux kernel's `hid_hw_output_report`, or a hidraw `write`) wants the report ID as the **first** byte. For a device with no report IDs that byte is `0`, and the stack removes it before the transfer. Build a **64-byte** buffer with `00` in front of the layout above (so every index in the table moves up by one: CPU temperature at `2`, RPM at `6–7`, GPU temperature at `10`). The stack then sends the same 63 bytes.

### Not known

| **Question**                                                                 | **Status** |
| ---------------------------------------------------------------------------- | ---------- |
| What the display shows for a temperature above 99 °C (it has two digits), and how soon it stops showing a value after reports stop | Untested   |
| Whether a 64-byte transfer is accepted as well as a 63-byte one              | Untested   |
| Whether a temperature of `0` blanks the field or shows `0`                   | Untested   |
| What the Input and Feature reports contain                                   | Untested   |

---

## RPM Display Quirk

The display firmware does not show the number it is sent. For a 16-bit value `i` sent as the RPM, with `tens_ones = i mod 100`, the number shown is:

| **Value sent (`i`)**   | **Condition**          | **Number shown** |
| ---------------------- | ---------------------- | ---------------- |
| `0 – 2559`             | always                 | `i`              |
| `2560 – 5999`          | `tens_ones` < 60       | `i + 40`         |
| `2560 – 5999`          | `tens_ones` ≥ 60       | `i − 60`         |
| `6000 – 7679`          | `tens_ones` < 20       | `i + 80`         |
| `6000 – 7679`          | `tens_ones` ≥ 20       | `i − 20`         |
| `7680` and above       | `tens_ones` < 80       | `i + 20`         |
| `7680` and above       | `tens_ones` ≥ 80       | `i − 80`         |

Status: **Verified (write)**, found by trial and error on the unit. The drivers compensate for exactly this behaviour.

The host therefore sends a **pre-compensated** value: it picks the `i` whose shown number is the one it wants.

```
function patch_rpm(want):
    if want < 2560: return want
    // each candidate is only valid if it lands in its own range with the right tens_ones
    c = want - 40;  if 2560 <= c < 6000  and c % 100 <  60: return c
    c = want + 60;  if 2560 <= c < 6000  and c % 100 >= 60: return c
    c = want - 80;  if 6000 <= c < 7680  and c % 100 <  20: return c
    c = want + 20;  if 6000 <= c < 7680  and c % 100 >= 20: return c
    c = want - 20;  if 7680 <= c < 10000 and c % 100 <  80: return c
    c = want + 80;  if 7680 <= c < 10000 and c % 100 >= 80: return c
    return want                             // not reachable: shown wrong
```

For example, to show `3000` the host sends `3060` (`60` is not below 60, so `i − 60` applies: 3060 − 60 = 3000).

### Values that cannot be shown

Working the table through every value sent from `0` to `10159` gives exactly two ranges of numbers that no value produces:

| **Range**       | **Status** |
| --------------- | ---------- |
| `2560 – 2599`   | Derived    |
| `7660 – 7679`   | Derived    |

`patch_rpm` returns the wanted value unchanged for these, so the display shows a different number: wanting `2580` sends `2580`, which shows `2520`; wanting `7670` sends `7670`, which shows `7650`. For every other value from `0` to `9999`, `patch_rpm` followed by the table gives back the wanted number. Derived.

The table also lets two different values sent show the same number: `2500 – 2539` can be produced by sending the same number or by sending `2560 – 2599`, and `7600 – 7619` can be produced two ways as well. `patch_rpm` returns the first one it finds. Derived.
