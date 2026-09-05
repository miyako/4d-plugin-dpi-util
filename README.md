# 4d-plugin-dpi-util

DPIUtil reads per-monitor display metrics on Windows (via `EnumDisplayMonitors`/`GetDeviceCaps`) and reads/writes the three per-user Windows DPI-scaling registry values under `HKEY_CURRENT_USER\Control Panel\Desktop`. It returns plain `Longint` values and text/longint arrays — there's no `Picture`/`Object` marshalling involved anywhere in this plugin.

| Command | Returns | Purpose |
|---|---|---|
| [`DPI GET INFORMATION`](#dpi-get-information) | *(none — out params)* | Physical size, resolution, and DPI for one monitor |
| [`DPI Get option`](#dpi-get-option) | Longint | Read a per-user Windows DPI registry value |
| [`DPI SET OPTION`](#dpi-set-option) | *(none)* | Write a per-user Windows DPI registry value |

**Platforms:** Windows only (win32/win64). All three commands are compiled solely under `VERSIONWIN`; there is no macOS build of this plugin.

---

## Requirements & platform notes

- **Windows only.** Nothing in this plugin has a macOS code path — don't expect it to build or run there.
- **`screen` defaults to monitor 1.** For `DPI GET INFORMATION`, omitting `screen` (or passing `0`, a negative number, or anything above `65535`) falls back to monitor `1` rather than raising an error.
- **Monitor numbering.** `screen` is a 1-based index into the order Windows' own `EnumDisplayMonitors` enumerates displays in — this is whatever order Windows itself assigns, not necessarily left-to-right or primary-first.
- **Failures are silent, not 4D errors.** Both an out-of-range `screen` and an unrecognized `option` code return zeroed/default results rather than raising an error — see [Error handling](#error-handling--troubleshooting) below before you assume a `0` means "the display doesn't have that dimension."
- **Registry changes may need a logon/restart to take effect.** `DPI SET OPTION` only writes the registry value; Windows itself decides when it re-reads that value (typically at logon), so writing a new value won't retroactively rescale an already-running session.

---

## DPI GET INFORMATION

### Syntax

```
DPI GET INFORMATION ( keyNames ; keyValues ; screen )
```

| Parameter | Type | Description |
|---|---|---|
| `keyNames` | ARRAY TEXT | *(out)* Filled with 6 key names, in this fixed order: `horzsize`, `vertsize`, `horzres`, `vertres`, `logpixelsx`, `logpixelsy` |
| `keyValues` | ARRAY LONGINT | *(out)* Filled with the corresponding values, same order/index as `keyNames` |
| `screen` | LONGINT | *(in, optional)* 1-based monitor index. Omitted, `0`, or out of range → defaults to `1` |
| Result | — | No return value; results are written into `keyNames`/`keyValues` by reference |

### Description

Internally this calls Windows' `EnumDisplayMonitors` to find the requested monitor, then reads six values off its device context with `GetDeviceCaps`:

- `horzsize` / `vertsize` — physical width/height of the display in millimeters (`HORZSIZE`/`VERTSIZE`)
- `horzres` / `vertres` — resolution in pixels (`HORZRES`/`VERTRES`)
- `logpixelsx` / `logpixelsy` — the logical DPI along each axis (`LOGPIXELSX`/`LOGPIXELSY`)

If `screen` doesn't correspond to an actual connected monitor, or the system fails to obtain a device context at all, all six `keyValues` come back as `0` — there's no 4D error raised in that case, so check for an all-zero result rather than expecting an exception.

### Example

```4d
ARRAY TEXT($keyNames;0)
ARRAY LONGINT($keyValues;0)

DPI GET INFORMATION($keyNames;$keyValues;1)  //primary/first-enumerated monitor

For ($i;1;Size of array($keyNames))
	ALERT($keyNames{$i}+" = "+String($keyValues{$i}))
End for
```

```4d
 //loop over however many monitors respond with non-zero data
ARRAY TEXT($keyNames;0)
ARRAY LONGINT($keyValues;0)
$screen:=1

Repeat
	DPI GET INFORMATION($keyNames;$keyValues;$screen)
	$total:=0
	For ($i;1;Size of array($keyValues))
		$total:=$total+$keyValues{$i}
	End for
	If ($total>0)
		 //keyValues{4}=vertres, keyValues{6}=logpixelsy, per the fixed key order above
		ALERT("Monitor "+String($screen)+": "+String($keyValues{4})+"px tall @ "+String($keyValues{6})+" DPI")
	End if
	$screen:=$screen+1
Until ($total=0)
```

---

## DPI Get option

### Syntax

```
$result:=DPI Get option ( option )
```

| Parameter | Type | Description |
|---|---|---|
| `option` | LONGINT | One of `DPI_WIN8DPISCALING_KEY` (`0`), `DPI_LOGPIXELS_KEY` (`1`), `DPI_DESKTOPDPIOVERRIDE_KEY` (`2`) |
| Result | LONGINT | The current value stored at the corresponding registry entry under `HKEY_CURRENT_USER\Control Panel\Desktop`; `0` if `option` isn't one of the three constants above, or if the registry value doesn't exist |

### Description

Maps directly to one registry value each:

| Constant | Registry value |
|---|---|
| `DPI_WIN8DPISCALING_KEY` | `Control Panel\Desktop\Win8DpiScaling` |
| `DPI_LOGPIXELS_KEY` | `Control Panel\Desktop\LogPixels` |
| `DPI_DESKTOPDPIOVERRIDE_KEY` | `Control Panel\Desktop\DesktopDPIOverride` |

A `0` result is ambiguous: it means either "the value is genuinely `0`," "the value doesn't exist," or "`option` wasn't recognized." There's no separate error signal to tell these apart.

### Example

From the plugin's own README:

```4d
$v1:=DPI Get option (DPI_LOGPIXELS_KEY)
$v2:=DPI Get option (DPI_DESKTOPDPIOVERRIDE_KEY)
$v3:=DPI Get option (DPI_WIN8DPISCALING_KEY)
```

```4d
 //read all three current settings at once
ARRAY LONGINT($options;3)
$options{1}:=DPI Get option (DPI_WIN8DPISCALING_KEY)
$options{2}:=DPI Get option (DPI_LOGPIXELS_KEY)
$options{3}:=DPI Get option (DPI_DESKTOPDPIOVERRIDE_KEY)
```

---

## DPI SET OPTION

### Syntax

```
DPI SET OPTION ( option ; value )
```

| Parameter | Type | Description |
|---|---|---|
| `option` | LONGINT | Same three constants as [`DPI Get option`](#dpi-get-option) |
| `value` | LONGINT | Value to write to the corresponding registry entry |
| Result | — | No return value |

### Description

Writes `value` as a `DWORD` to the same three `HKEY_CURRENT_USER\Control Panel\Desktop` entries documented under [`DPI Get option`](#dpi-get-option), creating the key if it doesn't already exist. There's no validation of `value` against what Windows actually accepts for that setting — an out-of-range value will be written as-is. If `option` isn't one of the three known constants, the command does nothing, silently.

### Example

```4d
 //disable Windows 8.1-style automatic per-monitor DPI scaling for this user
DPI SET OPTION (DPI_WIN8DPISCALING_KEY;1)
```

```4d
 //write all three settings, then confirm by reading them back
DPI SET OPTION (DPI_WIN8DPISCALING_KEY;0)
DPI SET OPTION (DPI_LOGPIXELS_KEY;96)
DPI SET OPTION (DPI_DESKTOPDPIOVERRIDE_KEY;0)

ALERT("LogPixels is now: "+String(DPI Get option (DPI_LOGPIXELS_KEY)))
```

---

## Error handling & troubleshooting

- **Unknown `screen` index returns all zeros, not an error.** If `screen` doesn't correspond to a real, currently-connected monitor, `DPI GET INFORMATION` fills `keyValues` with `0`s and raises nothing — check for an all-zero result rather than expecting a 4D error.
- **Unrecognized `option` code is silently ignored.** `DPI Get option` returns `0`; `DPI SET OPTION` does nothing. Neither raises an error, so a typo in the constant won't surface as a bug until the values look wrong.
- **A `0` from `DPI Get option` is ambiguous.** It can mean "the setting is `0`," "the setting doesn't exist yet in the registry," or "`option` wasn't recognized" — the command doesn't distinguish these.
- **`DPI SET OPTION` writes may not take effect immediately.** These are read by Windows at logon; a running session generally won't rescale until the user logs off/on (or, for some of these keys, restarts Explorer).
- **Windows only.** Don't expect these commands to do anything on macOS — there is no macOS build.

---

## Quick reference

```4d
 //read current settings
$win8Scaling:=DPI Get option (DPI_WIN8DPISCALING_KEY)
$logPixels:=DPI Get option (DPI_LOGPIXELS_KEY)
$override:=DPI Get option (DPI_DESKTOPDPIOVERRIDE_KEY)

 //write new settings
DPI SET OPTION (DPI_LOGPIXELS_KEY;96)

 //inspect monitor 1
ARRAY TEXT($keyNames;0)
ARRAY LONGINT($keyValues;0)
DPI GET INFORMATION($keyNames;$keyValues;1)
```
