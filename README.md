# 4d-plugin-dpi-util
Get information about the DPI on Windows

### Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|||<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|

### Version

<img src="https://cloud.githubusercontent.com/assets/1725068/18940649/21945000-8645-11e6-86ed-4a0f800e5a73.png" width="32" height="32" /> <img src="https://cloud.githubusercontent.com/assets/1725068/18940648/2192ddba-8645-11e6-864d-6d5692d55717.png" width="32" height="32" />


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
