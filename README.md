# 4d-plugin-dpi-util
Get information about the DPI on Windows

### Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|||<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|

### Version

<img src="https://cloud.githubusercontent.com/assets/1725068/18940649/21945000-8645-11e6-86ed-4a0f800e5a73.png" width="32" height="32" /> <img src="https://cloud.githubusercontent.com/assets/1725068/18940648/2192ddba-8645-11e6-864d-6d5692d55717.png" width="32" height="32" />

Related proejct: https://github.com/miyako/4d-plugin-get-dpi/

## Syntax

```
DPI GET INFORMATION (keyNames;keyValues;screen)
```

Parameter|Type|Description
------------|------------|----
keyNames|ARRAY TEXT|``horzsize``, ``vertsize``, ``horzres``, ``vertres``, ``logpixelsx``, ``logpixelsy``
keyValues|ARRAY LONGINT|
screen|LONGINT|screen number

See [EnumDisplayMonitors](https://msdn.microsoft.com/en-us/library/windows/desktop/dd162610(v=vs.85).aspx).

```
value:=DPI Get option (option)
DPI SET OPTION (option;value)
```

Parameter|Type|Description
------------|------------|----
option|LONGINT|``DPI_WIN8DPISCALING_KEY``, ``DPI_LOGPIXELS_KEY``, ``DPI_DESKTOPDPIOVERRIDE_KEY``
value|LONGINT|

Read or write the corresponding registry value for ``HKEY_CURRENT_USER``.

```
Control Panel\Desktop\Win8DpiScaling
Control Panel\Desktop\LogPixels
Control Panel\Desktop\DesktopDPIOverride
```

Examples
---

Read/write [Window 8.1 DPI registry keys](https://msdn.microsoft.com/library/dn528846.aspx). 

```
$v1:=DPI Get option (DPI_LOGPIXELS_KEY)
$v2:=DPI Get option (DPI_DESKTOPDPIOVERRIDE_KEY)
$v3:=DPI Get option (DPI_WIN8DPISCALING_KEY)
```
