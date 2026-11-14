
**Note:** This describes the configuration documents a tool can save, load and share for the R1 NK: the file, what is in it, and how it is turned back into commands. It was read from how a configuration tool builds and applies them. **No saved file was opened and no config was loaded onto the mouse**, so every layout here is "as built by a tool", not checked against a real file. The commands themselves are in [PROTOCOL.md](PROTOCOL.md).

A config is a snapshot of everything the mouse stores that the settings pages can change: the sensor settings, the DPI stages, the light, the six button bindings and the macros, **for the active profile only**: the mouse keeps its other profiles separately ([PROTOCOL.md](PROTOCOL.md#profiles)). It does not contain the firmware, the battery state or the pairing.

---

## Saved Config File

| **Property**    | **Value**                                                                                           |
| --------------- | --------------------------------------------------------------------------------------------------- |
| **Extension**   | `.bin`                                                                                              |
| **Name**        | The device name, unless the user types another                                                      |
| **Contents**    | The **base64 text** (ASCII bytes) of a UTF-8 JSON document                                          |
| **Binary values** | Any binary view inside the document is written as `{"__type": "DataView", "data": [byte, …]}` and rebuilt on load |

```
save:  json   = JSON.stringify(replace_dataviews(document))
       file   = ascii_bytes(base64(utf8(json)))
load:  json   = utf8(base64_decode(ascii(file)))
       document = restore_dataviews(JSON.parse(json))
```

A file that is not base64 or not JSON fails to load.

---

## Document Structure

```
{
  "keyActions": [ [ [ <6 button entries> ] ] ],
  "deviceConfig": {
    "device_name":  "…",
    "version":      "1.0.12",
    "onboard":      0,
    "connectType":  …,
    "lightConfig":  { "mode": …, "brightness": …, "speed": … },
    "mouseConfig":  { … },
    "deviceFeatureSupport": { … },
    "macroList":    [ … ]
  }
}
```

### Button entries (`keyActions`)

One entry per button, in the order left, right, middle, back, forward, DPI button:

| **Field**       | **Description**                                                                                      |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| `label`         | Display text                                                                                         |
| `changeKey`     | Five numbers `[class, modifier mask, mouse button, key 0, key 1]`: the **stored** entry layout ([PROTOCOL.md](PROTOCOL.md#reading)) |
| `defaultLabel`  | `left`, `right`, `center`, `side1` (back), `side2` (forward) or `bottom` (the DPI button)            |
| `defaultKey`    | The factory binding of that button, in the same five numbers                                         |

Factory bindings: left `[1,0,0,0,0]`, right `[1,0,1,0,0]`, middle `[1,0,2,0,0]`, back `[1,0,3,0,0]`, forward `[1,0,4,0,0]`, DPI button `[10,0,0,0,0]`. A button is "changed" when its `changeKey` differs from its `defaultKey`. For a macro binding (`class 4`) the macro id is the fourth number and indexes `macroList` from 1.

### Sensor and DPI settings (`mouseConfig`)

| **Field**                | **Meaning**                                                       | **Applied with**                  |
| ------------------------ | ----------------------------------------------------------------- | --------------------------------- |
| `reportRate`             | Hertz                                                             | report rate                       |
| `silentHeight`           | Lift-off in millimetres (`offsetCalibration + 1`)                 | lift-off (`height 0`, `mm − 1`)   |
| `offsetCalibration`      | The stored lift-off byte                                          | lift-off                          |
| `moveSync`, `lineCorrection`, `rippleCorrection` | `0` or `1`                                        | the three switches                |
| `sleepTime`              | Seconds                                                           | sensor sleep                      |
| `keyDebounceTime`        | Milliseconds                                                      | debounce                          |
| `sensorModel`            | Performance mode                                                  | performance mode                  |
| `sensorAngle`, `sensorAngleEnable` | Not on the R1 NK                                        | sensor angle                      |
| `farDistance`            | Not on the R1 NK                                                  | long-range mode                   |
| `dpiLevel`               | Index of the current stage                                        | DPI stage with `current`          |
| `dpiTotal`               | Size of the stage table (8)                                       | —                                 |
| `dpiList`                | Eight entries `{dpi: {xDpi, yDpi, dpiEx: 0}, color: {r, g, b}}`   | DPI stages and colours            |
| `cidMid`                 | `{cid, mid}`, the identity of the mouse                           | read-only                         |
| `receiveVersion`         | Receiver firmware text                                            | read-only                         |

Present only when the mouse supports the feature (`deviceFeatureSupport`): `dpiToggleEnabled`, `scrollReverse`, `turnAround`, `sensorCenterPoint` (`enable`, `position {x, y}`, `backend`), `dynamicSensitivity` (`enable`, `mode`, `window`, `points`) and `bhop` (`enable`, `time`). The R1 NK reports none of the optional features, so none of those fields should be written for it.

### Light (`lightConfig`)

`mode`, `brightness` and `speed` in the tool's own enumerations, converted to the three wire bytes when applied: mode off `0`, breathing `1`, steady `2`; brightness low `0x55`, medium `0xAA`, high `0xFF`; speed slow `0x0A`, medium `0x0F`, fast `0x14`.

### Macros (`macroList`)

A list; entry `n` is the macro with id `n + 1`. Each macro has:

| **Field**   | **Description**                                                                                          |
| ----------- | -------------------------------------------------------------------------------------------------------- |
| `name`      | Display name (`M1`, `M2`, …)                                                                             |
| `actions`   | List of `{type, keyCode, keyStatus, delay}`                                                              |
| `type`      | Repeat mode: stop immediately, repeat until the next key press, repeat until any key press, or loop a number of times |
| `frequency` | The loop count (1 when unused)                                                                           |

Action types: modifier key `0`, normal key `1`, media key `2`, power key `3`, mouse key `4`, move `5`, scroll `6`. Key status: down `0`, up `1`, wheel up `2`, wheel down `3`. `delay` is the hold in milliseconds.

---

## Applying a Config

A tool writes the settings first, then the buttons. For the R1 NK that is, in this order:

1. DPI stages and colours (one set-DPI write per stage)
2. Report rate
3. DPI table size / current stage
4. Performance (sensor) mode
5. Lift-off, debounce, motion sync, ripple control, linear correction
6. Light
7. Sensor sleep
8. Sensor angle and bunny hop; then each optional feature present in the file (centre point, dynamic sensitivity, DPI toggle, scroll reverse, turn around)
9. Each button that differs from its default

A button whose class is `4` is applied by writing its macro: the actions from `macroList[id − 1]`, one packet per action, 20 ms apart. Any other button is applied with the button command, using the five numbers of `changeKey` converted to the write layout (a mouse button's value moves from the third stored byte to the fourth argument byte).

Converting a macro to packets:

| **Macro field**   | **Wire**                                                                                       |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| Action `type` modifier or normal key | key type `0`, status as given, usage in `code 0`                          |
| Action `type` scroll | key type `2`, status `0`, code `01` for wheel up or `FF` for wheel down                    |
| Any other `type`  | key type `1`                                                                                    |
| `delay`           | the hold, 16-bit little-endian                                                                  |
| Macro id          | `0` on every action except the last, where it is the macro's number                             |
| Repeat mode       | stop immediately → start type `1`; until any key → `2`; until the next key press → `3`; loop count → `4` |
| `frequency`       | the run count, on every action                                                                  |

Things that do not carry over to the R1 NK: a config can hold more macros than the mouse has slots (the R1 NK has one per button, six; the button a macro is written for decides the slot, not its id), and fields for features the mouse does not have should be skipped.

---

## Reading a Config

To build a document from the mouse a tool reads, in no required order: the button table, the active profile, the versions, the light, the link type, the config block, cid and mid, the receiver version, the DPI table, and the optional-feature mask. Each is a command in [PROTOCOL.md](PROTOCOL.md).

---

## Shared Configs

Saved configs can also be published to and imported from an online library of shared configs, listed by a configuration type, a category and tags. The service has these operations: list categories, list tags, list (search), detail, create, update, delete, import into the user's own library, like, and favourite. Listing categories, tags and configs does not need a sign-in; creating, importing, liking and deleting do. A config name is length-limited and checked against the user's existing names, and a description is limited to 120 characters. When an imported config has the same name as one the user already has, the tool asks whether to overwrite it, rename it, or skip it, with an "apply to all" option.

The request bodies of these operations were **not** read, so the exact fields of a shared config are not documented here.
