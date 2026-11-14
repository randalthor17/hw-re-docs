
**Warning:** Nothing in this document was flashed to a mouse. It describes the update path from the layouts and the files alone. A firmware image built for another USB ID can leave a mouse unusable. Do not edit the IDs inside an image to make it fit: the images are checked and signed.

Firmware for this family comes as `FWATKPAK` files from the vendor's lookup service. A NearLink mouse or receiver, which includes the R1 NK and its receiver, is flashed **in-band over two vendor interfaces it already exposes**: a control interface (`0xFFB1`, report 9) and a data interface (`0xFFB3`). The body of the file after its 1024-byte header is sent as it is, in 64-byte chunks. Other devices use a different in-band flow with signed MCUboot images. This document covers where firmware comes from, how the container is built, both update flows, and how a mouse and its receiver are updated together. Settings use another interface ([PROTOCOL.md](PROTOCOL.md)).

**The R1 NK (`373b:124c`) has no firmware on the vendor's service.** The receiver does. See [Finding Firmware](#finding-firmware).

---

## Hardware

| **Part**              | **Details**                                                                                                      |
| --------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Mouse chip**        | Hisilicon BS21 family. Update packages carry the chip tag `BS20` and are named `BS21x_bs20_...`.                 |
| **Radio**             | NearLink (SLE) and Bluetooth. Release notes give the names the mouse advertises: "VXE R1 NK" (USB and SLE) and "VXE R1 BT" (Bluetooth). |
| **Sensor**            | PixArt PAW3395SE                                                                                                 |
| **Receiver**          | The same chip family, a separate firmware ("NK mouse NANO dongle")                                               |
| **Images**            | MCUboot format: a header, a SHA-256 hash and a signature. The bootloader itself was not looked at.               |

Mouse and receiver have **separate firmware**. Updating one does not update the other, and a receiver update may expect a matching mouse version.

---

## Finding Firmware

The vendor runs a public lookup service. It needs no login.

```
GET /firmware/{vid}/{pid}/{tag}           latest entry, or {} when there is none
GET /firmware/{vid}/{pid}/{tag}/list      every entry, newest first, or [] when there is none
```

`vid` and `pid` are decimal. A hit is `{ "statusCode": 200, "data": { "version", "file", "content" } }`. `file` is a direct download from the vendor's CDN (`https://bpcdn.atkgear.com/...<md5>.bin` or `.zip`) and needs no login. `content` is the release note, in Chinese.

The tag is a short model mark. The mouse and the receiver are separate entries: the receiver is looked up with its own USB ID and the tag `dongle`, and the mouse with its own USB ID and its model mark.

| **Device**                     | **USB ID**    | **Tag**   | **Result**                                                    |
| ------------------------------ | ------------- | --------- | ------------------------------------------------------------- |
| **NK mouse NANO dongle**       | `373b:1216`   | `dongle`  | 1.0.20, 1.0.19, 1.0.17, 1.0.16, 1.0.12 (1.0.12 is the factory image; 1.0.20 appeared in November 2026 with the note "daily update") |
| **VXE R1 S NK**                | `373b:1310`   | `r1s`     | 1.0.20                                                        |
| **VXE R1 SE+**                 | `373b:12dc`   | `r1`      | 1.0.20                                                        |
| **VXE R1 NK**                  | `373b:124c`   | `r1`      | **Nothing.** The list is empty.                               |
| **VXE R1 NK**                  | `373b:1311`, `373b:135c` | `r1` | Nothing                                                  |

Tags `r1`, `r1nk`, `r1-nk`, `R1`, `mouse`, `x1`, the product name, and the product name with `2.4G` added were tried for `373b:124c`. All came back empty. Other brands on the same service use other vendor IDs (for example `3554`) with tags such as `r1-pro`.

There is also a beta lookup that takes `vid`, `pid`, `tag` and the current version in a POST. It was not reachable at the paths tried and was not pursued further.

Why the R1 NK gets nothing: a client only offers an update when the service has an entry for the exact USB ID and tag, and no entry exists for `373b:124c`. Whether that means "already current" or "never published" is not known.

The receiver on the test bench was updated to 1.0.20 and reads back `01 00 14` (decimal 1.0.20) over the settings channel. After that update its USB **manufacturer string reads "MADLIONS"** where it read "ATK" before. The USB ID (`373b:1216`) and the product string ("NK mouse NANO dongle") did not change. The mouse behind it reports 1.0.12, so the receiver update did not change the mouse.

---

## Image Container (`FWATKPAK`)

A `FWATKPAK` file is a 1024-byte header followed by a body. The identity fields (offsets `0` to `76`) are in every file seen. The encryption fields from offset `128` on are only filled when the body is encrypted; **none of the four files downloaded has them** (the receiver at 1.0.17, 1.0.19 and 1.0.20, and the R1 S NK at 1.0.20 all have zeros from offset `128` to `1023`).

| **Offset**     | **Field**           | **Description**                                                                       |
| -------------- | ------------------- | ------------------------------------------------------------------------------------- |
| **`0`**        | Magic               | ASCII `FWATKPAK`                                                                      |
| **`8`**        | Name                | Product name, NUL padded to offset `0x40`. Seen: "VXE R1 S NK", "NK mouse NANO dongle". |
| **`72`**       | Product ID          | 32-bit little-endian. Seen: `0x1310` (R1 S NK), `0x1216` (receiver).                  |
| **`76`**       | Vendor ID           | 32-bit little-endian, `0x373B`                                                        |
| **`128`**      | Encryption magic    | ASCII `ATKE`                                                                          |
| **`132`**      | Version             | `1`                                                                                   |
| **`133`**      | Algorithm           | `1`                                                                                   |
| **`136`**      | Ciphertext length   | 32-bit little-endian                                                                  |
| **`140`**      | Nonce               | 12 bytes                                                                              |
| **`152`**      | Key ID              | 32-bit little-endian, `1`                                                             |
| **`156`**      | Reserved            | `0`                                                                                   |
| **`1024`**     | Body                | Ciphertext, then a 16-byte tag. The body length is the ciphertext length plus 16.     |

The body is encrypted with a stream cipher built from SHA-256 and authenticated with HMAC-SHA-256. Both keys come from one fixed 32-byte master key that every host application ships with. The master key is not reproduced here.

```
enc_key = HMAC_SHA256(master, "ATK-OTA-ENC-v1")                       // 32 bytes
mac_key = HMAC_SHA256(master, "ATK-OTA-MAC-v1")

tag = HMAC_SHA256(mac_key, file[0 .. 1024 + ciphertext_length - 1])[0 .. 15]
if tag != file[1024 + ciphertext_length ..]: error("wrong key or damaged file")

// keystream block i: SHA-256( enc_key (32) || nonce (12) || i as 32-bit big-endian )
for i in 0 .. ceil(ciphertext_length / 32) - 1:
    block = SHA256(enc_key || nonce || be32(i))
    plain[i * 32 ..] = ciphertext[i * 32 ..] XOR block
```

A file that does not start with `FWATKPAK` is treated as a raw, unencrypted image with no vendor or product ID.

**The IDs in the header must match the device.** A host reads the product and vendor ID from the header, and refuses the file with a "firmware mismatch" error when they differ from the device it is talking to. The plain header is also covered by the tag, so the IDs cannot be edited.

### Plain Image (MCUboot)

The decrypted body is an MCUboot image.

| **Offset**     | **Field**           | **Description**                                                          |
| -------------- | ------------------- | ------------------------------------------------------------------------ |
| **`0`**        | Magic               | `0x96F3B83D`, little-endian                                              |
| **`4`**        | Load address        | 32-bit                                                                   |
| **`8`**        | Header size         | 16-bit, at least 32                                                      |
| **`10`**       | Protected TLV size  | 16-bit                                                                   |
| **`12`**       | Image size          | 32-bit                                                                   |
| **`16`**       | Flags               | 32-bit. `0x20` = load to RAM.                                            |
| **`20`**       | Version             | major (8-bit), minor (8-bit), revision (16-bit), build number (32-bit)   |

After the header and the image come the protected TLVs and a TLV block that starts with the magic `0x6907`. A host needs the SHA-256 entry (type `0x10`, 32 bytes) and refuses the image without it. Other types in the block: `0x01` key hash, `0x20` RSA-2048 PSS signature, `0x21` ECDSA-224, `0x22` ECDSA-256. The signature is for the mouse's bootloader to check.

Sizes seen: R1 S NK 1.0.20 is 296 640 bytes, receiver 1.0.20 is 279 312, receiver 1.0.19 is 278 800, receiver 1.0.17 is 277 376.

**What the downloaded files are.** The body of all four starts at offset 1024 with `4e 15 8d cb 00 00 01 00 00 05 00 00 20 00 00 00`, and its entropy is about 7.99 bits per byte. A host does not decrypt or parse it: for a NearLink device it checks the vendor and product ID in the header and sends everything after the first 1024 bytes as the update ([NearLink Update](#nearlink-update)). The `ATKE` encryption and the MCUboot image above belong to the other flow ([MCUboot In-Band Update](#mcuboot-in-band-update)). The receiver was updated to 1.0.20 with the vendor's Windows client, which runs the same update code as a browser does; that run was not captured.

---

## NearLink Update

This is the flow for the files the vendor's service serves for NearLink mice and receivers, the R1 NK family included. It was read from how a host builds the packets and was not run on a device.

**Two vendor interfaces carry it.** Both belong to the device that is being updated (the mouse's own USB ID for a mouse, the receiver's for a receiver). They are the two interfaces [PROTOCOL.md](PROTOCOL.md#usb-interfaces-373b124c-atk-vxe-r1-nk) lists next to the configuration channel.

| **Channel** | **Usage Page**              | **Usage** | **Report**                       | **Use**                                          |
| ----------- | --------------------------- | --------- | -------------------------------- | ------------------------------------------------ |
| **Control** | Vendor Defined (`0xFFB1`)   | `0x01`    | Report ID 9, 12 bytes, host to device | Start and end the update                    |
| **Data**    | Vendor Defined (`0xFFB3`)   | `0x01`    | No report ID, 64 bytes out, 12 bytes in | The header, then the image in chunks     |

The product and vendor ID of the device come from the file: 32-bit little-endian at header offsets `72` and `76` ([Image Container](#image-container-fwatkpak)). A host refuses the file when they differ from the connected device. The file's body (everything after the first 1024 bytes) is the image. Nothing is decrypted or parsed.

All messages start with the magic `EF BE AD DE`, then a 16-bit little-endian length, then a 16-bit little-endian command.

| **Message**     | **Channel** | **Bytes**                                                                                                  |
| --------------- | ----------- | ---------------------------------------------------------------------------------------------------------- |
| **Enter update** | Control    | `EF BE AD DE`, `0C 00`, `1E E1`, `00 00`, `00 00`                                                          |
| **Image header** | Data       | `EF BE AD DE`, `18 00`, `D2 2D`, `00 00 00 00`, size, size, `00 00 00 00`, zero padded to 64 bytes. Size is the body length, 32-bit little-endian, written twice. |
| **Image chunk**  | Data       | 64 bytes of the image, the last one padded with `FF`                                                       |
| **Exit update**  | Control    | Same as enter update, with `FF FF` in place of the first `00 00` after the command                         |

```
// body = file[1024 ..], size = len(body)
control.send(report 9, EF BE AD DE 0C 00 1E E1 00 00 00 00)       // enter
sleep(1 s)
data.send(header)                                                // 64 bytes, see above
sleep(1 s)
for i in 0 .. ceil(size / 64) - 1:
    chunk = body[i * 64 .. i * 64 + 63], padded to 64 with 0xFF
    reply = data.send_and_wait(chunk)                            // 12 bytes
    if reply[0 .. 11] != chunk[0 .. 11]: error("chunk i failed")
    sleep(2 ms)
sleep(1 s)
control.send(report 9, EF BE AD DE 0C 00 1E E1 FF FF 00 00)       // exit
sleep(3 s or more)                                               // the device restarts
```

Each chunk is acknowledged by an echo of its first 12 bytes; any difference stops the update. A host reports progress from 15 % to 95 % while the chunks go out. After the exit message the device restarts and shows up again (a desktop host waits for two device events, up to 10 seconds).

A receiver image of 278 288 body bytes (receiver 1.0.20) is 4 349 chunks.

The update needs **both** the `0xFFB1` and the `0xFFB3` interface of the same device open at once. On Linux that means access to every hidraw node of the product, not only the configuration one.

What this does not say: what is in the body (see [Image Container](#image-container-fwatkpak)), how the device checks the image, and what happens if the update is interrupted.

---

## MCUboot In-Band Update

This is the in-band flow for a MCUboot image. It was read from how a host builds the commands and was never matched to the files on the vendor's service (see above). The update uses three commands on report 8, in the same frame as the settings commands ([PROTOCOL.md](PROTOCOL.md#frame-report-8)), with target `0`.

| **Command** | **Name**   | **Param Len** | **Cmd Len** | **Arguments**                                    |
| ----------- | ---------- | ------------- | ----------- | ------------------------------------------------ |
| `0x4B`      | Init DFU   | 5             | 4           | Image size, 32-bit little-endian                 |
| `0x4C`      | Write DFU  | n + 6         | n + 4       | Offset, 32-bit little-endian, then n bytes of image (n up to 48) |
| `0x4D`      | Finish DFU | 1             | 0           | none                                             |

```
// image = plain MCUboot image, as above
bm_xfer(0x4B, 5, 4, le32(len(image)))        // reply payload[0] must be 0
for offset in 0, 48, 96, ... len(image) - 1:
    chunk = image[offset .. min(offset + 48, len(image)) - 1]
    r = bm_xfer(0x4C, len(chunk) + 6, len(chunk) + 4, le32(offset) + chunk)
    if le32(r[0 .. 3]) != offset: error("offset mismatch")     // up to 3 tries, 100 ms apart
send(0x4D, 1, 0)                              // no reply is awaited
// the mouse reboots; wait a second or more before talking to it again
```

The steps a client takes:

1. Read the file and check the IDs in its header against the connected device.
2. Decrypt and check the image, and take its SHA-256 from the TLV block.
3. Connect on the normal channel (`0xFF05`, usage `1`, the file's product ID). There is no separate boot-mode USB ID in this path.
4. Init, write in 48-byte chunks, finish.

This was not run. The reply to the write command is expected to carry the offset the mouse accepted, so a host should compare it with the offset it sent.

### Other Update Commands

A different set of command numbers is defined next to these and is not used by the path above: `0x80` get image list, `0x81` get image info, `0x82` start update, `0x83` write image, `0x84` write image end, `0x85` reset, `0x90` enter recovery, `0x91` exit recovery. Their layouts are not known. The numbers `0x81` and `0x82` also appear as receiver commands in [PROTOCOL.md](PROTOCOL.md#commands), so the lane they belong to is not clear. Do not send any of them to a mouse to see what happens.

---

## Updating the Mouse and Receiver Together

Many NearLink mice are flagged "update together" in the vendor's device list, including the R1 NK (`373b:124c`), the R1 S NK (`373b:124d`, `373b:1310`, `373b:135b`), the R1 NK variants `373b:1311` and `373b:135c`, the R1 SE+ and the R1 Pro Max 2.0 NK. For these, a host does not update the receiver on its own. It offers one combined update:

1. The host finds the receiver and the mouse as two separate HID devices (the user picks each, or the host picks them).
2. It looks up firmware for each: the receiver with the tag `dongle`, the mouse with its model tag, each under its own USB ID ([Finding Firmware](#finding-firmware)). The user can pick a local file instead of the vendor's.
3. **The start button works only when both a receiver file and a mouse file are selected.** If either is missing, nothing starts.
4. The receiver is updated first (the progress bar shows 50 % when it is done), then the mouse.
5. If the receiver step fails, the mouse step is not tried and the user sees a "receiver upgrade failed" result.

This is why a receiver update cannot be done alone for a mouse like the R1 NK: the mouse has no entry on the service, so the dialog never gets the second file. The receiver itself can be updated with a tool that does not ask for the mouse (the receiver was moved to 1.0.20 with the vendor's Windows updater). Nothing shows that a receiver update depends on the mouse's version.

Before the update starts, for devices handled by the older update tool, the dialog checks for a local desktop helper. Without one it shows a prompt that sends the user to the vendor's desktop updater. What that helper does was not read, so the prompt is the only evidence that some updates need it.

---

## Alternative Package: `ComUsbUpgradeFile`

A second kind of package circulates for the same product family. It was built for another USB ID of the R1 NK, and it is flashed with a different tool. The files are named `BS21x_bs20_Mouse_Fota_<model>_0x373B_0x<pid>_0x<version>_<sensor>_<hash>_<date>_DLL升级.bin`.

A package seen had three files:

| **File**                                   | **Target**                     | **Version** |
| ------------------------------------------ | ------------------------------ | ----------- |
| `..._VXE R1 NK_0x373B_0x10C7_...`          | `373b:10c7`, sensor 3395SE     | 1.25        |
| `..._VXE R1 S NK_0x373B_0x121F_...`        | `373b:121f`, sensor 3311       | 1.25        |
| `..._NK mouse NANO dongle_0x373B_0x10C9_...` | `373b:10c9`                  | 1.22        |

The release notes for 1.25 list: a macro-recording scroll-wheel fix, a keyboard repeated-keypress fix, device names ("VXE R1 NK", Bluetooth "VXE R1 BT", NearLink "VXE R1 NK"), and a patch for USB devices that stopped replying. The R1 S NK entry also changes a sensor register initial value (`0x7F`, set to `0x00`, in two places). The receiver release note lists only the same USB patch.

### Header (720 bytes)

| **Offset**     | **Field**           | **Description**                                                                       |
| -------------- | ------------------- | ------------------------------------------------------------------------------------- |
| **`0`**        | Header check        | 32-bit little-endian, `0x5555xxxx`. The algorithm is not known (a byte sum, CRC-16 and CRC-32 were tried). |
| **`4`**        | Header length       | `720` (`0x2D0`)                                                                       |
| **`8`**        | Firmware length     | 32-bit                                                                                |
| **`12`**       | Next file address   | `0`                                                                                   |
| **`16`**       | Version             | 32-bit, shown as hex: `0x125` is 1.25                                                 |
| **`20`**       | Device type         | `0xD2` mouse, `0xD3` receiver                                                         |
| **`21`, `22`** | cid, mid            | `0`, `0`                                                                              |

From offset `23` there are 64-byte slots:

| **Slot** | **Offset** | **Content**                                                                     |
| -------- | ---------- | ------------------------------------------------------------------------------- |
| **0**    | `0x17`     | ASCII `ComUsbUpgradeFile`                                                       |
| **1**    | `0x57`     | Chip tag `BS20`                                                                 |
| **2, 3** | `0x97`, `0xD7` | Boot-mode endpoints `vid_3554&pid_f2fe&mi_01&col01` and `...col02`          |
| **4, 5** | `0x117`, `0x157` | Normal-mode endpoints `vid_373b&pid_<pid>&mi_01&col05`                    |
| **6**    | `0x197`    | Command frame that makes the device reboot into update mode                     |
| **7**    | `0x1D7`    | Prepare-download command frame                                                  |
| **8**    | `0x217`    | Data-download command frame                                                     |
| **9**    | `0x257`    | Sensor name (`3395se`, `3311`)                                                  |
| **10**   | `0x297`    | Product name (empty here)                                                       |

The payload begins at `0x2D0`. Its first 16 KB has low entropy and the rest about 7.99, so most of it looks packed or encrypted.

The update device in boot mode is `3554:f2fe`. The package carries the frames to enter that mode, so the tool needs no fixed command. A tool is expected to find the device by the normal endpoint (`vid_373b&pid_<pid>`), so a package for `373b:10c7` would not be matched to a mouse at `373b:124c`. This was not run. This is the same kind of mismatch as in the `FWATKPAK` path above.

---

## Other Generations

- **Generation 1** (16-byte frames): `0x0D` puts the mouse into USB upgrade mode, and `0x5A` and `0x5B` carry the update error and status. The layouts were not seen working.
- **Generation 3** (feature reports on `0xFF10`): setting the boot flag (data block byte 10) to `1` reboots the mouse for an update. The update device and its protocol are not known.
- Some older models are updated with a Windows tool whose `.dat` files start with the bytes `qres` followed by a zlib stream. The payload entropy is about 7.99, so these are likely encrypted too. The tool was not run.

---

## Open Questions

- Whether an R1 NK firmware exists at all for `373b:124c`, and under what tag.
- The header check in the `ComUsbUpgradeFile` header.
- What the first 16 KB of the `ComUsbUpgradeFile` payload is, and how its payload is protected.
- The layout of the `0x80–0x91` update commands.
- What the body of the `FWATKPAK` files on the service is. A host sends it unchanged (the [NearLink Update](#nearlink-update)), and it is neither MCUboot nor marked `ATKE`.
- Whether the [NearLink Update](#nearlink-update) steps match what the device does on the wire. They come from how a host builds the packets. A capture of a real update (the receiver was moved to 1.0.20 on Windows and was not captured) would confirm the timing, the 12-byte replies and the restart.
- Whether the update needs the mouse to be on the cable, and whether it can run through a receiver.
- Whether a mouse stays on its normal USB ID during the update, or re-enumerates.
- Whether the bootloader of a `373b:124c` mouse accepts an image whose header ID is for another revision. This is why the images are not edited.
