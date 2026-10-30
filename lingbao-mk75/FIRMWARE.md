
**Warning:** Writing firmware can leave the keyboard unusable. Everything here keeps the ISP bootloader intact and was done over USB only, without opening the case. Keep a full dump of your own keyboard before writing anything.

The stock firmware is Keil C51 code for an 8051. It was dumped over the ISP bootloader, read in Ghidra, and turned back into assembler source that rebuilds the stock image byte for byte. On top of that source, small patches add features. All addresses below are flash (code) addresses unless they say XRAM or IRAM. The tools mentioned here are in [tools/](tools/README.md).

**The firmware can only be read or written over the USB cable.** The ISP bootloader is a USB device (`0603:1020`), and the USB firmware read (GET `0x88`) has no wireless form. Over 2.4 GHz the receiver only passes protocol commands. Bluetooth hasn't been looked at.

---

## Hardware

| **Part**            | **Details**                                                                                                                         |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **MCU**             | Sinowealth SH68F90 (BYK916 family), 8051 core, 64 KB flash                                                                         |
| **Flash split**     | `0x0000–0xEFFF` firmware (60 KB), `0xF000–0xFFFF` ISP bootloader (4 KB)                                                             |
| **IRAM**            | 256 bytes. The stack starts at `0x79`.                                                                                              |
| **XRAM**            | 4 KB at `0x0000–0x0FFF`. Start-up clears it, and IRAM too.                                                                          |
| **Peripherals**     | XSFRs at XRAM `0xFFxx` (USB, PWM). Bit `0x86.0` selects the XSFR page.                                                             |
| **Radio**           | Almost certainly a Beken BK3632. The OEM app's receiver class is `CDev3632`, the firmware reads 0x17-byte packets from it (`0x4A81`), and the open AULA F75 firmware drives a BK3632. |
| **Firmware**        | Keil C51. Reset vector: `LJMP 0x9B52`.                                                                                              |
| **Same product as** | AULA F75 (and AU75). `sinowisp` lists the F75 as `aula-f75`, with exactly `258a:010c`.                                             |
| **Open firmware**   | An SMK fork for the AULA F75 exists (`github.com/Thaolia/smk_aulaF75`, one maintainer, partly unverified). Not tried on the MK75.  |

---

## Flash Layout

Settings live in the same flash as the code, in 512-byte sectors. Each protocol block is an exact copy of one sector.

| **Address**                                | **Content**                                                                                                 |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| **`0x0000–0xB1FF`**                        | Firmware code, with data inside: USB/HID descriptors and strings (`0x591A–0x5B4F`), USB request handler pointers (`0x5AD6`), colour and LED tables (`0x27C5–0x2DFF`) |
| **`0xB200`**                               | Palette copy (probably the defaults). Its tail at `0xB3E3` holds the PSD identity bytes that GET `0x82` index 1 returns. |
| **`0xB400`, `0xB800`**                     | Keymap layer 0 and 1 copies                                                                                 |
| **`0xBC00–0xC3FF`**                        | Blank layer copies                                                                                          |
| **`0xC400`**                               | Factory default config: Neon stream, side light rainbow wave, debounce 2, sleep 60 s, knob in gaming mode. The breath table (128 steps, 0 → 255 → 0) follows at `0xC480`. |
| **`0xC600`**                               | Config (live)                                                                                               |
| **`0xC800`**                               | Palette (live)                                                                                              |
| **`0xCA00`**                               | Per-key colours (live)                                                                                      |
| **`0xCC00`, `0xD000`, `0xD400`, `0xD800`** | Keymap layers 0–3 (live), 1 KB each: Windows half, then macOS half                                         |
| **`0xDC00–0xEBFF`**                        | Macro store, 8 sectors                                                                                      |
| **`0xEC00–0xEF32`**                        | Firmware code. `0xEC1F`: Bluetooth names `MK75 3.0`, `MK75 5.0`. `0xEEC3`: jump to ISP.                     |
| **`0xEF33–0xEFF7`**                        | Unused (zeros): the only free flash, 197 bytes                                                              |
| **`0xEFF8–0xEFFF`**                        | Boot entry: `0xEFFB` holds an `LJMP` to the firmware, written by the ISP tool                               |
| **`0xF000–0xFFFF`**                        | ISP bootloader                                                                                              |

Every protocol write erases one 512-byte sector (`0xAE63`) and programs 512 bytes from the receive buffer (`0xA27B`). The rules that follow from this are in [PROTOCOL.md](PROTOCOL.md#write-rules).

---

## Memory Map

### XRAM

| **Address**         | **Content**                                                                                                      |
| ------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **`0x00A3`**        | Radio packet: command `0x00A5`, packages `0x00A6`, index `0x00A7`, layer/length `0x00A8`, payload from `0x00A9` |
| **`0x00D5`**        | Live LED buffer: 126 × `R G B` (378 bytes). USB `0x08` writes here directly.                                     |
| **`0x0265`**        | Transfer: total blocks                                                                                           |
| **`0x028C`**        | Live config: byte `n` at `0x028C + n` (byte 14, connection mode, is `0x029A`)                                    |
| **`0x030C`**        | Transfer: index / layer                                                                                          |
| **`0x030D–0x030E`** | Transfer: length                                                                                                 |
| **`0x0328`**        | Side-light entries: 6 bytes per LED-matrix column, at `0x0328 + column × 6`                                      |
| **`0x0748–0x074D`** | Knob light entry, filled by the power code                                                                       |
| **`0x0892`**        | Active effect (byte 10, or byte 11 while byte 9 = 1)                                                             |
| **`0x098E`**        | LED-scan pause timer                                                                                             |
| **`0x09B7`**        | USB receive buffer (every command but `0x08`). Over the radio: a ring of three 200-byte banks for direct-mode records. |
| **`0x0C2D`**        | Battery value                                                                                                    |
| **`0x0D0B`**        | Transfer: block number                                                                                           |
| **`0x0D0F`**        | Cell type of the key just used (sent on input report 3)                                                          |
| **`0x0D28 + key`**  | Tap/hold tick counters                                                                                           |
| **`0x0DAA`**        | Direct-mode timeout counter                                                                                      |
| **`0x0E51`**        | Side-light breathing phase                                                                                       |

### IRAM and Bits

| **Address**             | **Content**                                                                     |
| ----------------------- | ------------------------------------------------------------------------------- |
| **`0x17–0x1E`**         | USB report header: report ID, command (`0x18`), index, 0, blocks, block, length |
| **Bit `0x2A`**          | LED-scan pause (set before flash writes)                                        |
| **Bit `0x3D`**          | Key lock (config byte 16)                                                       |
| **Bit `0x3E`**          | Win-key lock (config byte 15)                                                   |
| **Bits `0x42`, `0x43`** | Direct mode on. `0x43` clears when the timeout runs out.                        |
| **Bit `0x48`**          | Unused by stock code (IRAM `0x29.0`). The side-light patch uses it.             |
| **Bit `0x53`**          | Not charging (pin P3.6 low, debounced)                                          |
| **Bit `0x54`**          | Side-light renderer off                                                         |
| **Bit `0x60`**          | USB power present (pin P3.4, debounced in `0xA188`)                             |

### Interrupts

| **Vector** | **Handler** | **Job**                                                                                   |
| ---------- | ----------- | ----------------------------------------------------------------------------------------- |
| **`0x43`** | `0x6207`    | Matrix and LED scan: up to 20 columns (column in XRAM `0x028A`), loads the PWM registers |
| **`0x63`** | `0x8CA1`    | 1 ms tick: seconds for the sleep timer, 21 ms units for tap/hold                          |

---

## Code Map

| **Address**             | **Routine**                                                                                                  |
| ----------------------- | ------------------------------------------------------------------------------------------------------------ |
| **`0x9B52`**            | Reset / start-up. The Keil init table at `0x9FCF` only sets XRAM (`0x08C0`, `0x0C2D`, `0x0DD1` + 126 bytes). |
| **`0x0200`**            | Report 5 SET: `05 75` → `0xEEC3` (ISP entry)                                                                 |
| **`0x02D8`**            | Report 6 SET: header into IRAM `0x17–0x1E`, payload to `0x09B7` (or `0x00D5` for `0x08`, at most 378 bytes)  |
| **`0x0442–0x0470`**     | Connection-mode check and LED-scan pause before every SET                                                    |
| **`0x0473`**            | SET dispatcher; table `0x0495`, one `LJMP` per command `0x03–0x0A`                                           |
| **`0x04AD`**            | SET `0x03` keymap                                                                                            |
| **`0x04DF` → `0xB1F0`** | SET `0x04` config, then apply                                                                                |
| **`0x04E5`**            | SET `0x05` macro                                                                                             |
| **`0x0505`**            | SET `0x06` per-key colours                                                                                   |
| **`0x056E`**            | SET `0x08` direct mode                                                                                       |
| **`0x0584`**            | SET `0x0A` palette                                                                                           |
| **`0x05A8`**            | SET `0xAA` echo → USB IN task `0x6C23`                                                                       |
| **`0x05E9`**            | Bare `RET`: the slot for `0x07` and `0x09`                                                                   |
| **`0x53EA`**            | GET_REPORT for feature report 6; dispatcher `0x5506`, table `0x5523` for `0x82–0x8A`                         |
| **`0x1E6F`**            | Radio packet handler. `0x2058`: branch for command `0x08`. `0x2075–0x209F`: LED-scan pause. `0x20A8`: case table. |
| **`0x2607`**            | Radio `0x08` by layer: layer 2 → fill (`0x272A`), layer 1 → record ring (`0x2618`), others → `0x27BC`        |
| **`0x4A81`**            | Read a packet from the radio                                                                                 |
| **`0x1108`**            | Lighting task. `0x11B9–0x13EA`: radio direct records. `0x1144`: per-key brightness.                          |
| **`0x1BBE`**            | Effect dispatcher on XRAM `0x0892`: 18-slot table (effects 0–17), exit `0x1E6E`                              |
| **`0x3F00`**            | Side-light renderer                                                                                          |
| **`0xA8C8`**            | Load a side-light entry into the PWM registers                                                               |
| **`0x3108`**            | Key lookup (picks the keymap page from config bytes 0 and 27)                                                |
| **`0x5108`**            | Macro player; `0x535C` event decoder, `0x9BEC` key events                                                    |
| **`0xA3E2`**            | Macro key binding (modes 1, 2, 4)                                                                            |
| **`0x9970`**            | Slow loop: direct-mode timeout, sleep timer (`0x99BE`), locks                                                |
| **`0xA1F8`**            | Config loader (checks `5a a5`)                                                                               |
| **`0xA260`**            | Picks the active effect                                                                                      |
| **`0xAA8E`**            | Whole-sector rewrite: erase `0xAE63`, program `0xA27B`, called through `0xEDA9`                              |
| **`0xEED9`**            | Drive the LED lines off                                                                                      |
| **`0xEEC3`**            | ISP entry: `CLR EA; MOV B,#0xA5; MOV A,#0x5A; LJMP 0xFF00`                                                   |

### What the Firmware Doesn't Do

- **Effects 6, 14 and 18 are missing.** Table slots 6 and 14 point to the exit, and 18 lies past the end of the table. The OEM app offers them anyway.
- **Two per-key modes are hidden:** effect 32 (`0x1E57`) and 38 (`0x1DB1`). How they differ isn't known.
- **GETs don't check bounds.** The block number adds `block × 0x200` to the start address.
- **GET `0x88` reads code, not XRAM.** It was probably meant to return the live LED buffer at XRAM `0x00D5`, but it reads flash from `0x00D5`. That is why the firmware can be read without ISP (below).
- **The knob light is not an LED in the map.** It is a red-only indicator driven by the power code (`0x05EA` charging breath, `0x07C2` low-battery blink).

---

## Bootloader and ISP

| **Step**         | **Details**                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Entering ISP** | Feature report 5 `05 75 00 00 00 00`. The keyboard re-enumerates as `0603:1020` "SINO WEALTH Gaming KB" (root-only on Linux). |
| **Power-on**     | The bootloader (`0xF000`) boots the firmware if `0xEFFB` holds `0x02` (a stored `LJMP`). Otherwise it stays in ISP.            |
| **`0xFF00`**     | Enters ISP only with A = `5A` and B = `A5`.                                                                                    |
| **Key combo**    | None found.                                                                                                                    |

A failed or partial write leaves `0xEFFB ≠ 0x02`, so the keyboard stays in ISP and can be written again over USB. **A firmware that boots but can't reach `0xFF00`** (no `05 75` handler, no key combo) **can only be recovered through the chip's debug pins.**

---

## Reading the Firmware

### Over ISP (Root)

```
sudo sinowisp read -d aula-f75 -s full --format bin dump.bin
```

`sinowisp` 2.1.0 and its predecessor `sinowealth-kb-tool` (`read --device aula-f75 --section full`) read byte for byte the same. The ISP read masks bytes `0x0001–0x0002` and the boot entry around `0xEFFB`, so those don't match flash exactly.

| **Dump**                   | **MD5**                            | **Notes**                                                        |
| -------------------------- | ---------------------------------- | ---------------------------------------------------------------- |
| **First dump, 2026-10-28** | `54bf275ac3a36c5e878023b977a8be83` | 65536 bytes                                                      |
| **2026-10-30**             | `496cb35723c2be5c64d404c9b0c39430` | Only the settings sectors (`0xC600`, `0xC800`, `0xCA00`) differ |

Settings differ from keyboard to keyboard, so your dump won't match these.

### Over USB (No Root)

GET `0x88` returns flash from `0x00D5 + block × 0x200`. It works over the cable only: the receiver has no firmware read. Blocks 0, 1 and 119 have been checked against the dump; the rest go through the same code. The 16-bit pointer wraps, so the last block also reaches `0x0000–0x00D4`.

**A full dump this way has not been run yet.** So it isn't confirmed that all 128 blocks read back correctly, or whether the read reaches the bootloader area.

```
image = zeros(0x10000)
for b in 0 .. 127:
    data = usb_get(0x88, 512, first_block = b)       // see PROTOCOL.md; tools/mk75dump88.py does this
    for i in 0 .. 511:
        image[(0x00D5 + b * 0x200 + i) & 0xFFFF] = data[i]
```

---

## Writing the Firmware

These steps were verified on 2026-10-30, by writing the unchanged image back and then an image rebuilt from source. Both times the keyboard re-enumerated normally and read back identical.

1. Make a fresh full dump, so the settings sectors are current.
2. Cut it to exactly `0xF000` bytes (firmware only, no bootloader).
3. Write it.

```
head -c 61440 dump.bin > image.bin
sudo sinowisp write -d aula-f75 --format bin image.bin
```

`sinowisp` erases `0x0000–0xEFFF`, writes, reads back and verifies. Only after the verify passes does it send "enable firmware", which restores the boot entry at `0xEFFB`. The bootloader is never touched.

- **The file must be exactly `0xF000` bytes.** A shorter one is padded with zeros after a prompt. A longer one isn't rejected.
- **The write also rewrites the settings sectors from the file.** An old dump brings back old settings.
- **Keep your stock dump** to restore with the same command.

---

## Rebuilding from Source

`tools/mk75asm.py` turns a dump into `sdas8051` source and builds it again with SDCC 4.5.0 (`sdas8051` + `sdld`). The rebuilt image matches the dump: **0 bytes differ**. That is 24 785 instructions and 43 KB of code. The source isn't published, because it is vendor code.

```
head -c 61440 dump.bin > stock.bin                            # firmware only
python3 tools/mk75asm.py dis stock.bin mk75.asm               # source of 0x0000–0xEFFF
python3 tools/mk75asm.py build mk75.asm mk75.bin stock.bin    # assemble, link, compare
```

How code is told apart from data:

- **Recursive descent** from the reset and interrupt vectors, plus a list of seed addresses.
- **Keil patterns:**
  - `?C?CCASE` case tables after `LCALL 0x4C7B`: `DB hi, lo, value` …, then `DB 0, 0` and the default address.
  - The inline 4-byte constant helper at `0x4C3E`.
  - `JMP @A+DPTR` tables of `LJMP`s, indexed with `MUL AB` by 3 or with `MOV R0,A` / `ADD A,R0` twice. The bound is the preceding `CJNE A,#n`.
- **A hand-made list** for the 21 generic code pointers at `0x5AD6`. They are probably the USB request handlers.

Every branch, call, case and pointer target becomes a label. `MOV DPTR,#imm` stays numeric, because 190 of them point into flash. So **code can't be inserted**: a change has to hook into existing code and jump to new code in the free space.

---

## Patching

```
python3 tools/mk75asm.py patch mk75.asm patch.asm out.asm out.bin stock.bin
```

A patch file has two parts:

| **Marker**            | **Meaning**                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------ |
| **`;@site ADDR LEN`** | Replace the stock instructions at `ADDR` (whole instructions, `LEN` bytes in total) with the lines below it |
| **`;@code`**          | Everything after it is new code, placed with `.org` in the free space                                        |

The tool **refuses** any change outside the sites and `0xEF33–0xEFF7`, and any byte in the boot entry `0xEFF8–0xEFFF`.

Rules that keep a patched keyboard recoverable over USB:

- Leave reset (`0x9B52`), start-up, USB, the interrupt vectors and the report-5 ISP handler alone.
- Run new code only when a command arrives. Hooks in paths that always run must behave exactly like the stock code while idle.
- Never write flash from new code.
- Restore by writing the stock dump back.

---

## Side-Light Direct Patch

Verified by eye on the cable and over 2.4 GHz (2026-10-30). Stock firmware only lets the side light run its own modes (config bytes 18–21). The patch lets the host set each side LED, the way direct mode does for the keys. How a host uses it is in [PROTOCOL.md](PROTOCOL.md#side-light).

It adds 178 bytes of new code at `0xEF33–0xEFE4` and a 5-byte version tag at `0xEFF0–0xEFF4`, leaving 14 of the 197 free bytes unused (`0xEFE5–0xEFEF`, `0xEFF5–0xEFF7`). It rewrites 18 bytes at 6 sites, which jump into that code. Against stock, 190 bytes differ: 176 in the free space (the other 7 new bytes are zeros, the same as before) and 14 at the sites (4 site bytes keep their stock value, such as the `LJMP` opcodes).

| **Site**     | **Stock**                                        | **Patched**                                                   |
| ------------ | ------------------------------------------------ | ------------------------------------------------------------- |
| **`0x03A1`** | `0x08` payload bytes from 378 on are dropped     | They go into the receive buffer, like other commands          |
| **`0x044E`** | `xrl a,#0x08` / `jz`                             | `0x07` skips the LED-scan pause, like `0x08`                  |
| **`0x04A1`** | SET slot for `0x07`: `RET`                       | Side-light handler                                            |
| **`0x04A4`** | SET slot for `0x08`: direct handler              | Direct handler, then the side slots if the frame carries them |
| **`0x2615`** | Radio `0x08`, layers other than 1 and 2: ignored | Layer 3: side-light handler                                   |
| **`0x3F00`** | Side-light renderer entry                        | Gate: skip the renderer while side direct holds the slots     |

### How the Side Light Is Driven

The side LEDs share the key LEDs' multiplex. Each matrix column has one RGB entry at XRAM `0x0328 + column × 6`. The scan interrupt loads the entry of the current column into the PWM registers with `0xA8C8`:

| **Channel** | **PWM Registers (high / low)** |
| ----------- | ------------------------------ |
| **R**       | `0xFFFA` / `0xFFE2`            |
| **G**       | `0xFFFB` / `0xFFE3`            |
| **B**       | `0xFFFC` / `0xFFE4`            |

Each channel is stored as a 16-bit big-endian value `c × 4 + base`, with base `0xC6`, `0xC7`, `0xC8` (from `0x27D7`). `c = 0` is off. The stock renderer fills columns 0–6 and 9–15 and caps `c` at 80 (brightness table `0x27DB`: `00 14 28 3c 50`). **`c = 255` is clearly brighter and works**, so the patch takes the full 8-bit range.

| **Slot**   | **Column** | **LED**                             |
| ---------- | ---------- | ----------------------------------- |
| **`0–5`**  | 0–5        | Left strip, front to back (6 LEDs)  |
| **`6`**    | 6          | None                                |
| **`7–13`** | 9–15       | Right strip, front to back (7 LEDs) |

The left strip really has one LED fewer: its LEDs sit further apart.

### How Direct Mode Ends

All three commands start direct mode the way USB `0x08` does: bits `0x42`/`0x43` set, timeout `0x0DAA` = 0. They also set bit `0x48`. The renderer gate skips the stock renderer while `0x48` and `0x43` are both set. About 2 s after the last frame the slow loop clears `0x43`, the gate drops `0x48`, and the stock side light returns. The keys keep their stock effect unless `0x08` frames come too.

### Versions

| **Version** | **What It Adds**                                                                                                                                         |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **None**    | First build: SET `0x07` only, no version tag. It left out the `0x044E` site, so every frame blanked all LEDs for 2 s. That is how the LED-scan pause was found. |
| **1**       | SET `0x07` and radio layer 3, with the pause fixed                                                                                                       |
| **2**       | Side slots also ride in the `0x08` key frame (bytes 378–419, marker `0x5A` at 420). Every USB SET costs about 67 ms, so this keeps direct mode at one report per frame. Verified: 90 frames at 67.0 ms each, side strips blue. |

**Detecting the patch:** `0xEF33–0xEF38` holds `64 08 60 03 B4 0F` (zeros on stock), and `0xEFF0` holds `MKSD` plus the version. A host reads both with GET `0x88` block 119 (see [PROTOCOL.md](PROTOCOL.md#side-light)).

### Source

The patch source is [`tools/patches/side_direct.asm`](tools/patches/side_direct.asm) (version 2). Its header comment repeats the slot layout, the commands and the flag use described above, and every hook and routine is commented.

### Building and Flashing It

```
sudo sinowisp read -d aula-f75 -s full --format bin dump.bin
head -c 61440 dump.bin > stock.bin                                          # keep this to restore
python3 tools/mk75asm.py dis stock.bin mk75.asm
python3 tools/mk75asm.py patch mk75.asm tools/patches/side_direct.asm mk75-side.asm mk75-side.bin stock.bin
sudo sinowisp write -d aula-f75 --format bin mk75-side.bin
```

To undo it, write `stock.bin` back the same way.

---

## Open Questions

- **Config bytes 1–2, 4, 13 and 17:** no reader found (17 sets bit `0x3F`, which nothing reads).
- **Effects 32 and 38:** they behave the same in every test, but their handlers differ.
- **Input report 3 with `state` 2** (`0xA52B`): never seen.
- **The code that reads the pointer table at `0x5AD6`** hasn't been found.
- **A full dump over GET `0x88`:** never run. Whether all blocks match an ISP dump, and whether the read reaches the bootloader area, is unknown.
- **The pin map** (matrix, LEDs, knob, radio SPI, mode switch) hasn't been extracted. A port of open firmware needs it.
