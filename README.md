# 4d-plugin-dpi-util

DPIUtil reads per-monitor display metrics on Windows (via `EnumDisplayMonitors`/`GetDeviceCaps`) and reads/writes the three per-user Windows DPI-scaling registry values under `HKEY_CURRENT_USER\Control Panel\Desktop`. It returns plain `Longint` values and text/longint arrays — there's no `Picture`/`Object` marshalling involved anywhere in this plugin.

| Command | Returns | Purpose |
|---|---|---|
| [`DPI GET INFORMATION`](#dpi-get-information) | *(none — out params)* | Physical size, resolution, and DPI for one monitor |
| [`DPI Get option`](#dpi-get-option) | Longint | Read a per-user Windows DPI registry value |
| [`DPI SET OPTION`](#dpi-set-option) | *(none)* | Write a per-user Windows DPI registry value |

**Command support:** Windows only (win32/win64). All three commands are compiled solely under `VERSIONWIN`; the release pipeline also builds a macOS bundle, but these commands have no macOS implementation.

---

## Requirements & platform notes

- **Windows command support only.** The release pipeline builds a macOS bundle, but none of these commands has a macOS code path.
- **`screen` defaults to monitor 1.** For `DPI GET INFORMATION`, omitting `screen` (or passing `0`, a negative number, or anything above `65535`) falls back to monitor `1` rather than raising an error.
- **Monitor numbering.** `screen` is a 1-based index into the order Windows' own `EnumDisplayMonitors` enumerates displays in — this is whatever order Windows itself assigns, not necessarily left-to-right or primary-first.
- **Failures are silent, not 4D errors.** Both an out-of-range `screen` and an unrecognized `option` code return zeroed/default results rather than raising an error — see [Error handling](#error-handling--troubleshooting) below before you assume a `0` means "the display doesn't have that dimension."
- **Registry changes may need a logon/restart to take effect.** `DPI SET OPTION` only writes the registry value; Windows itself decides when it re-reads that value (typically at logon), so writing a new value won't retroactively rescale an already-running session.

## Release maintenance

The commands above are Windows-only. The existing release pipeline nevertheless
builds Windows x64 and a universal arm64/x86_64 macOS bundle, merges them, signs
and notarizes the macOS package, and attaches ZIP and DMG assets. This lifecycle
does not add command support on macOS or change platform builds/dependencies.

1. Run **Bump version** on the desired branch, choosing patch, minor, or major.
   It validates and commits source metadata only, then non-force pushes only
   that branch with follow-tags disabled. It creates no tag and starts no Build.
   A concurrent branch update rejects the push; inspect it and rerun deliberately.
2. Run **Build** manually, using its branch selector (no workflow inputs).
   All checkouts use the immutable selected `github.sha`, not a moving branch/tag.
   Builds are not triggered by pushes, tags, or the bump workflow and are not
   restricted to `master`.
3. Build derives strict `X.Y.Z` from all six Xcode `MARKETING_VERSION` settings,
   checking every `CURRENT_PROJECT_VERSION` against that same version,
   coordinated with source `Info.plist` and `English.lproj/InfoPlist.strings`.
   Supported plist `$(MARKETING_VERSION)` / `${MARKETING_VERSION}` references
   remain intact, as do corresponding `CURRENT_PROJECT_VERSION` references.
   `CFBundleVersion` is absent from the source plist; if present it must also
   coordinate (literal or supported build variable). Neither dependency
   versions, 4D format versions, nor checked-in prebuilt bundles are bumped.

The old bump workflow explicitly promised to coordinate both Xcode settings,
but its implementation selected only `MARKETING_VERSION`, leaving all six
`CURRENT_PROJECT_VERSION` fields at `1.0.0` across successive bump commits.
They are not documented independent counters. The migration restores that
contract by aligning them and the stale localized `1.0` source strings to the
existing authoritative `1.0.3`, without incrementing the release version.
Invalid or drifted metadata now fails before building or bumping.

Publication is serialized repository-wide across branches. Authenticated,
validated, paginated release listing includes drafts; any existing same-tag
release or remote tag blocks publication. API, authentication, network, malformed
response, and later-page failures are errors, never evidence of absence.
Availability is rechecked after Windows/macOS builds, universal verification,
codesign verification, both accepted notarizations, and DMG stapling/validation.
Only then does a non-force push create `vX.Y.Z` at the exact selected SHA, verify
its remote target, POST a **new published non-prerelease** release with explicit
tag/SHA/name, and upload assets without clobber. No generated release notes are
requested (the prior release-note policy is unchanged).

There is no delete, update-existing, rollback, or automatic retry. A race, failed
POST, or upload can leave a tag, release, or some assets behind. Inspect remote
state manually and decide how to recover; rerunning the same version intentionally
fails closed rather than replacing/deleting partial state. Do not retry publication
blindly. Signing and notarization continue to use the existing secret names.

Local lifecycle regressions: `python3 -m unittest discover -s .github/tests -v`.
Workflow lint: `actionlint`.

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
- **Windows command support only.** Don't expect these commands to do anything on macOS, even though release packages include a macOS bundle.

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
