
**Note:** I do not have a Bluetooth adapter, and so the Bluetooth protocol remains unsolved. I would love it if someone takes up the work though :)

The keyboard has **one command layer**. Over the cable, the host talks to it with 520-byte feature reports. Over 2.4 GHz, the host talks to the receiver with 20-byte reports, and the receiver forwards them over the air. Both end up in the same handlers, so the two transports differ only in framing and command numbers. Everything the protocol stores lives in the MCU's own flash, in 512-byte sectors.

---

## Wired Protocol (`258a:010c` "BY Tech Gaming Keyboard")

When connected via USB-C, the keyboard appears as two separate **physical** USB interfaces. Interface 0 handles the standard USB boot protocol, while Interface 1 combines all consumer keys, vendor event channels, N-key rollover (NKRO) matrices, mouse emulation, and protocol feature reports.

### Interface 0: USB Boot Keyboard

| **Endpoint Type** | **Direction** | **Payload Size** | **Usage Page**           | **Usage**         | **Description & Purpose**                                                  |
| ----------------- | ------------- | ---------------- | ------------------------ | ----------------- | -------------------------------------------------------------------------- |
| **Interrupt IN**  | IN            | 8 Bytes          | Generic Desktop (`0x01`) | Keyboard (`0x06`) | **Standard USB Boot Protocol**: 6-key rollover (6KRO) boot keyboard report |

### Interface 1: Extended Features & Vendor Protocol

| **Report ID** | **Endpoint Type**     | **Direction** | **Payload Size** | **Usage Page**            | **Usage**                 | **Description & Purpose**                                                                   |
| ------------- | --------------------- | ------------- | ---------------- | ------------------------- | ------------------------- | ------------------------------------------------------------------------------------------- |
| 1             | **Interrupt IN**      | IN            | 1 Byte           | Generic Desktop (`0x01`)  | System Control (`0x80`)   | **System Power Control**: Sleep, Wake, and Power events                                     |
| 2             | **Interrupt IN**      | IN            | 2 Bytes          | Consumer (`0x0C`)         | Consumer Control (`0x01`) | **Media Control Keys**: Volume Up/Down, Mute, Track controls                                |
| 3             | **Interrupt IN**      | IN            | 3 Bytes          | Vendor Defined (`0xFF00`) | Vendor Defined (`0x01`)   | **Vendor Event Channel**: Reports Fn key presses & returns `0xAA` echo responses to host    |
| 4             | **Interrupt IN**      | IN            | 15 Bytes         | Generic Desktop (`0x01`)  | Keyboard (`0x06`)         | **NKRO Matrix Bitmap**: Key usages `0x04–0x70`. _Macro sequences type through this report._ |
| 5             | **Control / Feature** | OUT / IN      | 5 Bytes (+ID)    | Vendor Defined (`0xFF00`) | Vendor Defined (`0x01`)   | **ISP Bootloader Trigger**: Payload `05 75 ...` forces jump to hardware bootloader          |
| 6             | **Control / Feature** | OUT / IN      | 519 Bytes (+ID)  | Vendor Defined (`0xFF00`) | Vendor Defined (`0x01`)   | **Main Configuration Protocol**: Read/Write Matrix, Config, Macros, Palette, & Side Light   |
| 6             | **Interrupt IN**      | IN            | 7 Bytes          | Vendor Defined (`0xFF00`) | Vendor Defined (`0x01`)   | **Vendor Status**: Return buffer for vendor status queries                                  |
| 7             | **Interrupt IN**      | IN            | Variable         | Generic Desktop (`0x01`)  | Mouse (`0x02`)            | **Mouse Emulation**: Buttons, X/Y movement axes, and scrolling wheel                        |

### Feature Report 6 Frame Byte Breakdown

Every transfer is one 520-byte feature report. Data longer than 512 bytes is split into numbered blocks.

| **Byte Index** | **Field Name** | **Description / Value**                                      |
| -------------- | -------------- | ------------------------------------------------------------ |
| **`0`**        | Report ID      | Constant `0x06`                                              |
| **`1`**        | Command Code   | See [Commands](#commands)                                    |
| **`2`**        | Index          | For the keymap this is the **layer** (`0–3`); otherwise `00` |
| **`3`**        | Reserved       | `00`                                                         |
| **`4`**        | Total Blocks   | Number of 512-byte blocks in the transfer                    |
| **`5`**        | Block Number   | 0-based                                                      |
| **`6–7`**      | Payload Length | Bytes in this block, little-endian                           |
| **`8–519`**    | Payload Array  | Up to 512 bytes                                              |

WebHID's `sendFeatureReport(6, data)` takes the 519 bytes after the ID.

### Reading (GET)

A GET command is the SET command with bit 7 set: SET `0x04` becomes GET `0x84`. For each block:

1. Wait 20 ms.
2. Send the frame header with no payload. `length` = the number of bytes wanted from this block.
3. Wait 20 ms.
4. Read feature report 6.

The reply echoes header bytes 1–7, then only the requested bytes. On Linux, Chrome includes the report ID: recognise a reply by `raw[0] == 6 && raw[1] == cmd`.

GETs don't check bounds: the block number simply adds `block × 0x200` to the start address. That is how block 1 of GET `0x83` reads the macOS half of a keymap layer.

```
// GET: returns `length` bytes, read in 512-byte blocks
function usb_get(cmd, length, index = 0, first_block = 0):
    out    = []
    blocks = ceil(length / 512)
    for b in 0 .. blocks - 1:
        n   = min(512, length - b * 512)
        buf = zeros(520)
        buf[0..7] = [0x06, cmd | 0x80, index, 0x00, blocks, first_block + b, n & 0xFF, n >> 8]
        sleep(20 ms)
        send_feature_report(buf)                 // SET_REPORT: header only, no payload
        sleep(20 ms)
        raw = get_feature_report(6, 520)         // GET_REPORT
        if raw[0] != 0x06 or raw[1] != (cmd | 0x80): error("unexpected reply")
        out += raw[8 .. 8 + n - 1]               // after ID + 7 echoed header bytes
    return out
```

### Writing (SET)

For each block, wait 20 ms and send the frame with its payload. Nothing is read back. Retry a failed send up to 3 times, 70 ms apart (the OEM app does the same).

- **Every SET takes about 67 ms**, whatever the command. The keyboard takes the 520 bytes 8 at a time, one packet per 1 ms USB frame. It needs the full 520 bytes: a shorter report timed out and the keyboard reset. So direct LED frames over the cable top out at about 15 frames/s. A host should send them from their own thread so it doesn't hold up other devices.
- **Every SET except `0x08` blanks all LEDs for about 2 s**, longer while direct mode is on. The pause guards flash writes, but it also hits commands that write nothing: `0x07` and `0x09` (which do nothing on stock firmware) and `0xAA`.
- **SETs are ignored while config byte 14 ≠ 0**, i.e. while the keyboard is in 2.4 GHz or Bluetooth mode and the cable only charges it.
- **There is no save command.** Writes persist across a power cycle on their own.

```
// SET: sends `data` in 512-byte blocks; always a full 520-byte report
function usb_set(cmd, data, index = 0):
    blocks = max(1, ceil(len(data) / 512))
    for b in 0 .. blocks - 1:
        chunk = data[b * 512 .. b * 512 + 511]
        buf   = zeros(520)
        buf[0..7] = [0x06, cmd, index, 0x00, blocks, b, len(chunk) & 0xFF, len(chunk) >> 8]
        buf[8 ..] = chunk
        sleep(20 ms)
        repeat up to 3 times, 70 ms apart, until it succeeds:
            send_feature_report(buf)             // SET_REPORT, ~67 ms
```

### Report 5: Bootloader Entry

Feature report 5 `05 75 00 00 00 00` jumps into the ISP bootloader. The keyboard re-enumerates as `0603:1020` "SINO WEALTH Gaming KB" (root-only on Linux). Any other report-5 payload does nothing useful. How the bootloader works, and how to read and write the firmware, is in [FIRMWARE.md](FIRMWARE.md#bootloader-and-isp).

```
send_feature_report([0x05, 0x75, 0x00, 0x00, 0x00, 0x00])
// the keyboard drops off the bus and comes back as 0603:1020
```

### Report 3: Event Channel

The keyboard sends input report 3 as `03 code arg state`, over the cable only.

| **Event**            | **Bytes**        | **Meaning**                                                                                                                      |
| -------------------- | ---------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Echo**             | `03 aa index 00` | Answer to SET `0xAA` with that index                                                                                             |
| **Lighting changed** | `03 08 00 01`    | Sent after **every** lighting Fn press (effect, brightness, speed, colour, side light). Re-read the config to learn what changed. |

Device-function keys (Fn + Win, Fn + B) send nothing on report 3.

```
// echo
usb_set(0xAA, [], index = 0x5C)
r = read_input_report()                          // until r[0] == 0x03
// r == [03 aa 5c 00]

// lighting changed by a Fn key
on input report [03 08 00 01]:
    cfg = usb_get(0x84, 128)                     // re-read to see what changed
```

---

## Wireless Protocol (`3554:fa09` "Compx 2.4G Wireless Receiver")

When operating over the wireless 2.4 GHz dongle, communications bypass large 520-byte feature reports. Instead, all data is handled over a **single vendor interface** using **20-byte packetized frames**.

### Vendor Wireless Interface

| **Report ID** | **Endpoint Type**      | **Direction** | **Frame Size** | **Usage Page**            | **Usage**                 | **Description & Purpose**                                                                                                         |
| ------------- | ---------------------- | ------------- | -------------- | ------------------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `0x13`        | **Interrupt IN / OUT** | Bidirectional | 20 Bytes       | Vendor Defined (`0xFF02`) | Vendor Defined (`0x0002`) | **RF Protocol Transport**: Packetized channel for wireless configuration, matrix sync, and unsolicited battery/link status events |

### Report `0x13` Frame Byte Breakdown

_Every frame transferred over Report ID `0x13` follows this fixed 20-byte packet structure:_

| **Byte Index** | **Field Name**         | **Description / Value**                                                                                 |
| -------------- | ---------------------- | ------------------------------------------------------------------------------------------------------- |
| **`0`**        | Report ID              | Constant `0x13`                                                                                         |
| **`1`**        | Command Code           | See [Commands](#commands)                                                                               |
| **`2`**        | Total Packages         | Total number of 20-byte packages in the transfer. _On replies, Bit 7 set (`0x80`) indicates an error._ |
| **`3`**        | Package Index          | 0-based sequence counter for the current package                                                        |
| **`4`**        | Layer / Length Nibbles | **High Nibble**: Target Layer / Block Index; **Low Nibble**: Valid Payload Length in bytes (`0–14`)     |
| **`5–18`**     | Payload Array          | Up to 14 bytes of configuration or keymap data                                                          |
| **`19`**       | Frame Checksum         | Modulo 256 sum of all preceding bytes: `(Sum of Bytes 0–18) % 256`                                      |

_A 128-byte config block therefore travels as 10 packages (9 × 14 bytes + 1 × 2 bytes), and a 512-byte sector as 37._

### Reading

Send one frame with the GET command, `packages = 1`, `index = 0`, `length = 0`, and the layer / block in the high nibble of byte 4. The receiver answers with `total` frames, numbered `0 … total − 1`. Concatenate their payloads.

While waiting, skip unrelated input reports (key events and unsolicited reports). Allow up to 5 s for a reply: a sleeping keyboard first has to wake up.

```
function rx_frame(cmd, packages, index, layer, payload):   // payload: 0-14 bytes
    f = zeros(20)
    f[0..4] = [0x13, cmd, packages, index, (layer << 4) | len(payload)]
    f[5 ..] = payload
    f[19]   = sum(f[0..18]) & 0xFF
    return f

// GET: concatenates the payloads of all reply frames
function rx_get(cmd, layer = 0):
    write_output_report(rx_frame(cmd, 1, 0, layer, []))
    out = [];  expect = 0
    loop (timeout 5 s, then retry up to 3 times, 70 ms apart):
        r = read_input_report()
        if r[0] != 0x13 or (r[1] & 0x7F) != cmd: continue   // key events, 0x0A reports
        if r[2] & 0x80: error("device reported error")
        if r[3] != expect: error("out of order")
        out += r[5 .. 5 + (r[4] & 0x0F) - 1]
        expect += 1
        if r[3] == (r[2] & 0x7F) - 1: return out              // last package
```

**Wireless GETs return less than the full sector.** Writes still rewrite all 512 bytes, so a read-modify-write over the receiver has to supply the missing tail itself (take it from a wired read). Otherwise those bytes are lost.

| **Data**         | **Bytes Returned** | **Missing Tail**                                                       |
| ---------------- | ------------------ | ---------------------------------------------------------------------- |
| Keymap (`0x41`)  | 504                | `00 00 00 00 00 00 5a a5`                                              |
| Per-key (`0x42`) | 378                | Bytes 378–511 as stored (starts `00 00 5a a5`)                         |
| Palette (`0x49`) | 490                | Bytes 490–511 as stored (identity bytes, see [Palette](#palette-512-bytes)) |
| Macros (`0x43`)  | 512                | None                                                                   |

### Writing

Send the packages in order, about 15 ms apart. The receiver acknowledges each one with a frame that echoes the command and package index. Wait for it, and resend the package if the index doesn't match. Don't wait for an acknowledgement on `0x06` (reset), `0x08` (direct LEDs) or any command ≥ `0x80`.

```
// SET: one package per 14 bytes; `ack` = false for 0x06, 0x08 and commands >= 0x80
function rx_set(cmd, data, layer = 0, ack = true):
    n = max(1, ceil(len(data) / 14))
    for i in 0 .. n - 1:
        write_output_report(rx_frame(cmd, n, i, layer, data[i * 14 .. i * 14 + 13]))
        if ack:
            r = next input report with r[1] & 0x7F == cmd       // skip others
            if r[2] & 0x80 or r[3] != i: resend package i
        sleep(15 ms)
```

### Unsolicited Reports

The receiver also sends frames with command `0x0A`, laid out `[0x0A, 1, 0, len, type, value, extra]`:

| **Type** | **Meaning**                                                                  |
| -------- | ---------------------------------------------------------------------------- |
| **`2`**  | Link state: value `1` = up, `0` = down                                       |
| **`5`**  | Battery: value = percent, extra = flag                                       |
| **`7`**  | Sent ~0.5 s after every config write, probably "settings applied" (`7 0 0`) |

> **Not a save command.** Older notes (and the [AULA F87 project](https://github.com/marcoslor/Aula-F87-Controller)) send `13 0A 01 00 04 07 00 …` after every config write as "save". It is really the OEM app's "select onboard profile" command, used only for mice. The MK75 never needs it. Don't send it.

---

## Commands

| **Function**                         | **USB SET** | **USB GET**      | **Wireless SET** | **Wireless GET** | **Data**                                              |
| ------------------------------------ | ----------- | ---------------- | ---------------- | ---------------- | ----------------------------------------------------- |
| **Keymap layer**                     | `0x03`      | `0x83`           | `0x01`           | `0x41`           | [Keymap](#keymap)                                     |
| **Configuration block**              | `0x04`      | `0x84`           | `0x04`           | `0x44`           | [Configuration Block](#configuration-block-128-bytes) |
| **Macro store**                      | `0x05`      | `0x85`           | `0x03`           | `0x43`           | [Macros](#macros)                                     |
| **Per-key colours**                  | `0x06`      | `0x86`           | `0x02`           | `0x42`           | [Per-Key Colours](#per-key-colours-378-bytes)         |
| **Direct LED stream**                | `0x08`      | —                | `0x08`           | —                | [Direct Mode](#direct-mode)                           |
| **Palette**                          | `0x0A`      | `0x8A`           | `0x09`           | `0x49`           | [Palette](#palette-512-bytes)                         |
| **Identity (PSD)**                   | —           | `0x82` (index 1) | —                | `0x05`           | [Identity and Power](#identity-and-power-status)      |
| **Power status**                     | —           | `0x87`           | —                | `0x4A`           | [Identity and Power](#identity-and-power-status)      |
| **Link state**                       | —           | —                | —                | `0x07`           | —                                                     |
| **Firmware read**                    | —           | `0x88`           | —                | —                | [Identifying the MK75](#identifying-the-mk75)         |
| **Echo**                             | `0xAA`      | —                | —                | —                | Answered on [input report 3](#report-3-event-channel) |
| **Side-light direct** (patched only) | `0x07`      | —                | `0x08`, layer 3  | —                | [Side Light](#side-light)                             |
| **Reset device**                     | `0x11`      | —                | `0x06`           | —                | _Don't send casually._                                |

`0x0B` and `0x0F` (screen / self data) exist in the OEM app but are unused on the MK75.

---

## Configuration Block (128 Bytes)

Read/Write via commands `0x84` / `0x04` (wired) or `0x44` / `0x04` (wireless). Lives in flash at `0xC600`; the factory default copy is at `0xC400`.

Always **read-modify-write**: read the block, change the bytes you need, write all 128 bytes back. The OEM app does exactly this, so bytes it doesn't understand keep their value.

```
cfg = usb_get(0x84, 128)                         // wireless: cfg = rx_get(0x44)
if cfg[56..57] != [ff ff] or cfg[126..127] != [5a a5]:
    stop                                         // sleeping keyboard or bad read: never write this back
cfg[10] = 2                                      // e.g. effect Respire
cfg[9]  = (cfg[10] == 21) ? 1 : 0                // per-key enable, as the OEM app sets it
usb_set(0x04, cfg)                               // wireless: rx_set(0x04, cfg)
```

| **Byte Index** | **Field / Parameter Name** | **Value Range / Description**                                                                                   |
| -------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **`00`**       | OS Mode / Keymap Page      | `00` Windows, `01` macOS (uses the macOS half of each keymap layer). Set by FN + E.                            |
| **`01–02`**    | Unknown                    | Default: `03 03`                                                                                                |
| **`03`**       | Debounce Level             | `00` to `04` (the OEM app shows value + 1)                                                                      |
| **`04`**       | Unknown                    | Default: `00`                                                                                                   |
| **`05`**       | Global Lighting Switch     | `00` Use per-effect pairs; `≠0` Use bytes 6–8 for every effect                                                  |
| **`06`**       | Global Brightness          | Used when byte 5 ≠ 0                                                                                            |
| **`07`**       | Global Speed               | `00` slow (≈ 8 s per breath) to `04` fast (≈ 3 s); used when byte 5 ≠ 0                                         |
| **`08`**       | Global Colour Mode         | Low nibble `7` = colourful, `0` = single colour (first palette colour); used when byte 5 ≠ 0                    |
| **`09`**       | Per-Key Enable Flag        | `01` Render the effect in byte 11 instead of byte 10. The OEM app sets it exactly when Self-define is chosen.  |
| **`10`**       | Active Lighting Effect     | See [Lighting Effects](#lighting-effects)                                                                       |
| **`11`**       | Per-Key Effect ID          | `0x20` (32), the per-key renderer. Any effect number works here.                                                |
| **`12`**       | Wireless RF Channel        | `1–3`. _Untested: changing it can drop the 2.4 GHz link._                                                       |
| **`13`**       | Unknown                    | Default: `00`                                                                                                   |
| **`14`**       | Connection Mode            | `00` Wired USB, `01` 2.4 GHz, `02` Bluetooth. **While ≠ 0, wired SETs are ignored.**                            |
| **`15`**       | Win-Key Lock               | `≠0` (Windows mode only): Win keys and the Menu key do nothing                                                  |
| **`16`**       | Full Key Lock              | `≠0` Every key does nothing; only the knob still works                                                          |
| **`17`**       | Unknown Flag               | No effect found                                                                                                 |
| **`18`**       | Side Light Mode            | `00` Off, `01` Rainbow Wave, `02` Rainbow Breathing, `03` Static, `04` Colour Breathing                         |
| **`19`**       | Side Light Colour          | `0` Red, `1` Green, `2` Blue, `3` Yellow, `4` Purple, `5` Cyan, `6` White, `7` Off, `8` Cyan                    |
| **`20`**       | Side Light Brightness      | `00` to `04`. Higher values blink erratically.                                                                  |
| **`21`**       | Side Light Speed           | `00` to `04`                                                                                                    |
| **`22`**       | Tap/Hold Threshold         | `00` Off, or the hold time in ~21 ms units. See [Tap/Hold Keys](#taphold-keys).                                 |
| **`23`**       | Auto-Detect Setting        | Default: `ff`. Unused on the MK75.                                                                              |
| **`24`**       | Sleep Timeout Timer        | Units of 30 s: `1, 2, 3, 4, 6, 8, 10, 20, 30, 40` (30 s up to 20 min). `00` = never sleep. Wireless modes only. |
| **`25`**       | Side-Light Ramp Direction  | Breathing direction for side mode 4 (`00` or `01`). A lighting key flips it. Both look the same.                |
| **`26`**       | Rotary Encoder Mode        | `1` Gaming (brightness / effect), `0` Media (volume)                                                            |
| **`27`**       | OS Mode, Part 2            | FN + Q (Android) sets it; FN + W (Windows) clears it and byte 0                                                 |
| **`28–55`**    | Unknown                    | Keep as read                                                                                                    |
| **`56–57`**    | Configuration End Marker   | Always `ff ff`. **Never write a block without it** (see [Quirks](#power-sleep-and-charging-quirks)).            |
| **`58–93`**    | Effect Pairs               | 18 pairs of [Brightness, Speed/Colour] for effects 1–18 (tested for 1–17). See [Effect Pairs](#effect-pairs).   |
| **`94–95`**    | Self-Define Pair           | Written by the OEM app; the keyboard ignores it                                                                 |
| **`117`**      | Per-Key Brightness         | Brightness used while byte 9 = 1 (presumably `0–4`, like the other brightness bytes)                            |
| **`126–127`**  | Block Integrity Trailer    | Constant `5a a5`. Checked by the boot loader.                                                                   |

### Tap/Hold Keys

When byte 22 ≠ 0, every key whose cell in **keymap layer 3** is non-zero becomes a tap/hold key:

- Released **before** `byte 22 × 21 ms`: it sends its layer-3 cell (the tap action).
- Held **longer**: it acts as its normal key.

Example: layer 3 cell 9 = `B` and byte 22 = 20 (≈ 420 ms). Tapping A types `b`; holding A for 1 s types `a`.

```
l3 = usb_get(0x83, 512, index = 3)               // keymap layer 3
l3[9*4 .. 9*4+3] = [00 00 00 05]                 // A (cell 9) taps B
usb_set(0x03, l3, index = 3)
cfg = usb_get(0x84, 128);  cfg[22] = 20;  usb_set(0x04, cfg)
```

---

## Lighting Effects

_Byte 10 of the config block._

| **Effect** | **Name**           | **Pair Bytes** | **Notes**                                                                    |
| ---------- | ------------------ | -------------- | ---------------------------------------------------------------------------- |
| **`0`**    | Off                | —              |                                                                              |
| **`1`**    | Fixed On           | 58–59          |                                                                              |
| **`2`**    | Respire            | 60–61          | "Colourful" is a fixed blue–green–red gradient (left to right) that breathes |
| **`3`**    | Rainbow            | 62–63          |                                                                              |
| **`4`**    | Flash Away         | 64–65          |                                                                              |
| **`5`**    | Raindrops          | 66–67          |                                                                              |
| **`6`**    | Rainbow Wheel      | 68–69          | **Not implemented**: keys stay dark                                          |
| **`7`**    | Ripples Shining    | 70–71          |                                                                              |
| **`8`**    | Stars Twinkle      | 72–73          |                                                                              |
| **`9`**    | Shadow Disappear   | 74–75          |                                                                              |
| **`10`**   | Retro Snake        | 76–77          |                                                                              |
| **`11`**   | Neon Stream        | 78–79          | Factory default                                                              |
| **`12`**   | Reaction           | 80–81          |                                                                              |
| **`13`**   | Sine Wave          | 82–83          |                                                                              |
| **`14`**   | Retinue Scanning   | 84–85          | **Not implemented**: keys stay dark                                          |
| **`15`**   | Rotating Windmill  | 86–87          |                                                                              |
| **`16`**   | Colorful Waterfall | 88–89          |                                                                              |
| **`17`**   | Blossoming         | 90–91          |                                                                              |
| **`18`**   | Rotating Storm     | 92–93          | **Not implemented**: keys stay dark                                          |
| **`21`**   | Self-Define        | —              | Per-key colours. Needs byte 9 = 1; brightness from byte 117.                 |
| **`32`**   | Per-Key (hidden)   | —              | The per-key renderer that Self-define runs. Works with byte 9 = 0 too.       |
| **`38`**   | Per-Key (hidden)   | —              | A second per-key mode, never offered by the OEM app. Works with byte 9 = 0.  |

Effects 6, 14 and 18 are offered by the OEM app (it's shared across models) but missing from the MK75 firmware. Both per-key modes follow per-key writes live.

### Effect Pairs

_Effect `e` (1–18) has its pair at bytes `56 + 2e` and `57 + 2e`._

| **Byte**   | **Content**                                                                  |
| ---------- | ---------------------------------------------------------------------------- |
| **First**  | Brightness `0–4`                                                             |
| **Second** | High nibble: speed `0–4`. Low nibble: `7` = colourful, `0` = single colour. |

FN + F5 / FN + F6 change the current effect's brightness byte by 1. The single colour is the first colour of the effect's [palette](#palette-512-bytes) entry.

```
cfg = usb_get(0x84, 128)
e = 2                                            // Respire
cfg[56 + 2*e] = 3                                // brightness 3
cfg[57 + 2*e] = (4 << 4) | 0                     // speed 4, single colour
usb_set(0x04, cfg)
```

---

## Palette (512 Bytes)

_Read/Write via commands `0x8A` / `0x0A` (wired) or `0x49` / `0x09` (wireless). Lives in flash at `0xC800`._

| **Byte Index** | **Content**                                                                    |
| -------------- | ------------------------------------------------------------------------------ |
| **`e × 21`**   | Entry for effect `e`: 7 colours × `R G B`. **The first colour is the single colour.** |
| **`483–507`**  | Copy of the identity (PSD) bytes: `03 00 00 00 00 c6 … 5a a5`                  |
| **`508–511`**  | `00 10 00 00`                                                                  |

The stock palette holds red, green, blue, yellow, purple, cyan, white in every entry. Colours are full 24-bit RGB, not snapped to presets. Always write all 512 bytes as a read-modify-write, so the identity bytes survive.

```
pal = usb_get(0x8A, 512)
e = 1                                            // Fixed On
pal[e*21 .. e*21+2] = [0xFF, 0x80, 0x00]         // its single colour: orange
usb_set(0x0A, pal)

// wireless: the read is 490 bytes, so add the stored tail from a wired read
pal = rx_get(0x49) + wired_pal[490 .. 511]
rx_set(0x09, pal)
```

---

## Per-Key Colours (378 Bytes)

_Read/Write via commands `0x86` / `0x06` (wired) or `0x42` / `0x02` (wireless). Lives in flash at `0xCA00`. Shown by Self-define (byte 9 = 1), effect 32 or effect 38._

| **Byte Index** | **Content**                     |
| -------------- | ------------------------------- |
| **`0–125`**    | R plane, one byte per LED index |
| **`126–251`**  | G plane                         |
| **`252–377`**  | B plane                         |
| **`378–381`**  | `00 00 5a a5`                   |

The **LED index is the key's keymap cell index** (Esc = 0, A = 9). The knob ring (cell 90) is not in this map: it is a red-only power indicator.

```
pk = usb_get(0x86, 512)                          // wireless: rx_get(0x42) + wired_pk[378 .. 511]
n = 9                                            // A
pk[n] = R;  pk[126 + n] = G;  pk[252 + n] = B
usb_set(0x06, pk)                                // wireless: rx_set(0x02, pk)

cfg = usb_get(0x84, 128);  cfg[10] = 21;  cfg[9] = 1;  usb_set(0x04, cfg)   // show it (Self-define)
```

---

## Direct Mode

_Streams LED colours straight to the keys. Nothing is written to flash. Direct mode ends **about 2 s after the last frame** and the normal effect returns, so keep sending (20 Hz works)._

Direct frames are not blanked while charging, unlike the configured lighting.

### Wired (`0x08`)

Send SET `0x08`, index 0, 1 block, block 0, length 378. The payload is **126 LEDs × `R G B`, interleaved**, by cell index.

| **Byte Index**  | **Content**                                                                 |
| --------------- | --------------------------------------------------------------------------- |
| **`3n … 3n+2`** | `R G B` of LED `n` (`n = 0–125`)                                            |
| **`378–420`**   | Side-light slots, **patched firmware only** (see [Side Light](#side-light)) |

```
frame = zeros(378)
loop every 50 ms (in its own thread):
    for n in 0 .. 125:
        frame[3n .. 3n+2] = colour_of(n)
    usb_set(0x08, frame)                         // ~67 ms each, so ~15 frames/s at most
```

### Wireless (`0x08`)

Not acknowledged: send the packages without waiting. The layer nibble picks the form:

| **Layer** | **Payload**                                    | **Effect**                                                         |
| --------- | ---------------------------------------------- | ------------------------------------------------------------------ |
| **`1`**   | Records `R G B N idx₁ … idx_N`, as many as fit | All LEDs go black, then each listed LED takes its record's colour |
| **`2`**   | `R G B`                                        | Every LED takes that colour                                        |
| **`3`**   | Side-light slots                               | **Patched firmware only** (see [Side Light](#side-light))          |

Layer-1 limits:

- **A frame holds at most 199 bytes of records.** Each distinct colour costs 4 bytes, each lit key 1 byte. With all 81 keys lit, that allows 29 distinct colours; merge the rest.
- Each frame starts from black, so a frame can't be built up in parts.
- An empty frame is ignored. To go all black, send a layer-2 fill of `00 00 00`.

An animated 16-colour rainbow (11 packages per frame) ran smoothly at 15–30 frames/s.

```
// layer 2: one colour everywhere
rx_set(0x08, [R, G, B], layer = 2, ack = false)

// layer 1: records, grouped by colour
records = []
for (colour, leds) in group_leds_by_colour(frame):
    records += [colour.R, colour.G, colour.B, len(leds)] + leds
if len(records) > 199: merge similar colours and rebuild
if records is empty: rx_set(0x08, [0, 0, 0], layer = 2, ack = false)
else:                rx_set(0x08, records, layer = 1, ack = false)   // 1-4 ms between packages works
```

---

## Side Light

6 LEDs inside the left strip, 7 inside the right.

On stock firmware the side light only runs its own modes, set by config bytes 18–21 or the Fn keys. Per-LED control needs the **side-light direct patch** (see [FIRMWARE.md](FIRMWARE.md#side-light-direct-patch)). The patch adds 14 slots of `R G B`, each channel `0–255`:

| **Slot**   | **LED**                   |
| ---------- | ------------------------- |
| **`0–5`**  | Left strip, front to back |
| **`6`**    | None                      |
| **`7–13`** | Right strip, front to back |

| **Transport**               | **How**                                                                                                                                                                                       |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Wired, in the key frame** | SET `0x08` as above, plus payload bytes `378–419` = slots 0–13 and byte `420` = `0x5A` (marker). Frames without the marker leave the side light alone. **Use this one**: it costs no extra 67 ms report. |
| **Wired, alone**            | SET `0x07`, index 0, 1 block, block 0, length 42: slots 0–13                                                                                                                                  |
| **Wireless**                | Command `0x08`, layer 3, not acknowledged. Payload: first slot, then up to 4 × `R G B` (length 13). A frame is 4 packages (first slots 0, 4, 8, 12).                                         |

Like the keys, the stock side light returns about 2 s after the last frame.

```
slots = zeros(42)                                // 14 slots x R G B
slots[3s .. 3s+2] = [R, G, B]                    // s = 0-5 left, 7-13 right

// wired, with the key frame (one report)
usb_set(0x08, key_frame(378) + slots + [0x5A])   // 421 bytes

// wired, alone
usb_set(0x07, slots)

// wireless: 4 stand-alone packages, no ack
for first in [0, 4, 8, 12]:
    payload = [first] + slots[3*first .. 3*first + 11]
    write_output_report(rx_frame(0x08, 1, 0, 3, payload))
    sleep(2 ms)
```

**Detecting the patch.** USB GET `0x88` block 119 returns firmware bytes; ask for at least `0x120` bytes. Counting from the start of the data (after the 8-byte header), bytes `0x5E–0x63` are `64 08 60 03 B4 0F` on patched firmware (zeros on stock), and bytes `0x11B–0x11F` are `MKSD` plus the version (`02`). Don't send SET `0x07` to stock firmware: it blanks every LED for 2 s. Stock firmware ignores wireless layer 3, so that is safe to send unchecked.

```
code = usb_get(0x88, 0x120, first_block = 119)   // firmware 0xEED5-0xEFF4
patched = code[0x5E .. 0x63] == [64 08 60 03 B4 0F]
version = (code[0x11B .. 0x11E] == "MKSD") ? code[0x11F] : 1   // 2 = slots in the key frame
```

---

## Keymap

_Read/Write via commands `0x83` / `0x03` (wired) or `0x41` / `0x01` (wireless), with the layer in the index (wired) or the layer nibble (wireless)._

| **Layer** | **Flash** | **Use**                                                        |
| --------- | --------- | -------------------------------------------------------------- |
| **`0`**   | `0xCC00`  | Base layer                                                     |
| **`1`**   | `0xD000`  | FN layer                                                       |
| **`2`**   | `0xD400`  | Unused (all zero)                                              |
| **`3`**   | `0xD800`  | Tap actions for [Tap/Hold Keys](#taphold-keys); all zero by default |

Each layer is one 512-byte sector: **126 cells × 4 bytes** (504 bytes), then `00 00 00 00 00 00 5a a5`. The cell index is the key's matrix position; for example, Esc is cell 0 and A is cell 9.

Each layer also has a **macOS half** 512 bytes after it (`0xCE00`, `0xD200` …), used when config byte 0 = 1. It can be read (wired GET `0x83`, block 1) but **not written** over the protocol. In it, Win and Alt are swapped, and layer 0 puts the media functions on F1–F12 (the FN layer has plain F-keys there).

Never write a layer above 3: the firmware writes it to a stale flash address.

```
layer = usb_get(0x83, 512, index = L)            // L = 0-3; first_block = 1 reads the macOS half
layer[9*4 .. 9*4+3] = [00 00 00 05]              // A (cell 9) types B
usb_set(0x03, layer, index = L)                  // never L > 3

// wireless: the read is 504 bytes
layer = rx_get(0x41, layer = L) + [00 00 00 00 00 00 5a a5]
rx_set(0x01, layer, layer = L)
```

### Cell Format

| **Byte 0** | **Type**          | **Bytes 1–3**                                                                                                                       |
| ---------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **`00`**   | Normal key        | b1 = modifier mask, b2 = second usage, b3 = HID usage. Modifier-only: `00 mods 00 00`. Esc = `00 00 00 29`.                        |
| **`02`**   | Consumer key      | b2:b3 = 16-bit consumer usage (`02 00 00 e9` = Volume Up)                                                                           |
| **`03`**   | Macro             | b1 = mode, b2 = repeat count, b3 = macro id. See [Binding a Key](#binding-a-key).                                                   |
| **`07`**   | Device function   | b3: `0e` Windows, `0f` macOS, `16` Android, `11` battery display, `05–07` Bluetooth channels, `01` probably Win lock                |
| **`08`**   | Lighting function | b1: `0` effect, `2` colour, `3` brightness, `4` speed. b2: `0` cycle, `1` up/next, `2` down/previous. b3: `0` keys, `1` side light. |
| **`0d`**   | Fn key            | b1 = `0` or `1` picks which layer flag it holds while pressed                                                                       |

**Modifier mask bits:** `01` LCtrl, `02` LShift, `04` LAlt, `08` LGui, `10` RCtrl, `20` RShift, `40` RAlt, `80` RGui.

---

## Macros

_Read/Write via commands `0x85` / `0x05` (wired) or `0x43` / `0x03` (wireless). Lives in flash at `0xDC00–0xEBFF`: 8 blocks of 512 bytes, all zero when no macro is bound. Over the receiver, the block number travels in the layer nibble._

**Never write block 8 or higher**: that is firmware code.

### Store Layout

```
[ directory: N entries × 4 bytes ] [ body 0 ] [ body 1 ] ...
```

| **Field**       | **Size** | **Content**                                |
| --------------- | -------- | ------------------------------------------ |
| **Body offset** | 2 bytes  | Little-endian, from the start of the store |
| **Body length** | 2 bytes  | Little-endian, name included               |

There's no count field: entry 0's offset implies N. Macro id `k` plays the body of entry `k`. The OEM app numbers macros in the order keys use them (layers 0–3, then cells in order).

### Body

```
[nameLen = 2 × chars] [name, UTF-16LE] [event] [event] ...
```

The keyboard skips the name.

### Events (4 Bytes Each)

| **Byte** | **Content**                                                                    |
| -------- | ------------------------------------------------------------------------------ |
| **`0`**  | Bit 7: `1` = release, `0` = press. Bits 4–6: type. Bits 0–3: delay bits 16–19. |
| **`1`**  | Delay bits 8–15                                                                |
| **`2`**  | Delay bits 0–7 (20-bit delay, probably ms; the OEM app caps it at `0xFFFFF`)   |
| **`3`**  | Code                                                                           |

| **Type**  | **Code**                                          |
| --------- | ------------------------------------------------- |
| **`0`**   | Key, HID usage                                    |
| **`1`**   | Modifier, `E0–E7`                                 |
| **`2`**   | Mouse button mask: `1` L, `2` R, `4` M, `8`, `10` |
| **`3–6`** | Wheel / axes; act on press only                   |

Macro keystrokes are sent through the NKRO report (report 4), not the boot report.

### Binding a Key

Set the key's cell to `03 mode count id`:

| **Mode**        | **Behaviour**                                                                      |
| --------------- | ---------------------------------------------------------------------------------- |
| **`1`**         | Play once per press (ignored while already playing)                                |
| **`2`**         | Loop forever, even after release, until another key is pressed                     |
| **`4`**         | Toggle: pressing again stops it. A one-shot macro plays once per tap.              |
| **`0`, others** | Nothing. That is why the stock cells `03 00 00 00` and `03 00 00 01` do nothing.  |

`count` repeats the macro: count 2 typed `abab` from one tap.

### Example

Macro "T" that types `ab`:

```
04 00 13 00                directory: body at 0x0004, 0x13 = 19 bytes long
02 54 00                   name: 2 bytes, "T"
00 00 14 04  80 00 14 04   A press, A release (20 ms each)
00 00 14 05  80 00 14 05   B press, B release
```

With cell 9 (A) set to `03 01 01 00`, every press of A types `ab`.

```
function event(press, type, delay_ms, code):
    return [(press ? 0x00 : 0x80) | (type << 4) | ((delay_ms >> 16) & 0x0F),
            (delay_ms >> 8) & 0xFF, delay_ms & 0xFF, code]

function build_store(macros):                    // macros = [(name, [events])], id = position
    dir = [];  bodies = []
    offset = 4 * len(macros)
    for (name, events) in macros:
        body = [2 * len(name)] + utf16le(name) + concat(events)
        dir    += u16le(offset) + u16le(len(body))
        bodies += body
        offset += len(body)
    return pad_zeros(dir + bodies, 4096)         // 8 blocks

store = build_store([("T", [event(1, 0, 20, 0x04), event(0, 0, 20, 0x04),
                            event(1, 0, 20, 0x05), event(0, 0, 20, 0x05)])])
usb_set(0x05, store)                             // blocks 0-7, never 8+
// wireless: for b in 0 .. 7: rx_set(0x03, store[b*512 .. b*512+511], layer = b)

layer0 = usb_get(0x83, 512, index = 0)
layer0[9*4 .. 9*4+3] = [03, 01, 01, 00]          // A plays macro 0 once
usb_set(0x03, layer0, index = 0)
```

---

## Identity and Power Status

| **Command**                                | **Reply**                                                                          |
| ------------------------------------------ | ---------------------------------------------------------------------------------- |
| **Wired GET `0x82`, index 1**              | 25 bytes `03 00 00 00 00 c6 … 5a a5` (PSD identity). Other indexes: `00 10 00 00`. |
| **Wired GET `0x87`** / **Wireless `0x4A`** | 2 bytes: battery percent, then power flags                                         |

| **Power Flags** | **State**                 | **Lights**                                      |
| --------------- | ------------------------- | ----------------------------------------------- |
| **`0x01`**      | On battery                | As configured                                   |
| **`0x11`**      | Cable in, charge complete | As configured                                   |
| **`0x10`**      | Charging                  | **All off**, except the knob ring breathing red |

```
psd   = usb_get(0x82, 25, index = 1)             // wireless: rx_get(0x05)
p     = usb_get(0x87, 2, index = 2)              // wireless: rx_get(0x4A)
battery_percent = p[0]
charging        = (p[1] == 0x10)                 // keys dark while true
```

### Identifying the MK75

Nothing in the protocol names the model:

- **VID:PID `258a:010c`** is shared with the AULA F75 and AU75 (same hardware).
- **The USB product string**, "BY Tech Gaming Keyboard", is generic.
- **The PSD bytes** from GET `0x82` aren't understood, and haven't been compared with another model.
- **The receiver**, `3554:fa09`, is a generic CompX dongle.

The firmware holds the Bluetooth names in plain text: `MK75 3.0` at flash `0xEC1F` and `MK75 5.0` at `0xEC27`, back to back. Wired GET `0x88` reads flash: block `b` returns code from `0x00D5 + b × 0x200`, with no bounds check and no root needed. Block 117 starts at `0xEAD5`, so the names sit at offset `0x14A` of its data.

```
code    = usb_get(0x88, 0x15A, first_block = 117)  // flash 0xEAD5-0xEC2E
is_mk75 = code[0x14A .. 0x159] == "MK75 3.0MK75 5.0"
```

Limits:

- **Not yet tried on the keyboard.** The address comes from the firmware dump; GET `0x88` itself is verified against that dump.
- **Wireless can't do this.** The receiver has no firmware read. The best check there is that config, palette and keymap reads come back in the layout described here.
- **Another firmware build may move the string**, and then a real MK75 fails the check. A rebranded F75 or AU75 most likely carries its own name here, but no such firmware has been compared.

---

## Write Rules

Where each block lives in flash is given in its section; the full flash map is in [FIRMWARE.md](FIRMWARE.md#flash-layout).

**Every SET rewrites a whole 512-byte sector.** A shorter payload doesn't leave the rest alone: the rest is filled with leftovers from an earlier transfer. So:

- Send full 512-byte payloads for keymap, macros, per-key colours and palette. Read-modify-write when only part changes.
- The config block is the exception: send 128 bytes.
- Never write a keymap layer above 3, or a macro block of 8 or higher.
- Never write a config block that lacks `ff ff` at bytes 56–57.

---

## Power, Sleep and Charging Quirks

Each of these looked like a broken write at first. **Check the power status before blaming a write.**

- **Charging turns the backlight off.** While charging (power flags `0x10`), every key is dark whatever the config says. Unplugging relights it at once. Direct mode still works while charging.
- **Sleep.** In wireless modes, the backlight and link go off after `byte 24 × 30 s` without key presses. Mouse activity doesn't count. A key press wakes it. `00` never sleeps.
- **A sleeping keyboard returns a mostly-zero config.** It keeps `5a a5` at bytes 126–127 but lacks `ff ff` at 56–57. Writing that block back wipes the live config, and the keyboard stays dark. Always check bytes 56–57 before writing.
