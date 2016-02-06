# 4d-plugin-dpi-util
Get information about the DPI on Windows

##Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|🚫|🚫|🆗|🆗|

Commands
---

```c
// --- DPIUtil
DPI_GET_INFORMATION
DPI_Get_option
DPI_SET_OPTION
```

Examples
---

Read/write [Window 8.1 DPI registry keys](https://msdn.microsoft.com/library/dn528846.aspx). 

```
$v1:=DPI Get option (DPI_LOGPIXELS_KEY)
$v2:=DPI Get option (DPI_DESKTOPDPIOVERRIDE_KEY)
$v3:=DPI Get option (DPI_WIN8DPISCALING_KEY)
```
