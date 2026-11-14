
**Note:** Tested on one VXE R1 NK (mouse firmware 1.0.12, receiver firmware 1.0.17 and later 1.0.20). Each entry says how far it was tested: **Cable** means exercised over the USB cable, **Receiver** means exercised through the NearLink receiver (writes were read back), **Untested** means the layout is known but was never run on this unit. Most receiver writes below were run and restored in the later sessions with memory snapshots, including DPI stage add, delete and current-stage writes. Other ATK and VXE mice use the same command layer with different numbers; those were not tested.

The mouse has **one command layer**. Over the cable the host talks to the mouse directly, with 63-byte reports on report ID 8. Over NearLink the host talks to the receiver with the same reports. The receiver answers its own commands and forwards mouse commands over the air. The two paths differ only in one byte (the target) and in how patient the host has to be: a sleeping mouse does not answer. Settings live in the mouse's own memory.

---

## USB Interfaces (`373b:124c` "ATK VXE R1 NK")

The mouse exposes three HID interfaces. Only the vendor channel on report 8 carries the settings protocol; the other two vendor pipes are for firmware updates.

| **Interface** | **Report ID** | **Direction** | **Payload Size** | **Usage Page**            | **Usage**                 | **Description & Purpose**                                                              |
| ------------- | ------------- | ------------- | ---------------- | ------------------------- | ------------------------- | -------------------------------------------------------------------------------------- |
| **A**         | 2             | IN / OUT      | 8 Bytes          | Generic Desktop (`0x01`)  | Keyboard (`0x06`)         | **Keyboard**: modifiers, LED output bits, 6 keys. Used for keyboard bindings.          |
| **A**         | 1             | IN            | 7 Bytes          | Generic Desktop (`0x01`)  | Mouse (`0x02`)            | **Mouse**: 5 buttons, wheel, 16-bit X/Y, horizontal wheel                              |
| **A**         | 3             | IN            | 2 Bytes          | Consumer (`0x0C`)         | Consumer Control (`0x01`) | **Media Keys**                                                                         |
| **B**         | none          | OUT / IN      | 64 / 12 Bytes    | Vendor Defined (`0xFFB3`) | Vendor Defined (`0x01`)   | **Update data pipe**: carries the firmware image ([FIRMWARE.md](FIRMWARE.md#nearlink-update)). A configuration frame sent here got no reply. |
| **C**         | 9             | OUT           | 12 Bytes         | Vendor Defined (`0xFFB1`) | Vendor Defined (`0x01`)   | **Update control**: starts and ends a firmware update ([FIRMWARE.md](FIRMWARE.md#nearlink-update)) |
| **C**         | 8             | OUT / IN      | 63 Bytes (+ID)   | Vendor Defined (`0xFF05`) | Vendor Defined (`0x01`)   | **Configuration channel**: everything below                                            |

The receiver (`373b:1216`) exposes the same set spread over three interfaces: a mouse-only interface, one with usage page `0xFFB3`, and one that combines the keyboard, media-key, `0xFFB1` and `0xFF05` collections. Configuration on the receiver also uses report 8 on `0xFF05`.

On Linux each interface is a separate `/dev/hidraw` node, and each one is root-only by default. Send to the node whose report descriptor contains usage page `0xFF05` and report ID 8.

---

## Frame (Report 8)

Every transfer is one 63-byte report, plus the report ID in front on output. The mouse answers with an input report on the same ID. Offsets below are within the 63 bytes after the ID.

### Request

| **Byte Index** | **Field Name**    | **Description / Value**                                                                |
| -------------- | ----------------- | -------------------------------------------------------------------------------------- |
| **`0`**        | Checksum          | Sum of bytes `1–62`, modulo 256                                                        |
| **`1`**        | Magic             | Constant `0x72`                                                                        |
| **`2`**        | Parameter Length  | See [Commands](#commands)                                                              |
| **`3`**        | Sequence          | `00` in every frame seen                                                                |
| **`4`**        | Target            | `0` = the device being addressed, `1` = the mouse behind a receiver                    |
| **`5`**        | Command           | See [Commands](#commands)                                                              |
| **`6`**        | Command Length    | See [Commands](#commands)                                                              |
| **`7–62`**     | Arguments         | Zero padded                                                                            |

### Reply

| **Byte Index** | **Field Name**    | **Description / Value**                                                                |
| -------------- | ----------------- | -------------------------------------------------------------------------------------- |
| **`0`**        | Magic             | Constant `0x72`. Unsolicited events are different frames, see [Events](#events).      |
| **`1`**        | Status            | `00` = ok. Non-zero is an error (`0xFF` is the error value; not reproduced on this unit). |
| **`2`**        | Length            | `0x3B` when a device answers its own command (cable, or the receiver answering for itself). For a mouse reached through the receiver (target `1`) it was the command length plus 4: `0x0A` for cid,mid, `0x16` for the config block. |
| **`3`**        | Reserved          | `00`                                                                                   |
| **`4`**        | Command Echo      | The command byte of the request                                                        |
| **`5`**        | Length Echo       | The command length of the request. It is **not** a count of the payload bytes: the battery reply echoes `01` and carries three bytes. |
| **`6–61`**     | Payload           | Up to 56 bytes, zero padded                                                            |
| **`62`**       | Constant          | `0x3C`                                                                                 |

Replies carry no checksum. A reply is matched to its request by the command echo.

```
// One command and its reply
function bm_xfer(cmd, param_len, cmd_len, args = [], target = 0):
    buf = zeros(63)
    buf[1] = 0x72
    buf[2] = param_len
    buf[3] = 0x00
    buf[4] = target
    buf[5] = cmd
    buf[6] = cmd_len
    buf[7 ..] = args
    buf[0] = sum(buf[1 .. 62]) & 0xFF
    send_output_report(8, buf)                   // 64 bytes with the ID
    until timeout:                               // 0.7 to 3 s, retry up to 3 times
        r = read_input_report(8)                 // 63 bytes
        if r[0] != 0x72 or r[4] != cmd: continue // events and stale replies
        if r[1] != 0x00: error("mouse returned an error")
        return r[6 ..]                           // payload
```

Example, cable, read cid and mid (`0x4A`):

```
TX  ca 72 08 00 00 4a 06 00 ...                  checksum 0xCA = 0x72 + 0x08 + 0x4A + 0x06
RX  72 00 3b 00 4a 06 00 02 08 00 ... 3c         payload 00 | cid = 02 | mid = 08
```

Timing: on the cable the reply arrived in about 4 ms. Through the receiver the mouse must be awake (move it). A sleeping or out-of-range mouse gives a timeout or an error status. Retry a few times before giving up.

### Reply buffer

A reply is built in a buffer that is **not cleared between commands**. Bytes after the real payload are left over from the previous reply, not zeros. For example, a `0x08` reply read right after a battery read ends `02 68 10`, where `68 10` is the previous reply's millivolts, and after a version read the same reply ends `02 00 0c`. Two rules follow:

- The real payload is the bytes the command defines. The length byte of the frame (`cmdLen + 4` through the receiver) and the echoed command length do **not** give an exact payload size: `0x1C` echoes `3` and carries four bytes, battery echoes `1` and carries three.
- A command sent with no arguments, such as `0x0A` or `0xAD` with command length `0`, returns no payload, and the first bytes it shows are leftovers. Do not read them as a value. (A `0x0A` "read" returned `f6 09` once, the leftover of an unrelated reply.)

Not tested: what the mouse does with a wrong checksum or a wrong length byte.

---

## Events

The mouse sends frames nobody asked for when its DPI changes. They are built like a request, not like a reply: the first byte is a checksum (the same sum of bytes `1` to `62`), byte `1` is **`0x73`** (a reply has `0x00` there), and byte `2` is the event type.

| **Byte Index** | **Field**     | **Description**                                                              |
| -------------- | ------------- | ---------------------------------------------------------------------------- |
| **`0`**        | Checksum      | Sum of bytes `1–62`, modulo 256                                              |
| **`1`**        | Magic         | `0x73`                                                                       |
| **`2`**        | Type          | See below                                                                    |
| **`3`**        | Length        | `05` in the DPI events seen                                                  |
| **`4`**        | Reserved      | `00`                                                                         |
| **`5–6`**      | X DPI         | 16-bit little-endian, the DPI now in use                                     |
| **`7–8`**      | Y DPI         | Same value                                                                   |

| **Type** | **Meaning**                                              | **Seen**        |
| -------- | -------------------------------------------------------- | --------------- |
| **`1`**  | DPI changed (the DPI button)                             | Receiver        |
| **`2`**  | Active profile changed                                   | Sent when a button changes the profile: `73 02 02 00 …` (see below); not sent after `0x0A` |
| **`4`**  | The mouse went to sleep                                  | **Not sent** on this unit (see below) |
| **`5`**  | The mouse is awake and connected again                   | Not captured    |

Example, receiver: four presses of the DPI button gave `91 73 01 05 00 80 0c 80 0c` (3200 DPI), `9b 73 01 05 00 90 01 90 01` (400), `bf 73 01 05 00 20 03 20 03` (800) and `05 73 01 05 00 40 06 40 06` (1600), in the order of the stage table. The event carries the DPI value, not the stage number. Button clicks and wheel scrolling produce no event on this channel: they are ordinary mouse reports on the mouse interface.

A frame whose byte `1` is `2` is not a reply and a host should drop it. The profile type was not triggered.

**Sleep.** With the sleep time set to 30 s and the mouse left untouched for 110 s, the mouse did go to sleep: a config read sent afterwards got no answer. In that time **no event frame of any type arrived** on the settings channel, and nothing arrived on the receiver's mouse interface either. So this unit does not announce that it is going to sleep. A host that wants a sleep indicator has to infer it, for example from unanswered reads. While the mouse sleeps the receiver still answers some simple queries (versions, battery, online status) from what it last saw, so an answer to those does not prove the mouse is awake: use a read that only the mouse can answer, such as the config block. Waking was checked separately with the default 300 s sleep: a passive listener on all three receiver nodes ran for 420 s with the mouse untouched, then the mouse was moved. Moving it produced hundreds of ordinary mouse reports on the mouse interface and **no frame at all** on the settings channel or the other receiver interface, so there is no wake event either (the type `5` in the vendor's tables is not sent by this unit).

Every client with the interface open sees every reply, not only the replies to its own requests, so two programs talking to the same receiver see each other's traffic.

---

## Commands

Parameter and command lengths are the values sent on this unit. The argument layouts are below.

| **Command** | **Name**               | **Param Len** | **Cmd Len** | **Description**                                              | **Tested**        |
| ----------- | ---------------------- | ------------- | ----------- | ------------------------------------------------------------ | ----------------- |
| `0x01`      | Set report rate        | 3             | 1           | One rate code, see [Report Rate](#report-rate)               | Receiver          |
| `0x02`      | Set DPI stage          | 12            | 10          | One stage, see [DPI Stages](#dpi-stages)                     | Cable, Receiver   |
| `0x03`      | Set lift-off           | 4             | 2           | Args `height`, millimetres minus 1. `height` is stored at `0x0045` (`0` in profile 0, `1` in profiles 1 to 3); the second byte at `0x0046` | Receiver |
| `0x05`      | Set button             | 8             | 5           | See [Buttons](#buttons)                                      | Receiver          |
| `0x06`      | Set macro action       | 14            | 11          | One macro action, see [Macros](#macros)                      | Receiver          |
| `0x07`      | Battery                | 2             | 1           | Percent and millivolts                                       | Cable, Receiver   |
| `0x09`      | Get config             | 20            | 18          | See [Config Block](#config-block-0x09)                       | Cable, Receiver   |
| `0x0A`      | Set profile            | 3             | 1           | Profile number `0` to `3`; other numbers are ignored. There is no read form: read the active profile from byte 0 of the config block or from memory `0x0000` | Receiver |
| `0x0B`      | Set linear correction  | 3             | 1           | `00` / `01`                                                  | Receiver          |
| `0x0C`      | Set ripple control     | 3             | 1           | `00` / `01`                                                  | Receiver          |
| `0x0D`      | Set motion sync        | 3             | 1           | `00` / `01`                                                  | Receiver          |
| `0x13`      | Reset                  | 2             | 1           | Restores settings                                            | Untested          |
| `0x14`      | Set light              | 6             | 3           | See [Light](#light)                                          | Receiver          |
| `0x15`      | Set sensor sleep       | 5             | 2           | Seconds, little-endian                                       | Receiver          |
| `0x16`      | Set debounce           | 3             | 1           | Milliseconds                                                 | Receiver          |
| `0x17`      | Read memory            | 10            | 13          | See [Memory Reads](#memory-reads)                            | Cable, Receiver   |
| `0x18`      | Write memory           | —             | —           | Exists; layout not verified                                  | Untested          |
| `0x1A`      | Device type            | 2             | 1           | See [Identity and Power Status](#identity-and-power-status)  | Cable, Receiver   |
| `0x08`      | Worker mode            | 3             | 1           | Send one argument byte `00`; reads one byte, `02` on this unit (the same value as the link type) | Receiver |
| `0x1C`      | Mouse version          | 5             | 3           | See [Identity and Power Status](#identity-and-power-status)  | Cable, Receiver   |
| `0x1F`      | Set sensor mode        | 3             | 1           | `00` basic, `04` competitive, `05` competitive max (not on this model) | Receiver (`04`)   |
| `0x4A`      | Mouse cid and mid      | 8             | 6           | See [Identity and Power Status](#identity-and-power-status)  | Cable, Receiver   |
| `0xAD`      | Extended power status  | 3             | 1           | Send one argument byte `00`; reads one byte, `00` on this unit (full battery, not charging) | Receiver |
| `0x81`      | Receiver connection    | 3             | 1           | One byte. `00` while the mouse is on the cable.              | Cable, Receiver   |
| `0x82`      | Receiver pair mode     | 3             | 0           | Starts pairing                                               | Untested          |
| `0x83`      | Receiver clear pair    | 3             | 0           | Removes the pairing                                          | Untested          |
| `0x84`      | Receiver pair status   | 3             | 1           | One byte. `00` while the mouse is on the cable.              | Cable, Receiver   |
| `0x88`      | Receiver version       | 5             | 3           | Same layout as `0x1C`                                        | Receiver          |

Receiver commands (`0x81–0x88`) use target `0`. Everything else uses target `0` over the cable and target `1` through the receiver.

More commands exist for features other models have; they are in [Further Commands](#further-commands). The ones a host sends on connect, `0x0F` (charging state), `0xAE` (charge time remaining) and `0x23` (mouse online status), are decoded there.

---

## Config Block (`0x09`)

The reply payload is a block of settings. There is no argument.

| **Payload Index** | **Field**                  | **Description**                                                       | **Tested**      |
| ----------------- | -------------------------- | --------------------------------------------------------------------- | --------------- |
| **`0`**           | Profile                    | Active profile, `0` on this unit                                      | Cable, Receiver |
| **`1`**           | Config version             | `0` on this unit                                                      | Cable, Receiver |
| **`2`**           | Report rate code           | See [Report Rate](#report-rate)                                       | Cable, Receiver |
| **`3–4`**         | Lift-off height (byte 3) | Byte 3 is the first lift-off argument (memory `0x0045`): `00` in profile 0, `01` in profiles 1 to 3. Byte 4 reads `00`; a host also reads bytes 3 and 4 together as a 16-bit "DPI value", which is not what they hold here. | Cable, Receiver |
| **`5`**           | Lift-off                   | Millimetres minus 1                                                   | Cable, Receiver |
| **`6`**           | Motion sync                | `00` / `01`                                                           | Cable, Receiver |
| **`7`**           | Linear correction          | `00` / `01`                                                           | Cable, Receiver |
| **`8`**           | Ripple control             | `00` / `01`                                                           | Cable, Receiver |
| **`9–10`**        | Sensor sleep               | Seconds, little-endian                                                | Cable, Receiver |
| **`11`**          | Debounce                   | Milliseconds                                                          | Cable, Receiver |
| **`12–16`**       | Button class               | Class of left, right, middle, back, forward, see [Buttons](#buttons)  | Receiver        |
| **`17`**          | Combo DPI toggle           | `00` / `01`. Set with command `0xAF`, see [Further Commands](#further-commands). | Cable (reads `00`) |

Example, cable: `00 00 01 00 00 01 01 00 00 08 07 04` is profile 0, 500 Hz, lift-off 2 mm, motion sync on, linear correction and ripple control off, sleep `0x0708` = 1800 s, debounce 4 ms.

---

## Report Rate

`0x01` takes one code. The same code is in config payload byte `2`.

| **Code**  | **Rate**                                                          |
| --------- | ----------------------------------------------------------------- |
| **`0`**   | 1000 Hz                                                           |
| **`1`**   | 500 Hz                                                            |
| **`2`**   | 250 Hz                                                            |
| **`3`**   | 125 Hz                                                            |
| **`4`**   | 8000 Hz (other models; Untested)                                  |
| **`5`**   | 4000 Hz (other models; Untested)                                  |
| **`6`**   | 2000 Hz (other models; Untested)                                  |

500 Hz to 1000 Hz and back was written and read back through the receiver.

---

## DPI Stages

### Reading

The stage table is read with [Memory Reads](#memory-reads) from address `1`, in ten-byte chunks at addresses `1, 11, 21, 31, 41, 51, 61`. Together they give 66 bytes:

```
byte 0        index of the active stage
byte 1        table size, reads 8 (not a count of configured stages)
bytes 2..65   eight stages of 8 bytes: x lo, x hi, y lo, y hi, blue, green, red, reserved (0)
```

Unconfigured stages read 0 DPI and keep stale colour bytes. The usable stages are the leading run of non-zero entries. X and Y always hold the same value on the R1 NK.

Seen on the cable: stages 400, 800, 1600, 3200, with stage index 2 active.

### Writing (`0x02`)

Argument bytes, ten of them:

```
index, x lo, x hi, y lo, y hi, blue, green, red, 0, current
```

`current` is `1` when the stage being written is made the active one. With `current = 0` the table is updated and the sensor stays on its current stage. Removing a stage is a write of its index followed by nine zero bytes. The mouse replies with an echo of the request.

Example, cable (stage 1 to 800 DPI, green, made active):

```
TX  d1 72 0c 00 00 02 0a 01 20 03 20 03 00 ff 00 00 01 00 ...
RX  72 00 3b 00 02 0a 01 20 03 20 03 00 ff 00 00 01 00 ... 3c
```

Tested: reading over both paths. Writing a stage value, its colour, adding a fifth stage and deleting it (through the receiver, read back), and the 800 DPI example above (cable). The PAW3395SE range of 200 to 18000 DPI in 50 DPI steps comes from the vendor's sensor table. It was not exercised through this protocol.

---

## Other Settings

| **Setting**           | **Command** | **Arguments**                                              | **Tested**                       |
| --------------------- | ----------- | ---------------------------------------------------------- | -------------------------------- |
| **Lift-off**          | `0x03`      | `height`, `offset calibration`. A host sends `00`, millimetres minus 1. `height` is stored at `0x0045` and the second byte at `0x0046`; writing `[0, 1]` in profile 1 changed `0x0045` from `01` to `00` and nothing else. | Receiver (writes read back, both bytes seen in memory) |
| **Motion sync**       | `0x0D`      | `00` / `01`                                                | Receiver                         |
| **Linear correction** | `0x0B`      | `00` / `01`                                                | Receiver                         |
| **Ripple control**    | `0x0C`      | `00` / `01`                                                | Receiver                         |
| **Debounce**          | `0x16`      | Milliseconds. Values 1, 2, 4, 8, 15 and 20 were seen.      | Receiver (4 to 8)                |
| **Sensor sleep**      | `0x15`      | Seconds, little-endian                                     | Receiver (1800 to 300)           |
| **Sensor mode**       | `0x1F`      | `00` basic, `04` competitive, `05` competitive max (only on models that have it) | Receiver (`04` written and read back at `0x004A`, then restored) |
| **Profile**           | `0x0A`      | Profile number; see [Profiles](#profiles)                  | Receiver (profiles `1` to `3` selected and restored; `4` ignored) |

### Light

`0x14` takes three bytes: `mode, brightness, speed`.

| **Field**      | **Values**                                                                 |
| -------------- | -------------------------------------------------------------------------- |
| **Mode**       | `0` off, `1` breathing, `2` steady                                         |
| **Brightness** | `0x55` low, `0xAA` medium, `0xFF` high are the three a tool offers; the mouse stores any byte (`1E`, `80`, `00` and `FF` were written and read back unchanged) |
| **Speed**      | `0x0A` slow, `0x0F` medium, `0x14` fast                                    |

The setting reads back as the same three raw bytes at memory address `76`. Tested through the receiver; the unit read `00 55 14` (off, low, fast).

The vendor's model table switches four features off for the R1 NK: the "competitive max" sensor mode, separate X/Y DPI, long-range mode and sensor angle. Everything else is left on by default. This is the table's statement, not something checked on the unit.

---

## Buttons

### Writing (`0x05`)

Argument bytes: `index, class, b2, b3, b4`.

| **Index** | **Button**   |
| --------- | ------------ |
| **`0`**   | Left         |
| **`1`**   | Right        |
| **`2`**   | Middle       |
| **`3`**   | Back         |
| **`4`**   | Forward      |
| **`5`**   | DPI button   |

| **Class**                | **Meaning**                     | **Bytes after the class**                                         |
| ------------------------ | ------------------------------- | ----------------------------------------------------------------- |
| **`0`**                  | None / factory default          | `00 00 00`                                                        |
| **`1`**                  | Mouse button                    | `00, value, 00`. Value `0` left, `1` right, `2` middle, `3` back, `4` forward. |
| **`2`**                  | System key                      | `00, code 0, code 1`. Written and read back (code in the first of the two bytes). |
| **`3`**                  | Keyboard                        | `modifier mask, usage 0, usage 1`                                 |
| **`4`**                  | Macro                           | `00, macro id, 00`. This writes only the button entry; the macro body is written with the macro command. Accepted and read back. |
| **`5`**                  | Fire key                        | `click count, interval lo, interval hi` (interval 16-bit little-endian). Written and read back; whether it fires was not tried. |
| **`6`**                  | Turn around                     | A button that does a quick 180° turn, configured with `0xBA`. Not tested. |
| **`10`, `11`, `12`**     | DPI cycle, DPI up, DPI down     | none                                                              |
| **`13`–`16`**            | Scroll up, down, left, right    | none                                                              |
| **`17`**                 | Previous profile                | none                                                              |
| **`18`–`20`**            | Jump to profile 1, 2, 3         | none                                                              |
| **`21`**                 | Next profile ("profile loop")   | none                                                              |
| **`255`**                | Disabled                        | none                                                              |

Modifier bits: left ctrl `0x01`, left shift `0x02`, left alt `0x04`, left win `0x08`, right ctrl `0x10`, right shift `0x20`, right alt `0x40`, right win `0x80`.

### Reading

Read the button table with [Memory Reads](#memory-reads) at addresses `82`, `92` and `102`, ten bytes each. The 30 bytes are six five-byte entries in the index order above. The stored entry is laid out differently from the bytes sent to write it:

```
stored entry   class, modifier mask, mouse button, key 0, key 1
```

| **Class**       | **Stored entry**                                    |
| --------------- | --------------------------------------------------- |
| **Mouse**       | `01, 00, value, 00, 00`                             |
| **Keyboard**    | `03, modifier mask, 00, usage 0, usage 1`           |
| **Macro**       | `04, 00, 00, macro id, 00`                          |
| **Fire key**    | `05, 00, click count, interval lo, interval hi`     |
| **DPI, scroll, profile, disabled** | `class, 00, 00, 00, 00`           |

A written mouse button has its value in the fourth byte of the argument list; the stored entry has it in the third. Convert between them rather than copying the five bytes.

Writing a mouse button its own default (forward bound to forward) reads back as class `0`: the mouse normalises it, so this is not a failure. Rebinding a button does not clear a macro stored earlier.

Tested through the receiver on the back button (index `3`): every class in the table except turn around was written and read back, and the button was then restored to its default. Results:

- All of them were **accepted without an error**, including the profile classes and a macro class that points at a macro id with no body behind it. The mouse does not check that a class makes sense.
- Only the bytes of the entry changed. Each write is acknowledged by an echo of the five bytes plus a trailing `01`.
- The button table is in memory at `0x0052` onwards, five bytes per button in index order, so the back button's entry is at `0x0061–0x0065`: class, modifier mask, mouse button, key 0, key 1. A mouse button of `4` (forward) landed in the mouse-button byte (`0x0063`), a keyboard modifier mask in `0x0062`, a key usage in `0x0064`, a fire key's click count in `0x0063` and its interval in `0x0064–0x0065`, a system key's code in `0x0064`, and a macro id in `0x0064`.
- The class byte also shows in the config block, bytes `12–16` for left, right, middle, back and forward (the DPI button has no byte there).
- A button written with the class `1` and its own default value (back = `3`) reads back as all zeros, as the firmware treats that as default.

Whether a class actually does what it says when the button is pressed was not tried, except for the macro playback tests.

---

## Macros

### Writing (`0x06`)

A macro is sent one action per packet, about 20 ms apart. Argument bytes, eleven of them:

```
key index, action index, key type, key status, usage 0, usage 1,
hold ms lo, hold ms hi, macro id, start type, run count
```

| **Field**        | **Description**                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------------ |
| **Key index**    | The button the macro is bound to, numbered as in [Buttons](#buttons)                             |
| **Action index** | Position of this action within the macro, starting at `0`                                        |
| **Key type**     | `0` = keyboard, `1` = mouse button, `2` = scroll. All three were written and played on the unit. |
| **Key status**   | `0` = down, `1` = up                                                                             |
| **Usages**       | Keyboard usage in `usage 0`. Modifiers are ordinary usages (`0xE0` left ctrl, `0xE1` left shift, `0xE2` left alt), not a bitmask. |
| **Hold**         | Milliseconds, little-endian                                                                      |
| **Macro id**     | `0` on every action except the last, where it is the macro's number. This binds the macro to the button. |
| **Start type**   | Repeated on every action, see below                                                              |
| **Run count**    | Repeated on every action. Only used by start type `4`.                                           |

| **Start Type** | **Behaviour**                                   |
| -------------- | ----------------------------------------------- |
| **`1`**        | Repeat while held, stop at once on release      |
| **`2`**        | Repeat until any key is pressed                 |
| **`3`**        | Repeat until the same key is pressed again      |
| **`4`**        | Loop `run count` times                          |

How a host fills the key fields for each kind of action:

| **Action**           | **Key type** | **Key status**                  | **Usage 0**                              | **Usage 1** |
| -------------------- | ------------ | ------------------------------- | ---------------------------------------- | ----------- |
| **Key or modifier**  | `0`          | `0` down or `1` up              | Keyboard usage                           | `00`        |
| **Mouse button**     | `1`          | `0` down or `1` up              | Bit mask: `01` left, `02` right, `04` middle, `08` back, `10` forward| `00`        |
| **Scroll**           | `2`          | `0`                             | `01` wheel up, `FF` wheel down           | `00`        |

A scroll is a single action, not a down and up pair. The hold time of an action is the delay after it. A host lets the last action have no hold at all.

Example, back button to left ctrl + left shift + c, 100 ms holds, repeat while held:

```
03 00 00 00 e0 00 64 00 00 01 01
03 01 00 00 e1 00 64 00 00 01 01
03 02 00 00 06 00 64 00 01 01 01             macro id 1 on the last action
```

The button then reads back as `04 00 00 <macro id> 00` ([Buttons](#buttons)). Start type and run count are not in that entry.

### Store Layout

A macro is stored **per button**. The mouse has six slots of 430 bytes, one for each button in index order (left, right, middle, back, forward, DPI button), at `0x0071 + 430 × button index`: `0x0071`, `0x021F`, `0x03CD`, `0x057B`, `0x0729` and `0x08D7`. The bunny hop settings follow right after, at `0x0A86`. All six are read with [Memory Reads](#memory-reads). The slot of a write is chosen by its first argument, the key index (written and read back for all six buttons; the left and right buttons were bound to the test macro for a fraction of a second and set back to default). A host that assumes the 12 slots other models in the line have would read and write the wrong place on this mouse.

```
header   start type, run count                                                    2 bytes
record   key type, status, code 0, code 1, hold lo, hold hi                       6 bytes each, up to 70
footer   at slot offset 422: 00, action count + 1, then 6 zero bytes              8 bytes
```

A stored record is the same six fields the write packet carries, in the same order (see [Writing](#writing-0x06)). **One exception:** for a mouse-button action (key type `1`) the code of the key-up record is stored as the bit complement of the mask sent (a release of forward, `10`, was stored as `ef`), so the stored value is an AND mask for the release and an OR mask for the press. The macro id is **not** stored in the slot: it lives only in the button entry. The footer's second byte (offset 423) is the **action count plus one**: it read `05` for a four-action macro, `02` for a one-action macro, and `08` for the seven-action macro written in the playback test. A macro also ends at the first all-zero record.

The second header byte holds the run count **only in loop mode**; for the other start types it is **not written** and keeps whatever the slot held before. The same three-action macro was written with each start type and several run counts, in this order, and read back each time:

| **Start type sent** | **Run count sent** | **Stored header** | **Footer byte** |
| ------------------- | ------------------ | ----------------- | --------------- |
| `1`, `2` or `3`     | `1` or `5`         | `01 02`, `02 02`, `03 02`: the `02` left over from the previous loop-2 macro | count + 1 |
| `4`                 | `1`                | `04 01`           | count + 1       |
| `4`                 | `5`                | `04 05`           | count + 1       |
| `4`                 | `9`                | `04 09`           | count + 1       |
| `4`                 | `0`                | `04 00` (accepted) | count + 1      |

Writing a hold or same-key macro straight after that last loop-0 macro then read back `03 00` and `02 00`, which confirms the leftover rule. A host should ignore the second header byte unless the start type is `4`. The footer's second byte was the action count plus one in every case.

Example, `a` down 111 ms, `a` up 222 ms, `b` down 333 ms, `b` up 444 ms, loop 9, as stored in the back button's slot (`0x057B`):

```
04 09 | 00 00 04 00 6f 00 | 00 01 04 00 de 00 | 00 00 05 00 4d 01 | 00 01 05 00 bc 01 | ... | 00 05 00 00 00 00 00 00
```

Example, ctrl down, shift down, F13 down, F13 up, shift up, ctrl up, then one scroll up, 30 ms each, loop 2 (key type `0` is keyboard, `2` is scroll):

```
04 02 | 00 00 e0 00 1e 00 | 00 00 e1 00 1e 00 | 00 00 68 00 1e 00 | 00 01 68 00 1e 00 | 00 01 e1 00 1e 00 | 00 01 e0 00 1e 00 | 02 00 01 00 1e 00 | ... | 00 08 00 00 00 00 00 00
```

Writing the first action of a macro clears the rest of the slot: after a two-action macro was written over the four-action one, its old third and fourth actions read back as zero.

### Which Slot a Macro Uses

The slot is chosen by the **key index** in the write packet, not by the macro id. Writes with the same one-action macro and key index `3` (back) went to the back button's slot (`0x057B`) for macro ids `1`, `2`, `3`, `4`, `5` and `255`, and with key index `4` (forward) and id `2` the macro went to the forward button's slot (`0x0729`). Key index `2` wrote at `0x03CD`, key index `5` at `0x08D7`, and key indexes `0` and `1` at `0x0071` and `0x021F`.

The macro id is a number kept in the button entry. A button bound to any id plays the macro stored in **its own slot**: the back button, written with id `1` and then rebound to id `9`, played the same 70-action macro both times. Use any id; `1` for the first macro is the convention. A write whose last action carries id `0` does not mark the macro as complete (the slot read back with no actions), so always put a non-zero id on the last action.

Every macro write also **binds the button**: the button entry reads `04 00 00 <id> 00` afterwards, so a tool that writes a macro for a button must write that button's final binding afterwards if it should be something else.

There is no command that clears a slot. A rewrite replaces the header and the records and zeroes the old tail, but the footer keeps `count + 1`, so a slot that has held a macro never reads as all zero again. Stale bodies in unbound slots are harmless.

The number of slots equals the number of buttons here; a host cannot read the slot count from the mouse as far as was found.

**Limits that were tested** (through the receiver):

- **70 actions fit.** A macro of 70 key-down and key-up records was written and read back in full; the header read `04 01`, the last record started at offset 416, and the footer's second byte was `47`, which is 70 + 1. The same 70-action macro was then played from the back button: 70 keyboard reports (F13 down and up, 30 ms hold) in 2.21 s, and again in 1.97 s with the button rebound to another id. A 71st action was not written, because its record would run into the footer and the next slot.
- **The hold is a full 16-bit value.** Holds of `0`, `1000` and `65535` ms were stored as `00 00`, `e8 03` and `ff ff` and read back unchanged. A hold of `0` is accepted.
- **Macros belong to the active profile.** Selecting another profile showed the slots empty and selecting the first one brought them back unchanged ([Profiles](#profiles)).

Stale macro bodies stay in memory when a button is rebound; they are harmless.

Tested: through the receiver, a loop of `a`, 5 times, wrote and played back as expected; a two-action macro (`a` down 111 ms, `a` up 222 ms, loop 7) wrote, was acknowledged with an echo of each packet and read back from the back button's slot; and a seven-action macro with a chord, key-ups and a scroll wrote, read back and played correctly (below). The button was set to default again each time.

### Playback

What the mouse does when a button bound to a macro is pressed, captured on the receiver's keyboard and mouse interfaces. The macro was: left ctrl down, left shift down, F13 down, F13 up, left shift up, left ctrl up, then one scroll up, each action 30 ms, start type `4`, run count `2`, bound to the back button. It was pressed twice.

- **A macro is ordinary input.** The mouse plays it as plain keyboard reports (report ID 2, 8 bytes: modifiers, reserved, six keys) and mouse reports (report ID 1: buttons, wheel, X, Y). Nothing special travels on the settings channel while it plays.
- **The button's own report is suppressed.** No back-button report appeared; only the macro's output did.
- **Chords are built one modifier at a time.** The keyboard reports were `01` (ctrl), `03` (ctrl+shift), `03` with F13 (`68`) down, `03` with no key, `01`, `00`. Each action is its own report, and releasing is a separate key-up action: the mouse does not release anything by itself.
- **Hold time is the delay after the action.** Consecutive reports were 32 to 36 ms apart for a 30 ms hold, so the mouse adds about 2 to 6 ms to each.
- **Loop mode plays the whole sequence.** With start type `4` and run count `2` every press played the full sequence twice, then stopped. A second press played it again from the start.
- **A scroll action is one mouse report with the wheel at `+1`** (`00 01 00 00 00 00 00`: buttons, wheel, x, y), sent at its place in the sequence. It needs no release. Key type `2` with code `01` is wheel up.
- **A mouse-button action presses and releases a real button.** Key type `1`, code `10` (forward), status down then up gave the mouse report `10 00 00 00 00 00 00` (forward held), then `00 00 00 00 00 00 00` (released) 44 ms later. The code is a bit mask in the mouse report's button byte: `01` left, `02` right, `04` middle, `08` back, `10` forward.
- **A scroll down is one report with the wheel at `−1`** (`00 ff 00 00 00 00 00`), the same as a scroll up with the opposite sign. In the test it followed the button release by 44 ms. Key type `2`, code `FF`.
- **The next loop starts about 40 ms after the last action**, a little longer than a normal step.
- **Hold mode (start type `1`) repeats while the button is held.** A two-action macro (F14 down, F14 up, 40 ms each) held for about 2 seconds produced a press and a release about every 94 ms, 20 pairs in all, then stopped when the button was released. The last report was the key-up, so nothing is left held down.
- **Same-key mode (start type `3`) is a toggle.** Pressing the button once starts the macro and it repeats on its own (a press and release of F14 about every 92 ms). Pressing the same button again stops it, and a third press starts it again. Over a two-minute test that gave start, stop, start, stop, start: every stop ended on a key-up and every start began with a key-down, so a stop never leaves a key held.
- **Rebinding the button stops a running macro.** Writing the button back to its default while a macro was repeating stopped it within one cycle, again ending on a key-up.
- **Any-key mode (start type `2`) stops on a button press, not on motion.** One press of the back button started it and it repeated for 21.6 s. Six seconds of mouse movement in the middle did not interrupt it (no gap in the keyboard reports). A left click then stopped it: the last keyboard report was a key-up, and the left-button press report followed 30 ms later, so the press that stops the macro is still passed on to the host. A first, less controlled run stopped in a similar way.

Not yet played: delays longer than a few milliseconds, and a macro of more than a few actions.

---

## Further Commands

These are the commands for features that other mice in the line have. The read forms (operation byte `0`) of most of them were sent to the R1 NK through the receiver. The write forms were not. Do not send a write form to your own mouse to find out what it does: several of them change settings.

**A zero reply does not mean "supported".** The mouse answers a command it does not implement with the command echoed, status `00` and an all-zero payload, not with an error (the zeros were seen after replies whose tail was zero; see the [reply buffer](#reply-buffer), which can show leftovers instead). Ask `0xB1` first, as a host does, and treat the other replies as meaningful only for the features it reports.

Observed on the unit (mouse firmware 1.0.12, receiver 1.0.20, through the receiver, target `1`):

| **Command**             | **Payload**                | **Meaning**                                                                   |
| ----------------------- | -------------------------- | ----------------------------------------------------------------------------- |
| `0xB1` feature mask     | `00`                       | **None** of the five optional features (DPI toggle, scroll reverse, centre point v2, 13K fps, turn around) |
| `0x25` performance mode | `00 00 00`                 | Operation echo, mode `0`. **Writing mode `4` was acknowledged but changed nothing**: no memory byte moved and the read stayed `00 00 00`, so this firmware ignores it. |
| `0x27` scroll reverse   | `00 00`                    | Zeros; the mouse does not list the feature                                    |
| `0x22` bunny hop        | `00 00 c8 00`              | Operation echo, disabled, time `0x00C8` = 200 ms. **A write took effect**: enabling it read back `00 01 c8 00`, and disabling restored the original. It is stored at `0x0A86` (enable), `0x0A87–0x0A88` (time, little-endian), just after the settings region: writing enable `1`, time `0x0155` changed exactly those three bytes in a diff of `0x0000–0x4000` (nine more bytes around `0x2BD4` changed on their own in every pass; they look like RAM) and restoring put them back. |
| `0xAA` / `0xB7` centre  | all zero                   | Zeros; the mouse does not list the feature                                    |
| `0xAC` preset           | `00 00`                    | Zeros                                                                         |
| `0xBA` turn around      | `00 00`                    | Zeros; the mouse does not list the feature                                    |
| `0x47` chip ID          | all zero                   | Zeros (two 32-bit values of 0)                                                |
| `0x0F` charging         | `00 68 10`                 | Not charging; then the battery millivolts (`0x1068` = 4200 mV)                |
| `0xAE` charge time      | `00 00 00`                 | 0 (not charging)                                                              |
| `0x23` mouse online     | `00 00`                    | `00` while the mouse was awake and linked; with the mouse out of range it gets no reply at all (see below) |

Payload bytes are numbered from the first byte after the length echo, as in [Frame (Report 8)](#frame-report-8). Many commands start with an **operation byte**: `0` reads the setting, `1` writes it.

### Which Features the Mouse Has

`0xB1` (param len 3, cmd len 1, no argument) returns a bit mask in payload byte `0`. A host asks this instead of looking at the model. An error status means an older mouse that does not know the command.

| **Bit** | **Feature**                                                |
| ------- | ---------------------------------------------------------- |
| **`1`** | Combo DPI toggle (`0xAF`, config byte `17`)                |
| **`2`** | Scroll reverse (`0x27`)                                    |
| **`4`** | Sensor centre point, version 2 (`0xB7`)                    |
| **`8`** | 13K fps sensor mode                                        |
| **`16`**| Turn around (`0xBA`, button class `6`)                     |

Some features are also gated by firmware version per model (for example the sensor centre point and dynamic sensitivity need firmware 3.0.5 or later on the ATK F1 Ultimate 2.0, cid,mid `1,8`; bunny hop needs 1.0.0 on `1,19`, `1,25`, `1,27`, `2,34`, `2,35` and `2,36`). The R1 NK (`2,8`) is not in that gating list.

### Commands

| **Command** | **Name**               | **Param Len** | **Cmd Len** | **Payload**                                                                                           |
| ----------- | ---------------------- | ------------- | ----------- | ----------------------------------------------------------------------------------------------------- |
| `0x0F`      | Charging status        | 2             | 1           | One byte, `1` = charging                                                                              |
| `0x21`      | Set sensor angle       | 4             | 2           | `enable, angle`                                                                                       |
| `0x22`      | Bunny hop              | 6             | 4           | `operation, enable, time` (time 16-bit little-endian, milliseconds)                                   |
| `0x23`      | Mouse online status    | 3             | 1           | One byte                                                                                              |
| `0x25`      | Performance mode       | 5             | 3           | `operation, mode, corded` (see below)                                                                 |
| `0x27`      | Scroll reverse         | 4             | 2           | `operation, enable`                                                                                   |
| `0x47`      | Chip ID                | 10            | 8           | Two 32-bit little-endian values                                                                       |
| `0xAA`      | Sensor centre point    | 6             | 4           | `operation, enable, position, backend` (position `0` to `201`; backend `1` native, `2` overclock)     |
| `0xB7`      | Sensor centre point v2 | 6             | 4           | `operation, enable, y position, x position`                                                           |
| `0xAB`      | Dynamic sensitivity    | 27            | 25          | `operation, enable, point count (5), window ms (16-bit), 5 × (x 16-bit, scale 16-bit)`                |
| `0xAC`      | Dynamic sensitivity preset | 4         | 2           | `operation, preset`: `0` off, `1` classic, `2` natural, `3` jump, `4` custom                          |
| `0xAE`      | Charge time remaining  | 6             | 4           | 32-bit little-endian                                                                                  |
| `0xAF`      | Combo DPI toggle       | 3             | 1           | `enable`                                                                                              |
| `0xBA`      | Turn around            | 9 (3 to read) | 7 (1 to read) | read: `00`. write: `01, enable, direction, duration, count`; duration 16-bit milliseconds, 10 to 60000; count 16-bit, 1 to 65535 |

Sensor centre point: position `0` is the centre, `1` to `100` move it one way in steps of one, and `101` to `201` move it the other way. Dynamic sensitivity points are a speed (16-bit) and a scale in hundredths (10 to 600, so 0.10 to 6.00); the default curve is `0 → 1.00`, `5 → 1.00`, `35 → 1.15`, `70 → 1.40`, `120 → 1.60`, and the window is 4 to 64 ms (20 by default).

**Two commands set the same thing.** The sensor mode is written with `0x1F` (value stored at memory `0x004A`: `0` basic, `4` competitive, `5` competitive max) on mice that do not report the 13K-fps feature, and with `0x25` on mice that do (`0xB1` bit `8`). With `0x25`, `operation, mode, corded` is written as mode `0` basic, `1` competitive, `2` competitive max, and with mode `2` the `corded` byte picks the plain version (`1`) or the 13K version (`0`); the mode and flag are read back with the read form. The R1 NK reports no optional features, so it uses `0x1F`; `0x25` was acknowledged and ignored on it.

**Do not send the write form of `0x4A`.** With operation `1` and `cid`, `mid` it writes the mouse's identity (param len 7, cmd len 5: `01, cid, mid`). That would change which model a host thinks the mouse is.

### Receiver Light

The receiver has an LED. `0x86` reads it and `0x85` writes it, with target `0`, param len 11 and cmd len 9:

| **Payload Byte** | **Description**                                           |
| ---------------- | --------------------------------------------------------- |
| **`0`**          | Status (`1` when writing)                                 |
| **`1`**          | Mode                                                      |
| **`2`**          | Brightness: `10` low, `50` medium, `100` high             |
| **`3`**          | Speed                                                     |
| **`5–7`**        | Red, green, blue                                          |
| **`8`**          | Sleep time                                                |

Receiver command `0x89` reads the cid and mid of the paired mouse from the receiver, in the same layout as `0x4A`. Not tested.

On this receiver `0x86` and `0x89` read all zeros: it has no RGB light, as its device-table entry says.

---

## Settings Memory Map

Where each setting lives, found by changing one setting at a time through its command and diffing the memory before and after. Every change moved **exactly the bytes listed and nothing else** (the memory was stable between two reads, so there was no noise to filter). Each setting was restored and the whole region read back as it was before. Tested through the receiver.

| **Address**       | **Size** | **Setting**                                     | **Written with**              |
| ----------------- | -------- | ----------------------------------------------- | ----------------------------- |
| **`0x0000`**      | 1        | Active profile number                           | `0x0A`                        |
| **`0x0001`**      | 1        | Current DPI stage                               | Set DPI stage with `current`  |
| **`0x0002`**      | 1        | DPI table size (reads 8)                        | Not written                   |
| **`0x0003 + 8n`** | 8        | DPI stage `n` (0 to 7): x lo, x hi, y lo, y hi, blue, green, red, 0. Stage 3's x moved at `0x001B` and y at `0x001D`. | `0x02`                |
| **`0x0043`**      | 1        | Report rate code                                | `0x01`                        |
| **`0x0045`**      | 1        | Lift-off first argument ("height"), `00` in profile 0 | `0x03`                  |
| **`0x0046`**      | 1        | Lift-off: millimetres minus 1                   | `0x03`                        |
| **`0x0047`**      | 1        | Motion sync                                     | `0x0D`                        |
| **`0x0048`**      | 1        | Linear correction                               | `0x0B`                        |
| **`0x0049`**      | 1        | Ripple control                                  | `0x0C`                        |
| **`0x004A`**      | 1        | Sensor model: `00` basic, `04` competitive      | `0x1F` (written and restored) |
| **`0x004C–0x004E`** | 3      | Light: mode, brightness, speed                  | `0x14`                        |
| **`0x004F–0x0050`** | 2      | Sensor sleep, seconds, little-endian            | `0x15`                        |
| **`0x0051`**      | 1        | Debounce, milliseconds                          | `0x16`                        |
| **`0x0052–0x006F`** | 30     | Button table (six entries of five bytes)        | `0x05`                        |
| **`0x0071–0x0A84`** | 6 × 430 | Macro slots, one per button (`0x0071 + 430 × button`) | `0x06`                |
| **`0x0A86–0x0A88`** | 3      | Bunny hop: enable, time ms (little-endian)      | `0x22`                        |

The config block (`0x09`) is not a straight copy of this memory. Its payload bytes `2` to `8` follow addresses `0x0043` to `0x0049`, but its sleep (bytes `9–10`) and debounce (byte `11`) come from `0x004F–0x0051`, and its byte `3` follows `0x0045`, the first lift-off argument. Bytes `4` and `17` read zero. A write is acknowledged by an echo of the request's arguments (for example `15 02 58 02` for sleep 600: command, length, the two argument bytes).

---

## Profiles

The mouse stores more than one profile, and selecting one **swaps in a separate set of settings and a separate set of macros**. `0x0A` takes the profile number (param len 3, cmd len 1) and the active number is at memory `0x0000` and in config payload byte `0`.

Tested through the receiver: profile `1` was selected from profile `0`, the memory read, and profile `0` selected again. After selecting profile `1` the mouse answered with the config block reading profile `1`, and these bytes of the settings region had changed:

| **Memory**    | **Setting**               | **Profile 0** | **Profile 1** |
| ------------- | ------------------------- | ------------- | ------------- |
| `0x0000`      | Profile number            | `00`          | `01`          |
| `0x0043`      | Report rate code          | `01` (500 Hz) | `00` (1000 Hz) |
| `0x0045`      | Lift-off first argument (config payload byte 3) | `00` | `01`          |
| `0x004D`      | Light brightness          | `55`          | `1E`          |
| `0x004F–0x0050` | Sensor sleep            | 300 s         | 30 s          |
| `0x0051`      | Debounce                  | 4 ms          | 8 ms          |
| `0x006B`      | DPI button class          | `0A` (cycle)  | `00` (default) |
| `0x0071–0x0A84` | All macro slots         | the stored macros | **all zero** |

The DPI table, lift-off, motion sync, linear correction, ripple control, light mode and speed, and the other five buttons read the same in both. After selecting profile `0` again every setting and both macro slots read exactly as before, so the other profile's data is kept by the mouse and not lost by switching. A write goes to the **active** profile only.

Consequences for a tool:

- Read and write settings and macros for the profile that is active, and read `0x0000` first.
- Profile `1` looked like a factory-style set (30 s sleep, 8 ms debounce, 1000 Hz, empty macros). Whether it was ever customised on this unit is unknown.
- Profiles `2` and `3` were also selected: both answered like profile `1` (same changed bytes, same factory-style values, empty macros) and profile `0` came back unchanged each time. Selecting profile `4` was echoed but ignored: memory and config stayed on profile `0`. So the mouse has four profiles numbered `0` to `3`, which fits the profile button classes (`18` to `20` reach profiles 1 to 3, see [Profile buttons](#profile-buttons)). The current profile is not read with `0x0A`: sending it with no argument returns whatever the previous reply left in the buffer (see [Reply buffer](#reply-buffer)); use byte 0 of the config block.
- Selecting a profile was accepted at once and changed the active rate, so it is a real switch, not a label.

---


### Profile buttons

A button bound to class `17` to `21` changes the active profile when it is pressed, and the mouse sends one event `73 02 02 00 …` (type `2`) per press. Each class was bound to the back button in profile 0, pressed once, and the active profile read from the config block (byte 0), then profile `0` and the button were restored:

| **Class** | **Active profile after one press from profile 0** |
| --------- | ------------------------------------------------- |
| `17`      | `3` (from profile 1: `0`)                         |
| `18`      | `1`                                               |
| `19`      | `2`                                               |
| `20`      | `3`                                               |
| `21`      | `1` (from profile 1: `2`)                         |

From profile 1, class `17` led to profile `0` and class `21` to profile `2`. So class `17` is **previous profile** (0 wraps to 3), class `21` is **next profile** (3 wraps to 0, assumed), and classes `18`, `19` and `20` jump straight to profiles 1, 2 and 3 (class minus 17; profile 0 has no direct class on this mouse). The new profile has its own buttons (default), so a second press of the same button does nothing there. Read the active profile from byte 0 of the config block (`0x09`), which a sleeping mouse does not answer, or from memory `0x0000`; `0x0A` has no read form.
## Memory Reads

`0x17` reads the mouse's configuration memory in short pieces.

| **Argument Byte** | **Description**                  |
| ----------------- | -------------------------------- |
| **`0–1`**         | Address, little-endian           |
| **`2`**           | Length, at most 10 per read      |

The reply payload is `address lo, address hi, length`, then the data, so the data starts at payload offset `3`.

```
function bm_read(address, length):
    r = bm_xfer(0x17, 10, 13, [address & 0xFF, address >> 8, length])
    return r[3 .. 3 + length - 1]
```

DPI stages, the button table and macros are all read this way. A scan of addresses `0` to `0x800` found the macro area only at the address given above.

The address space is not limited to settings. Past `0x0C00` it reads like the mouse's working memory: 32-bit pointers of the form `xx xx 12 90` and `xx xx 13 90`, counters, and text such as "KeyboardGLE". Of the 7 KB read from `0x0C00` to `0x2800`, about 6 KB is non-zero. Reading is harmless, but this also means the memory write command (`0x18`) can reach structures well beyond the settings, so a host should write only to addresses it has read and understood. The settings live in three blocks: `0x0001–0x006F` (DPI table, sensor model, light, buttons), `0x0071–0x0A84` (the six macro slots) and `0x0A86–0x0A88` (bunny hop).

---

## Identity and Power Status

### Identifying the R1 NK

The USB ID is not enough on the receiver, so ask the mouse.

| **Command** | **Reply payload**                          | **Seen**                                                    |
| ----------- | ------------------------------------------ | ----------------------------------------------------------- |
| **`0x4A`**  | `operation, cid (1 byte), mid (32-bit little-endian)` | `00 02 08 00 00 00`, so cid 2 and mid 8. The R1 S NK answers 2,9. |
| **`0x1C`**  | `major, minor, patch, 1 more byte`         | `01 00 0c 43` is version 1.0.12. The fourth byte is real (it does not change with the previous reply): `43`, the ASCII letter `C`. Its meaning is not known. |
| **`0x88`**  | Same layout as `0x1C`, receiver only       | `01 00 14 41` for receiver firmware 1.0.20; the fourth byte is `41`, the ASCII letter `A` |
| **`0x1A`**  | One byte, the link type                    | The mouse answers `02` on the cable and through the receiver. The receiver answers `00` (receiver 1K) for itself. |

Link type values: `0` receiver 1K, `1` receiver 4K, `2` wired 1K, `3` wired 8K, `4` receiver 2K, `5` receiver 8K, `6` wired 2K, `7` wired 4K.

### Battery (`0x07`)

| **Payload Byte** | **Description**                              |
| ---------------- | -------------------------------------------- |
| **`0`**          | Percent                                      |
| **`1–2`**        | Millivolts, little-endian                    |

Seen: `52 c6 0f` is 82 % at 4038 mV. `48 70 0f` is 72 % at 3952 mV. Through the receiver, `64 68 10` is 100 % at 4200 mV. The charging state is not in this reply: it is a separate command, `0x0F`, with one payload byte (`1` = charging; the unit read `01` on the cable). The time left to a full charge is `0xAE`, a 32-bit little-endian value (the unit was on the cable and read `00 00 00 00`; the unit of the number is not known). Battery %, charging state and time remaining together are what a host shows as the battery.

### Online Status

For a mouse behind a receiver, a host first reads the receiver connection (`0x81`, payload byte 0 non-zero = a mouse is linked) and then the mouse's own online status (`0x23`, payload byte 0). Over the cable `0x23` returned `00`. With the mouse carried out of range, the receiver's `0x81` payload went from `01` to `00` about 3 s after the mouse's commands (`0x23`, battery, version) stopped getting any reply; there is no "offline" answer. When the mouse came back, `0x81` read `01` again and the mouse answered normally within about a second, without any event on the settings channel. So a host should treat a missing reply as offline and `0x81` as the link flag.

### Receiver

While the mouse is on the cable the receiver reports `00` for both connection status (`0x81`) and pair status (`0x84`), and a mouse command with target `1` gets no reply. Before sending a mouse command through the receiver, check the pair status and wake the mouse.

A read-only pass over the cable (target `0`, the interface that carries both `0xFFB1` and `0xFF05`) gave the same answers as through the receiver for version (`01 00 0c`), battery (100 %, 4200 mV, charging `0` because it was full), config, profile (config byte 0, `0`), link type (`02`), cid and mid (`2`, `8`) and the feature mask (`0`), and the same memory contents, so settings do not depend on the path. Receiver commands over the cable (`0x88`, `0x81`) returned empty payloads; target `1` got no reply at all. The reply length byte is `0x3B` on every cable reply.

With the mouse linked and awake the receiver reports `01` for both, and a mouse command with target `1` is answered normally (every query in [Further Commands](#further-commands) was). The receiver's own version reads `01 00 14 41` for firmware 1.0.20; the last byte is not decoded, as with the mouse's.

After the receiver moved to 1.0.20 its USB manufacturer string changed from "ATK" to "MADLIONS" (the product string stayed "NK mouse NANO dongle", and the USB ID `373b:1216` did not change). A host that matches the receiver by the name string, not by the ID, would stop finding it.

### What a Host Reads

A host that keeps a view of the mouse up to date was seen to send this through the receiver:

| **When**                | **What**                                                                                  |
| ----------------------- | ----------------------------------------------------------------------------------------- |
| **On connect**          | cid,mid (`0x4A`), mouse version (`0x1C`), receiver version (`0x88`), config block (`0x09`), then these memory reads (`0x17`): addresses `1, 11, 21, 31, 41, 51, 61` (DPI table), `74` (one byte, the sensor model; `00` on this unit), `76` (three bytes, light) and `82, 92, 102` (button table), then battery (`0x07`) and charging state (`0x0F`) |
| **Every 5 seconds**     | Receiver connection status (`0x81`)                                                       |
| **Every 30 seconds**    | Battery (`0x07`), charging state (`0x0F`), config block (`0x09`) and a one-byte memory read of address `1` (the current DPI stage; `02` on this unit) |

Each answer is a normal reply, so the traffic is easy to follow on the wire. Between those, nothing is sent unless the user changes something or the mouse sends an [event](#events).

---

## Write Rules

- **Read first.** Every command above that sets something has a way to read it back. Verify each write by reading the value again, and restore what you changed.
- **Keep unknown bytes.** Do not rewrite bytes that were not decoded (config bytes `3`, `4`, `17`).
- **A write is acknowledged by an echo.** Check the status byte, then read the value back.
- **Do not guess commands.** Some command numbers are sets, and the numbering does not tell them apart from gets. The commands marked Untested may change stored data or calibration.
- **Memory writes (`0x18`) and reset (`0x13`) were never run.**

---

## Other ATK and VXE Protocol Generations

The same vendor ID (`373b`, and `3554` on older 2.4 GHz models) is used by several incompatible generations. The R1 NK speaks only the one above. A 16-byte frame of the older generation sent to the R1 NK got no reply. The rest of this section was not tested on this unit and describes the other generations from their layout alone.

### Generation 1: 16-byte EEPROM protocol

Report ID 8, 16-byte frames, usage page `0xFF04` (or `0xFF02`), usage `0x02`.

| **Byte Index** | **Field**              | **Description**                                                    |
| -------------- | ---------------------- | ------------------------------------------------------------------ |
| **`0`**        | Command                |                                                                    |
| **`1`**        | Status                 | `00` in a request                                                  |
| **`2–3`**      | EEPROM address         | Big-endian                                                         |
| **`4`**        | Valid length           |                                                                    |
| **`5–14`**     | Data                   | 10 bytes                                                           |
| **`15`**       | Checksum               | `(0x55 − (0x08 + sum of bytes 0..14)) & 0xFF`                      |

Many settings are stored as `value, 0x55 − value` pairs.

| **Command**   | **Name**                                                            |
| ------------- | ------------------------------------------------------------------- |
| **`0x01`**    | Download data (connect handshake)                                   |
| **`0x03`**    | Wireless mouse online                                               |
| **`0x04`**    | Battery level                                                       |
| **`0x05`, `0x06`** | Set dongle pair, get pair result                                |
| **`0x07`, `0x08`** | Set EEPROM, get EEPROM                                         |
| **`0x09`**    | Restore factory                                                     |
| **`0x0A`**    | Report mouse status (unsolicited: DPI, rate, profile changed)       |
| **`0x0E`, `0x0F`** | Get and set current profile                                    |
| **`0x10`**    | Get mouse cid and mid                                               |
| **`0x12`**    | Get mouse version                                                   |
| **`0x13`**    | Dongle exit pair                                                    |
| **`0x14`, `0x15`** | Set and get 4K light mode                                      |
| **`0x16`, `0x17`** | Set and get far-distance mode                                  |
| **`0x18`, `0x19`** | Set and get dongle light mode                                  |
| **`0x1D`**    | Get dongle version                                                  |

EEPROM addresses (get with `0x08`, set with `0x07`):

| **Address**          | **Content**                                                                  |
| -------------------- | ---------------------------------------------------------------------------- |
| **`0x00`**           | Report rate (`1` 1 kHz, `2` 500, `4` 250, `8` 125, `0x10` 2 kHz, `0x20` 4 kHz, `0x40` 8 kHz) |
| **`0x02`, `0x04`**   | Maximum DPI stages, current stage                                            |
| **`0x08`**           | Button operation mode                                                        |
| **`0x0A`**           | Lift-off (silent height)                                                     |
| **`0x0C`–`0x24`**    | DPI stages 1, 3, 5, 7 (two stages in each 8-byte entry)                      |
| **`0x2C`–`0x44`**    | DPI stage colours                                                            |
| **`0x4C`–`0x5F`**    | DPI light effect, brightness, speed, enable; article lamp colour and effects |
| **`0xA0`**           | Decoration light                                                             |
| **`0xA9`–`0xBC`**    | Debounce, motion sync, light-off time, linear correction, ripple, sensor sleep and mode, RF transmit time (value and CRC pairs) |
| **`0xBD`**           | Sensor angle                                                                 |
| **`0x60 + 4n`**      | Button `n`, 0 to 15: four bytes `class, v1, v2, 0x55 − (class + v1 + v2)`    |
| **`0x100 + 0x20n`**  | Shortcut `n`, 0 to 15                                                        |
| **`0x300 + 0x180n`** | Macro `n`, 0 to 15 (12 usable). Ten bytes per write; five-byte actions, delay in the last two bytes (big-endian). |
| **`0x1B00`–`0x1B50`**| Sensor tables (PAW3955 DPI slots at 6 bytes each, dynamic sensitivity, centre point, fast-trigger debounce) |
| **`0xE3`**           | Rolling delay                                                                |

Button classes in this generation: `0` off, `1` mouse (`1` L, `2` R, `4` M, `8` side 1, `16` side 2), `2` DPI (`1` cycle, `2` up, `3` down), `3` roll side to side, `4` fire key, `5` shortcut, `6` macro, `7` report rate, `9` profile, `10` DPI lock, `11` wheel.

### Generation 3: Feature-report protocol

Used by a few models on usage page `0xFF10`, usage `0x01`, as 63-byte **feature** reports on report ID 2. Replies arrive as feature reports; unsolicited changes use input report 6.

| **Byte Index** | **Field**     | **Description**                                |
| -------------- | ------------- | ---------------------------------------------- |
| **`0`**        | Length        | Payload bytes for this command                 |
| **`1`**        | Type          | `0x80` set, `0x81` get                         |
| **`2`**        | Command       | `1` data, `2` performance, `3` DPI, `4` DPI colour, `5` buttons, `6` DPI button, `7` macro, `10` dongle light |
| **`3–62`**     | Payload       | Offsets are relative to the command byte       |

Data block (command `1`, length 14): current DPI stage, battery level, battery charge, mouse version (decimal digits), receiver version, active profile, receiver rate, mouse rate, boot flag, link type, mouse mid. Performance (command `2`, length 17): deep sleep (16-bit), pairing mode, function bits (ripple 0, motion sync 1, linear correction 2, rapid mode 5, high-speed mode 6), sensor angle, lift-off, five debounce bytes, reset, bunny-hop enable and time. DPI (command `3`, length 35): current stage, maximum stage, eight 16-bit X values, eight 16-bit Y values. Buttons (command `5`, length 33): five five-byte bindings, six macro binding bytes, a macro-valid bitmask. Macro (command `7`, length 39): modifier, button, 34 bytes of macro data.

Report rate codes in this generation: `0` 8000 Hz, `1` 4000, `2` 2000, `6` 1000, `7` 500, `8` 250, `9` 125.

---

## Open Questions

- What the fourth byte of the version reply is (`43` = `C` for the mouse, `41` = `A` for the receiver). It is stable and real, but a host reads only the first three bytes and nothing was found that explains it.
- Whether the zero replies to `0x27`, `0xAA`, `0xB7`, `0xAC`, `0xBA` and `0x47` mean "not implemented". `0xB1` says none of the optional features exist, so they probably are. (Bunny hop, `0x22`, does work, and `0x25` is acknowledged and ignored; both are described above.)
- The unit of the `0xAE` charge time while charging.
- Whether the other R1 NK USB IDs (`373b:1311`, `373b:135c`) use exactly this layout.
- What the single byte of `0x08` (`02`) and `0xAD` (`00`) stands for beyond their names; `0x08` was only read on the receiver, not on the cable, and `0xAD` only with the battery full.
