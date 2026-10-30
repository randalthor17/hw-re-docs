
## Tools

Everything needed to talk to the MK75, read and patch its firmware, and check the result. All tools are plain Python 3 (no extra packages) and run on Linux. The protocol is in [PROTOCOL.md](../PROTOCOL.md), the firmware in [FIRMWARE.md](../FIRMWARE.md).

| **Tool**                   | **What It Does**                                                                                         |
| -------------------------- | -------------------------------------------------------------------------------------------------------- |
| **`mk75wired.py`**         | Client for the keyboard over the USB cable (`258a:010c`): read config, raw GETs, change one config byte, side-light tests |
| **`mk75rx.py`**            | The same over the 2.4 GHz receiver (`3554:fa09`)                                                         |
| **`mk75dump88.py`**        | Reads the whole flash over the cable with GET `0x88` (no ISP, no root) and compares it with a dump      |
| **`mk75asm.py`**           | Turns a firmware dump into assembler source, rebuilds it, and applies patches                           |
| **`mk75tables.txt`**       | Code pointer tables found by hand, used by `mk75asm.py`                                                 |
| **`ghidra/seeds.txt`**     | Extra code entry points, used by `mk75asm.py` and the Ghidra script                                      |
| **`ghidra/run.sh`**        | Imports a dump into Ghidra (headless) and exports decompiled C and a listing                             |
| **`patches/side_direct.asm`** | The side-light direct patch, version 2                                                                |

---

## Setup

### Access to the Keyboard

The clients open the keyboard's hidraw node. Without root, a udev rule has to grant access, for example in `/etc/udev/rules.d/70-mk75.rules`:

```
KERNEL=="hidraw*", ATTRS{idVendor}=="258a", ATTRS{idProduct}=="010c", TAG+="uaccess"
KERNEL=="hidraw*", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="fa09", TAG+="uaccess"
```

Then run `sudo udevadm control --reload` and replug the keyboard or receiver. The clients find the right node on their own; `mk75wired.py --dev /dev/hidrawN` picks one by hand.

### Other Software

| **Software**     | **Needed For**                          | **Notes**                                                                                   |
| ---------------- | --------------------------------------- | ------------------------------------------------------------------------------------------- |
| **`sinowisp`**   | Reading and writing flash over ISP      | `cargo install sinowisp` (2.1.0 used). Runs as root: the ISP device gets no hidraw node.    |
| **SDCC**         | `mk75asm.py build` and `patch`          | 4.5.0 used. `mk75asm.py` looks for `sdas8051` / `sdld`, then Fedora's `sdcc-sdas8051` / `sdcc-sdld`, and otherwise runs them in a distrobox called `fedora`. |
| **Ghidra**       | `ghidra/run.sh` only                    | Ghidra 12 with a JDK it accepts. Found through Homebrew, or set `GHIDRA_HOME` and `JAVA_HOME`. |

---

## Talking to the Keyboard

### `mk75wired.py` (Cable)

| **Command**                         | **What It Does**                                                                               |
| ----------------------------------- | ---------------------------------------------------------------------------------------------- |
| **`cfg`**                           | Read and decode the config block (GET `0x84`)                                                  |
| **`psd`**                           | Read the PSD identity bytes (GET `0x82`)                                                       |
| **`get CMD LEN [INDEX]`**           | Any GET, printed as hex                                                                        |
| **`poke OFFSET VALUE`**             | Change one config byte (read-modify-write). Prints the command that puts the old value back.  |
| **`side SLOT\|all R G B [SECONDS]`** | Stream side-light frames (SET `0x07`) at 20 Hz. **Patched firmware only.**                    |
| **`side map A-B\|A,B,C [SECONDS]`**  | Light up to 7 slots in red, green, blue, yellow, magenta, cyan, white. **Patched firmware only.** |

```
python3 mk75wired.py cfg
python3 mk75wired.py get 0x87 2 2          # power status
python3 mk75wired.py poke 18 3             # side light: static colour
python3 mk75wired.py side all 0 0 255 5    # both strips blue for 5 s
```

### `mk75rx.py` (2.4 GHz Receiver)

| **Command**                         | **What It Does**                                                              |
| ----------------------------------- | ----------------------------------------------------------------------------- |
| **`cfg`**                           | Read and decode the config block (GET `0x44`)                                 |
| **`psd`**                           | Read the PSD identity bytes (GET `0x05`)                                      |
| **`get CMD [LAYER]`**               | Any GET, printed as hex                                                       |
| **`side SLOT\|all R G B [SECONDS]`** | Stream side-light frames (radio `0x08`, layer 3) at 20 Hz. **Patched firmware only**; stock firmware ignores them. |

```
python3 mk75rx.py cfg
python3 mk75rx.py get 0x41 0               # keymap layer 0
```

Both files are also libraries. `Wired.get(cmd, length, index)` / `Wired.set(cmd, data, index)` and `Rx.get(cmd, layer)` / `Rx.set(cmd, data, layer, ack)` do the framing, timing and retries from PROTOCOL.md. Their `set()` refuses keymap layers above 3 and macro blocks of 8 or higher, and `write_cfg()` refuses a config without `ff ff` at bytes 56–57.

---

## Working on the Firmware

### Reading It

Over ISP (as root), the full 64 KB:

```
sudo sinowisp read -d aula-f75 -s full --format bin dump.bin
```

Over the cable without ISP (**not yet run on a full dump**, see FIRMWARE.md):

```
python3 mk75dump88.py usb-dump.bin dump.bin   # second argument: compare with an ISP dump
```

### Rebuilding and Patching It

```
head -c 61440 dump.bin > stock.bin                                          # firmware only; keep it to restore
python3 mk75asm.py dis stock.bin mk75.asm                                   # source of 0x0000–0xEFFF
python3 mk75asm.py build mk75.asm rebuilt.bin stock.bin                     # must report 0 bytes differ
python3 mk75asm.py patch mk75.asm patches/side_direct.asm mk75-side.asm mk75-side.bin stock.bin
```

`patch` prints the sites and how much free space the patch uses, and refuses any change outside its sites and `0xEF33–0xEFF7`. The output is exactly `0xF000` bytes, the size `sinowisp write` expects. The generated source is vendor code: don't publish it.

### Writing It

```
sudo sinowisp write -d aula-f75 --format bin mk75-side.bin
```

To undo a patch, write `stock.bin` back the same way. Before writing, read the warnings in [FIRMWARE.md](../FIRMWARE.md#writing-the-firmware).

### Ghidra

```
ghidra/run.sh dump.bin
```

This writes `ghidra/decomp.c` and `ghidra/listing.txt` next to the `tools` folder. Like the source, they are derived from vendor code.
