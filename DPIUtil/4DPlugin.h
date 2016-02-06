/* --------------------------------------------------------------------------------
 #
 #	4DPlugin.h
 #	source generated by 4D Plugin Wizard
 #	Project : DPIUtil
 #	author : miyako
 #	2016/02/04
 #
 # --------------------------------------------------------------------------------*/



// --- DPIUtil
void DPI_GET_INFORMATION(sLONG_PTR *pResult, PackagePtr pParams);
void DPI_Get_option(sLONG_PTR *pResult, PackagePtr pParams);
void DPI_SET_OPTION(sLONG_PTR *pResult, PackagePtr pParams);

#define DPI_WIN8DPISCALING_KEY (0)
#define DPI_LOGPIXELS_KEY (1)
#define DPI_DESKTOPDPIOVERRIDE_KEY (2)
#define TOTALBYTES    (8192)
#define BYTEINCREMENT (4096)