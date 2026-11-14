
**Note:** This is the checklist of everything a configuration tool can do with the R1 NK, with the command, the memory address, the allowed values and how far each item was checked. The details are in [PROTOCOL.md](PROTOCOL.md) and [FIRMWARE.md](FIRMWARE.md). All checks were done on one unit (mouse firmware 1.0.12, receiver 1.0.20) through the receiver, with the mouse awake.

Status values:

- **Verified (write)**: written, read back, memory compared, and restored.
- **Verified (read)**: read on the unit; never written.
- **Host only**: the layout is how a configuration tool builds it; the mouse was not asked.
- **Untested**: known command, not tried.
- **Not on this model**: the vendor's model table switches it off, or the mouse reports it unsupported.

---

## Status and Identity

| **Feature**              | **Command**   | **Payload / value**                                       | **Status**         |
| ------------------------ | ------------- | --------------------------------------------------------- | ------------------ |
| **Battery level**        | `0x07`        | Percent, then millivolts (16-bit little-endian)           | Verified (read)    |
| **Charging state**       | `0x0F`        | `1` = charging, then millivolts                           | Verified (read)    |
| **Charge time left**     | `0xAE`        | 32-bit little-endian; `0` when not charging               | Verified (read)    |
| **Link type**            | `0x1A`        | Mouse answers `2`; the receiver answers `0` for itself    | Verified (read)    |
| **Mouse firmware**       | `0x1C`        | major, minor, patch (`01 00 0c` = 1.0.12)                 | Verified (read)    |
| **Receiver firmware**    | `0x88`        | Same layout (`01 00 14` = 1.0.20)                         | Verified (read)    |
| **Model identity**       | `0x4A`        | cid `2`, mid `8` (32-bit)                                 | Verified (read)    |
| **Receiver link status** | `0x81`, `0x84`| `1` when the mouse is linked and paired                   | Verified (read)    |
| **Mouse online**         | `0x23`        | Meaning of the extra bytes unknown                        | Verified (read)    |
| **Pair / unpair**        | `0x82`, `0x83`| Starts pairing, clears the pairing                        | Untested           |
| **Optional features**    | `0xB1`        | Bit mask; this mouse reports `0`                          | Verified (read)    |
| **Factory reset**        | `0x13`        | Restores settings                                         | Untested           |

---

## Sensor and Movement

| **Feature**              | **Command** | **Values**                                                            | **Memory**        | **Status**                    |
| ------------------------ | ----------- | --------------------------------------------------------------------- | ----------------- | ----------------------------- |
| **Report rate**          | `0x01`      | 125, 250, 500, 1000 Hz (codes `3`, `2`, `1`, `0`)                     | `0x0043`          | Verified (write: 500 ⇄ 1000)  |
| **Lift-off distance**    | `0x03`      | 1 mm or 2 mm: first argument `height` (`0x0045`), then mm − 1 (`0x0046`) | `0x0045–0x0046` | Verified (write: 2 ⇄ 1 mm, both bytes) |
| **Motion sync**          | `0x0D`      | on / off                                                              | `0x0047`          | Verified (write)              |
| **Linear correction**    | `0x0B`      | on / off                                                              | `0x0048`          | Verified (write)              |
| **Ripple control**       | `0x0C`      | on / off                                                              | `0x0049`          | Verified (write)              |
| **Button debounce**      | `0x16`      | 1, 2, 4, 8, 15, 20 ms (0 ms is not offered for this model)            | `0x0051`          | Verified (write: 4 ⇄ 8)       |
| **Sensor sleep time**    | `0x15`      | 30, 60, 120, 180, 300, 1200, 1500, 1800 s (16-bit little-endian)       | `0x004F–0x0050`   | Verified (write: 300, 600, 30) |
| **Sensor mode**          | `0x1F`      | `00` basic, `04` competitive; "competitive max" is not on this model   | `0x004A`          | Verified (write: `04`, read back, restored) |
| **Performance mode**     | `0x25`      | Used instead of `0x1F` only by mice that report the 13K-fps feature; acknowledged and ignored here | — | Verified (no effect)          |
| **Bunny hop**            | `0x22`      | Enable and a time in ms; a write read back correctly                  | `0x0A86–0x0A88` | Verified (write: on, then off) |
| **Long-range mode**      | `0x1B`      | —                                                                     | —                 | Not on this model             |
| **Sensor angle**         | `0x21`      | —                                                                     | —                 | Not on this model             |
| **Sensor centre point**  | `0xAA`, `0xB7` | —                                                                  | —                 | Not on this model             |
| **Dynamic sensitivity**  | `0xAB`, `0xAC` | —                                                                  | —                 | Not on this model             |
| **Scroll reverse**       | `0x27`      | —                                                                     | —                 | Not on this model (`0xB1`)    |
| **Turn around**          | `0xBA`      | —                                                                     | —                 | Not on this model (`0xB1`)    |

---

## DPI

| **Feature**              | **Command** | **Values**                                                                                    | **Memory**               | **Status**                        |
| ------------------------ | ----------- | --------------------------------------------------------------------------------------------- | ------------------------ | --------------------------------- |
| **Stage table**          | `0x17` read | Up to 8 stages; 4 in use (400, 800, 1600, 3200)                                               | `0x0003 + 8n`            | Verified (read)                   |
| **Stage value**          | `0x02`      | 200 to 18000 DPI in steps of 50 (sensor table; X and Y always the same)                       | `0x0003 + 8n`            | Verified (write: stage 3 ⇄ 3250)  |
| **Stage colour**         | `0x02`      | Red, green, blue per stage, stored blue first                                                 | `0x0003 + 8n + 4`        | Verified (write, with the value)  |
| **Add or delete stage**  | `0x02`      | Add = write the next index (stage 4 = 5000 DPI went to `0x0023`); delete = index followed by nine zero bytes (clears the stage). Table size at `0x0002` stays 8 | `0x0003 + 8n` | Verified (write, memory diffed, restored) |
| **Current stage**        | `0x02`      | Last argument `1` on a write makes that stage current; the write echoes back and memory `0x0001` changes (2 → 1) | `0x0001` | Verified (write, memory diffed, restored) |
| **DPI change event**     | unsolicited | `73 01 05 00` then the DPI (16-bit) twice                                                     | —                        | Verified (read)                   |

---

## Light

| **Feature**              | **Command** | **Values**                                                                    | **Memory**        | **Status**                    |
| ------------------------ | ----------- | ----------------------------------------------------------------------------- | ----------------- | ----------------------------- |
| **Mode**                 | `0x14`      | off (`0`), breathing (`1`), steady (`2`)                                      | `0x004C`          | Verified (write)              |
| **Brightness**           | `0x14`      | low `0x55`, medium `0xAA`, high `0xFF` offered; any byte is stored             | `0x004D`          | Verified (write, four values) |
| **Speed**                | `0x14`      | slow `0x0A`, medium `0x0F`, fast `0x14`                                       | `0x004E`          | Verified (write)              |
| **Per-stage colour**     | DPI stage   | One colour per DPI stage, shown by the DPI light                              | `0x0003 + 8n + 4` | Verified (write)              |
| **Receiver light**       | `0x85`, `0x86` | Mode, brightness, speed, colour, sleep                                     | —                 | Not on this model (reads zeros) |

---

## Buttons

Six entries, in this order: left, right, middle, back, forward, DPI button. The wheel and the sensor are not remappable. Memory `0x0052`, five bytes each.

| **Binding**              | **Wire (after index)**                         | **Status**                                              |
| ------------------------ | ---------------------------------------------- | ------------------------------------------------------- |
| **Default**              | `01 00 <own value> 00`, or class `0`           | Verified (write)                                        |
| **Another mouse button** | `01 00 <value> 00` (left `0`, right `1`, middle `2`, back `3`, forward `4`) | Verified (write)                     |
| **Keyboard key**         | `03 <modifiers> <usage> 00`                    | Verified (write)                                        |
| **System key**           | `02 00 <code> <code>`                          | Verified (write, binding only)                          |
| **Macro**                | `04 00 <macro id> 00`                          | Verified (write)                                        |
| **Fire key**             | `05 <clicks> <interval lo> <interval hi>`      | Verified (write, binding only; firing not tried)        |
| **DPI cycle, up, down**  | classes `10`, `11`, `12`                       | Verified (write, binding only)                          |
| **Scroll up/down/left/right** | classes `13` to `16`                      | Verified (write, binding only)                          |
| **Profile buttons**       | classes `17` to `21`                           | Binding verified; pressed: `17` previous, `18`–`20` jump to 1–3, `21` next; each press sends an event |
| **Disabled**             | class `255`                                    | Verified (write, binding only)                          |
| **Turn around**          | class `6`                                      | Not on this model                                       |

---

## Macros

| **Feature**              | **How**                                                                                          | **Status**                       |
| ------------------------ | ------------------------------------------------------------------------------------------------ | -------------------------------- |
| **Slots**                | Six, one per button, at `0x0071 + 430 × button` (`0x057B` back, `0x0729` forward); up to 70 actions each; the slot comes from the key index in the write, the id is only a label | Verified (read, write, played) |
| **Key and modifier actions** | key type `0`, down or up, any keyboard usage                                                 | Verified (write, played)         |
| **Chords**               | One action per key, ordered presses and releases                                                  | Verified (played)                |
| **Delay**                | Hold time per action in ms (16-bit); only short values were played                               | Verified (played, 30 and 40 ms; 70 actions in 2.2 s) |
| **Mouse button action**  | key type `1`, bit mask in the code                                                                | Verified (played)                |
| **Scroll action**        | key type `2`, code `01` up or `FF` down                                                           | Verified (played)                |
| **Repeat modes**         | `1` hold, `2` until any key, `3` until the same key, `4` loop N times                             | Verified (played, all four)      |
| **Read back**            | Header, six-byte records and the footer, with `0x17`                                              | Verified (read)                  |

---

## Profiles, Updates and Events

| **Feature**              | **Notes**                                                                                           | **Status**              |
| ------------------------ | --------------------------------------------------------------------------------------------------- | ----------------------- |
| **Profile switch**       | `0x0A` selects a profile; each profile has its own settings and its own macros. Profiles `0` to `3` exist; `4` is ignored. The active profile is read from the config block (byte 0). Profiles `1` to `3` were each selected and profile `0` restored. | Verified (write) |
| **Firmware update**      | In-band over the `0xFFB1` and `0xFFB3` interfaces; no firmware is published for this mouse          | Host only (never run)   |
| **Receiver update**      | Same interfaces on the receiver; receiver 1.0.20 is available and was installed with another tool   | Host only (never run)   |
| **Sleep event**          | The mouse does not send one                                                                         | Verified (read)         |
| **Wake event**           | The mouse does not send one: a 420 s idle then a move gave no frame on the settings channel         | Verified (read)         |

---

## Not Part of the Mouse

Several things a configuration tool offers are not stored on the mouse: saved and shared configs, preset libraries, themes and wallpapers, account sign-in, feedback and usage reporting, and the music-synced lighting effects. They are described in [CONFIGS.md](CONFIGS.md) where they affect what can be saved and loaded.
