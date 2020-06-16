from IPython import get_ipython
get_ipython().magic('reset -sf')

import os
import osr
import ogr
import gdal
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import rasterio
import glob

from rasterio.plot import show
from rasterio.mask import mask
from rasterio.features import shapes # for raster to polygon

from shapely.geometry import mapping
from shapely.geometry import shape
from shapely.geometry import Point, LineString

import math

from xml.etree import ElementTree
# from xml.dom import minidom
from scipy.interpolate import griddata #for grid interpolation
from scipy import ndimage # for image filtering
from scipy import signal # for convolution filter
#import cv2

from skimage import measure
#from skimage import graph 
from skimage.future import graph # for rag
from skimage import segmentation # for superpixels
from skimage import color # for labeling image
from skimage import filters # for Otsu thesholding
from skimage import transform # for rotation

from itertools import compress # for fast indexing

def read_band_image(band, path):
    """
    This function takes as input the Sentinel-2 band name and the path of the 
    folder that the images are stored, reads the image and returns the data as
    an array
    input:   band           string            Sentinel-2 band name
             path           string            path of the folder
    output:  data           array (n x m)     array of the band image
             spatialRef     string            projection 
             geoTransform   tuple             affine transformation coefficients
             targetprj                        spatial reference
    """
    fname = os.path.join(path,'*B'+band+'.jp2')
    img = gdal.Open(glob.glob(fname)[0])
    data = np.array(img.GetRasterBand(1).ReadAsArray())
    spatialRef = img.GetProjection()
    geoTransform = img.GetGeoTransform()
    targetprj = osr.SpatialReference(wkt = img.GetProjection())
    return data, spatialRef, geoTransform, targetprj

def read_sun_angles(path):
    """
    This function reads the xml-file of the Sentinel-2 scene and extracts an
    array with sun angles, as these vary along the scene.
    """
    fname = os.path.join(path,'MTD_TL.xml')
    dom = ElementTree.parse(glob.glob(fname)[0])
    root = dom.getroot()

    # image dimensions
    for meta in root.iter('Size'):
        res = float(meta.get('resolution'))
        if res==10: # take 10 meter band
            mI = float(meta[0].text)
            nI = float(meta[1].text)
    
    # get Zenith array
    Zenith = root[1][1][0][0][2]
    Zn = get_array_from_xml(Zenith)
    znSpac = float(root[1][1][0][0][0].text)
    znSpac = np.stack((znSpac, float(root[1][1][0][0][1].text)),0)
    znSpac = np.divide(znSpac,10) # transform from meters to pixels
    
    zi = np.linspace(0-10,mI+10,np.size(Zn,axis=0))
    zj = np.linspace(0-10,nI+10,np.size(Zn,axis=1))
    Zi,Zj = np.meshgrid(zi,zj)
    Zij = np.dstack([Zi, Zj]).reshape(-1, 2)
    del zi,zj,Zi,Zj,znSpac
    
    iGrd = np.arange(0,mI)
    jGrd = np.arange(0,nI)
    Igrd, Jgrd = np.meshgrid(iGrd, jGrd)

    Zn = griddata(Zij,Zn.reshape(-1),(Igrd,Jgrd), method="linear")
    
    # get Azimuth array
    Azimuth = root[1][1][0][1][2]
    Az = get_array_from_xml(Azimuth)  
    azSpac = float(root[1][1][0][1][0].text)
    azSpac = np.stack((azSpac, float(root[1][1][0][1][1].text)),0)  

    ai = np.linspace(0-10,mI+10,np.size(Az,axis=0))
    aj = np.linspace(0-10,nI+10,np.size(Az,axis=1))
    Ai,Aj = np.meshgrid(ai,aj)
    Aij = np.dstack([Ai, Aj]).reshape(-1, 2)
    del ai,aj,Ai,Aj,azSpac
    
    Az = griddata(Aij,Az.reshape(-1),(Igrd,Jgrd), method="linear")
    del Igrd,Jgrd,Zij,Aij 
    return Zn, Az

def read_view_angles(path):
    """
    This function reads the xml-file of the Sentinel-2 scene and extracts an
    array with sun angles, as these vary along the scene.
    """
    fname = os.path.join(path,'MTD_TL.xml')
    dom = ElementTree.parse(glob.glob(fname)[0])
    root = dom.getroot()

    # image dimensions
    for meta in root.iter('Size'):
        res = float(meta.get('resolution'))
        if res==10: # take 10 meter band
            mI = float(meta[0].text)
            nI = float(meta[1].text)
    # get coarse grids
    for grd in root.iter('Viewing_Incidence_Angles_Grids'):
        bid = float(grd.get('bandId'))
        if bid==4: # take band 4
            Zarray = get_array_from_xml(grd[0][2])
            Aarray = get_array_from_xml(grd[1][2])
            if 'Zn' in locals():
                Zn = np.nanmean(np.stack((Zn,Zarray),axis=2), axis=2)
                Az = np.nanmean(np.stack((Az,Aarray),axis=2), axis=2)
            else:
                Zn = Zarray
                Az = Aarray
            del Aarray,Zarray
            
    # upscale to 10 meter resolution    
    zi = np.linspace(0-10,mI+10,np.size(Zn,axis=0))
    zj = np.linspace(0-10,nI+10,np.size(Zn,axis=1))
    Zi,Zj = np.meshgrid(zi,zj)
    Zij = np.dstack([Zi, Zj]).reshape(-1, 2)
    del zi,zj,Zi,Zj
    
    iGrd = np.arange(0,mI)
    jGrd = np.arange(0,nI)
    Igrd, Jgrd = np.meshgrid(iGrd, jGrd)
    Zok = ~np.isnan(Zn)
    Zn = griddata(Zij[Zok.reshape(-1),:],Zn[Zok],(Igrd,Jgrd), method="linear")
    
    ai = np.linspace(0-10,mI+10,np.size(Az,axis=0))
    aj = np.linspace(0-10,nI+10,np.size(Az,axis=1))
    Ai,Aj = np.meshgrid(ai,aj)
    Aij = np.dstack([Ai, Aj]).reshape(-1, 2)
    del ai,aj,Ai,Aj
    
    Aok = ~np.isnan(Az) # remove NaN values from interpolation
    Az = griddata(Aij[Aok.reshape(-1),:],Az[Aok],(Igrd,Jgrd), method="linear")
    del Igrd,Jgrd,Zij,Aij 
    return Zn, Az

def get_array_from_xml(treeStruc):
    """
    Arrays within a xml structure are given line per line
    Output is an array
    """
    for i in range(0, len(treeStruc)):
        Trow = [float(s) for s in treeStruc[i].text.split(' ')]
        if i==0:
            Tn = Trow
        elif i==1:
            Trow = np.stack((Trow, Trow),0)
            Tn = np.stack((Tn, Trow[1,:]),0)
        else:
            # Trow = np.stack((Trow, Trow),0)
            # Tn = np.concatenate((Tn, [Trow[1,:]]),0)
            Tn = np.concatenate((Tn, [Trow]),0)
    return Tn

def RGB2HSI(R,G,B):
    """
    Transform Red Green Blue arrays to Hue Saturation Intensity arrays
    """
    Red = np.float64(R)/2**16
    Green = np.float64(G)/2**16
    Blue = np.float64(B)/2**16
    
    Hue = np.copy(Red)
    Sat = np.copy(Red)
    Int = np.copy(Red)
    
    # See Tsai, IEEE Trans. Geo and RS, 2006.
    # from Pratt, 1991, Digital Image Processing, Wiley
    Tsai = np.array([(1/3,1/3,1/3), \
                     (-math.sqrt(6)/6,-math.sqrt(6)/6,-math.sqrt(6)/3), \
                     (1/math.sqrt(6),2/-math.sqrt(6),0)])
    
    for i in range(0, Red.shape[0]):
        for j in range(0, Red.shape[1]):
            hsi = np.matmul(Tsai, np.array([ [Red[i][j]], [Green[i][j]] , [Blue[i][j]] ]))
            Int[i][j] = hsi[0]
            Sat[i][j] = math.sqrt(hsi[1]**2 + hsi[2]**2)
            Hue[i][j] = math.atan2(hsi[1],hsi[2])
            
    return Hue, Sat, Int

def pca(X):
    # Data matrix X, assumes 0-centered
    n, m = X.shape
    assert np.allclose(X.mean(axis=0), np.zeros(m))
    # Compute covariance matrix
    C = np.dot(X.T, X) / (n-1)
    # Eigen decomposition
    eigen_vals, eigen_vecs = np.linalg.eig(C)
    # Project X onto PC space
    X_pca = np.dot(X, eigen_vecs)
    return X_pca

def ruffenacht(R,G,B,NIR):
    """
    Transform Red Green Blue NIR to shadow intensities/probabilities
    """
    ae = 1e+1 
    be = 5e-1
    
    NanBol = R==0 # boolean array with no data
    
    Red = np.float64(R) # /2**16
    Red[~NanBol] = np.interp(Red[~NanBol], (Red[~NanBol].min(), Red[~NanBol].max()), (0, +1))
    Red[NanBol] = 0
    Green = np.float64(G) # /2**16
    Green[~NanBol] = np.interp(Green[~NanBol], (Green[~NanBol].min(), Green[~NanBol].max()), (0, +1))
    Green[NanBol] = 0
    Blue = np.float64(B) # /2**16
    Blue[~NanBol] = np.interp(Blue[~NanBol], (Blue[~NanBol].min(), Blue[~NanBol].max()), (0, +1))
    Blue[NanBol] = 0
    Near = np.float64(NIR) # /2**16 
    Near[~NanBol] = np.interp(Near[~NanBol], (Near[~NanBol].min(), Near[~NanBol].max()), (0, +1))
    Near[NanBol] = 0
    del R,G,B,NIR
    
    Fk = np.amax(np.stack((Red,Green,Blue),axis=2),axis=2)
    F = np.divide(np.clip(Fk, 0,2) ,2) # (10), see Fedembach 2010
    L = np.divide(Red+Green+Blue, 3) # (4), see Fedembach 2010
    del Red,Green,Blue,Fk
    
    Dvis = S_curve(1-L,ae,be)
    Dnir = S_curve(1-Near,ae,be) # (5), see Fedembach 2010
    D = np.multiply(Dvis,Dnir) # (6), see Fedembach 2010
    del L,Near,Dvis,Dnir
    
    M = np.multiply(D,(1-F)) 
    return M
    
def S_curve(x,a,b):
    fe = -a*(x-b)
    fx = np.divide(1,1+np.exp(fe))
    del fe,x
    return fx

def getShadowPolygon(M,sizPix,thres):
    mn = np.ceil(np.divide(np.nanprod(M.shape),sizPix));
    SupPix = segmentation.slic(M, sigma = 1, 
                  n_segments=mn, 
                  compactness=0.010) # create super pixels
    
#    g = graph.rag_mean_color(M, SupPix) # create region adjacency graph
#    mc = np.empty(len(g))
#    for n in g:
#        mc[n] = g.nodes[n]['mean color'][1]
#    graphCut = graph.cut_threshold(SupPix, g, thres)
#    meanIm = color.label2rgb(graphCut, M, kind='avg')
    meanIm = color.label2rgb(SupPix, M, kind='avg')
    sturge = 1.6*(math.log2(mn)+1)
    values, base = np.histogram(np.reshape(meanIm,-1), 
                                bins=np.int(np.ceil(sturge)))
    dips = findValley(values,base,2)
    val = max(dips)
#    val = filters.threshold_otsu(meanIm)
#    val = filters.threshold_yen(meanIm)
    imSeparation = meanIm > val
    labels = measure.label(imSeparation, background=0) 
    labels = np.int16(labels) # so it can be used for the boundaries extraction
    return labels, SupPix

def getShadows(M,siz,loop):
    mn = M.size;
    Mmed = M
    for i in range(loop):
        Mmed = ndimage.median_filter(M, size=siz)
    sturge = 1.6*(math.log2(mn)+1)
    values, base = np.histogram(np.reshape(Mmed,-1), 
                                bins=np.int(np.ceil(sturge)))    
    dips = findValley(values,base,2)
    val = max(dips)
    imSeparation = Mmed > val
    labels = measure.label(imSeparation, background=0) 
    return labels

def findValley(values,base,neighbors):
    """
    A valley is a point which has "n" consecuative higher values on both sides
    """
    for i in range(neighbors):
        if i == 0:
            wallP = np.roll(values, +(i+1))
            wallM = np.roll(values, -(i+1))
        else:
            wallP = np.vstack((wallP, np.roll(values, +(i+1))))
            wallM = np.vstack((wallM, np.roll(values, -(i+1))))            
    if neighbors>1:
        concavP = np.all(np.sign(np.diff(wallP, n=1, axis=0))==+1, axis=0)
        concavM = np.all(np.sign(np.diff(wallM, n=1, axis=0))==+1, axis=0)
    selec = np.all(np.vstack((concavP,concavM)),axis=0)    
    selec = selec[neighbors-1:-(neighbors+1)]
    idx = base[neighbors-1:-(neighbors+2)]
    dips = idx[selec]
    #walls = np.amin(sandwich,axis=0)
    #selec = values<walls    
    return dips
    

def castOrientation(I,sunZn,sunAz):
#    kernel = np.array([[-1, 0, +1], [-2, 0, +2], [-1, 0, +1]])
    kernel = np.array([[17], [61], [17]])*np.array([-1, 0, 1])/95
    Idx = ndimage.convolve(I, kernel) # steerable filters
    Idy = ndimage.convolve(I, np.flip(np.transpose(kernel),axis=0))
    Ican = np.multiply(np.cos(np.radians(sunAz)),Idy) - np.multiply(np.sin(np.radians(sunAz)),Idx)
    return Ican

def bboxBoolean(img):
    rows = np.any(img, axis=1)
    cols = np.any(img, axis=0)
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]

    return rmin, rmax, cmin, cmax

def listOccluderAndCasted(labels, sunZn, sunAz, geoTransform):
    msk = labels>1
    labels = labels.astype(np.int32)
    mskOrient = castOrientation(msk.astype(np.float),sunZn,sunAz)
    mskOrient = np.sign(mskOrient)
    #makeGeoIm(mskOrient,subTransform,crs,"polyRidges.tif")
    
    castList = []
    for shp, val in shapes(labels, mask=msk, connectivity=8):
    #        coord = shp["coordinates"]
    #        coord = np.uint16(np.squeeze(np.array(coord[:])))    
    #    if val!=0:
        if val==48:    
            # get ridge coordinates
            polygoon = shape(shp)
            polyRast = labels==val # select the polygon
            polyInnr = ndimage.binary_erosion(polyRast, np.ones((3,3), dtype=bool))
            polyBoun = np.logical_xor(polyRast, polyInnr)
            polyWhe = np.nonzero(polyBoun)
            ridgIdx = mskOrient[polyWhe[0],polyWhe[1]]==1
            ridgeI = polyWhe[0][ridgIdx]
            ridgeJ = polyWhe[1][ridgIdx]    
            del polyRast, polyInnr, polyBoun, polyWhe, ridgIdx
        
            for x in ridgeI:
                castLine = LineString([[ridgeJ[x],ridgeI[x]],
                            [ridgeJ[x] - (math.sin(math.radians(sunAz[ridgeI[x]][ridgeJ[x]]))*1e4), 
                             ridgeI[x] + (math.cos(math.radians(sunAz[ridgeI[x]][ridgeJ[x]]))*1e4)]])
                castEnd = polygoon.intersection(castLine)
                if castEnd.geom_type == 'LineString':
                    castEnd = castEnd.coords[:]
                elif castEnd.geom_type == 'MultiLineString':
                    # castEnd = [list(x.coords) for x in list(castEnd)]
                    cEnd = []
                    for m in list(castEnd):
                        cEnd = cEnd + m.coords[:]
                    castEnd = cEnd
                    del m, cEnd
                elif castEnd.geom_type == 'GeometryCollection':
                    cEnd = []
                    for m in range(len(castEnd)):
                        cEnd = cEnd + castEnd[m].coords[:]
                    castEnd = cEnd
                    del m, cEnd
                else:
                    print('something went wrong?')
                
                # if empty
                if len(castEnd)>1:
                # if len(castEnd.coords[:])>1:
                    # find closest intersection
                    occluder = Point(ridgeJ[x],ridgeI[x])
                    #dists = [Point(c).distance(occluder) for c in castEnd.coords]
                    dists = [Point(c).distance(occluder) for c in castEnd]
                    dists = [float('Inf') if  i == 0 else i for i in dists]
                    castIdx = dists.index(min(dists)) 
                    casted = castEnd[castIdx]
                    
                    # transform to UTM and append to array
                    castLine = np.array([ridgeI[x], ridgeJ[x], casted[1], casted[0], 
                                         sunAz[ridgeI[x]][ridgeJ[x]] , 
                                         sunZn[ridgeI[x]][ridgeJ[x]] ])
                    castList.append(castLine)
                    del dists, occluder, castIdx, casted
                del castLine, castEnd
    return castList

def makeGeoIm(I,R,crs,fName):
    drv = gdal.GetDriverByName("GTiff") # export image
    # type
    if I.dtype=='float64':
        ds = drv.Create(fName, I.shape[1], I.shape[0], 6, gdal.GDT_Float64)
    else:
        ds = drv.Create(fName, I.shape[1], I.shape[0], 6, gdal.GDT_Int32)
    ds.SetGeoTransform(subTransform)
    ds.SetProjection(crs)
    ds.GetRasterBand(1).WriteArray(I)
    ds = None
    del ds    



datPath = '/Users/Alten005/surfdrive/Eratosthenes/Denali/' 
# s2Path = 'Data/S2A_MSIL1C_20180225T214531_N0206_R129_T05VNL_20180225T232042/'
# fName = 'T05VNL_20180225T214531_B'
s2Path = 'Data/S2A_MSIL1C_20180225T214531_N0206_R129_T05VPL_20180225T232042/'
fName = 'T05VPL_20180225T214531_B'
# s2Path = 'Data/S2A_MSIL1C_20180225T214531_N0206_R129_T05VPK_20180225T232042/'
# fName = 'T05VPK_20180225T214531_B'

s2Path = datPath + s2Path

# read imagery of the different bands
(B2, crs, geoTransform, targetprj) = read_band_image('02', s2Path)
(B3, crs, geoTransform, targetprj) = read_band_image('03', s2Path)
(B4, crs, geoTransform, targetprj) = read_band_image('04', s2Path)
(B8, crs, geoTransform, targetprj) = read_band_image('08', s2Path)

mI = np.size(B2,axis=0)
nI = np.size(B2,axis=1)

# reduce image space, so it fit in memory
minI = 6000
maxI = 8000
B2 = B2[minI:maxI,minI:maxI]
B3 = B3[minI:maxI,minI:maxI]
B4 = B4[minI:maxI,minI:maxI]
B8 = B8[minI:maxI,minI:maxI]

subTransform = (geoTransform[0]+minI*geoTransform[1]+minI*geoTransform[2], 
                geoTransform[1], geoTransform[2], 
                geoTransform[3]+minI*geoTransform[4]+minI*geoTransform[5], 
                geoTransform[4], geoTransform[5])

# transform to shadow image
M = ruffenacht(B2,B3,B4,B8)
makeGeoIm(M,subTransform,crs,"ruffenacht.tif")
del B2,B3,B4,B8


# classify into regions
siz = 5
loop = 500
labels = getShadows(M,siz,loop)
makeGeoIm(labels,subTransform,crs,"schur.tif")

# find self-shadow and cast-shadow
(sunZn,sunAz) = read_sun_angles(s2Path)
sunZn = sunZn[minI:maxI,minI:maxI]
sunAz = sunAz[minI:maxI,minI:maxI]

castList = listOccluderAndCasted(labels, sunZn, sunAz, subTransform)

msk = labels>1
labels = labels.astype(np.int32)
mskOrient = castOrientation(msk.astype(np.float),sunZn,sunAz)
mskOrient = np.sign(mskOrient)
#makeGeoIm(mskOrient,subTransform,crs,"polyRidges.tif")

castList = [] # using rasterio.features.shape
for shp, val in shapes(labels, mask=msk, connectivity=8):
#        coord = shp["coordinates"]
#        coord = np.uint16(np.squeeze(np.array(coord[:])))    
#    if val!=0:
    if val==48:    
        # get ridge coordinates
        polygoon = shape(shp)
        polyRast = labels==val # select the polygon
        polyInnr = ndimage.binary_erosion(polyRast, np.ones((3,3), dtype=bool))
        polyBoun = np.logical_xor(polyRast, polyInnr)
        polyWhe = np.nonzero(polyBoun)
        ridgIdx = mskOrient[polyWhe[0],polyWhe[1]]==1
        ridgeI = polyWhe[0][ridgIdx]
        ridgeJ = polyWhe[1][ridgIdx]    
    #    polyIJ = list(zip(polyWhe[0][ridgIdx], polyWhe[1][ridgIdx]))
    #    ridges.append(polyIJ)
        del polyRast, polyInnr, polyBoun, polyWhe, ridgIdx
    
        for x in ridgeI:
            castLine = LineString([[ridgeJ[x],ridgeI[x]],
                        [ridgeJ[x] - (math.sin(math.radians(sunAz[ridgeI[x]][ridgeJ[x]]))*1e4), 
                         ridgeI[x] + (math.cos(math.radians(sunAz[ridgeI[x]][ridgeJ[x]]))*1e4)]])
            castEnd = polygoon.intersection(castLine)
            # if empty
            if len(castEnd.coords[:])>1:
                # find closest intersection
                occluder = Point(ridgeJ[x],ridgeI[x])
                dists = [Point(c).distance(occluder) for c in castEnd.coords]
                dists = [float('Inf') if  i == 0 else i for i in dists]
                castIdx = dists.index(min(dists)) 
                casted = castEnd.coords[castIdx]
                
                # transform to UTM and append to array
                castLine = np.array([ridgeI[x], ridgeJ[x], casted[1], casted[0], 
                                     sunAz[ridgeI[x]][ridgeJ[x]] , 
                                     sunZn[ridgeI[x]][ridgeJ[x]] ])
                castList.append(castLine)
                del dists, occluder, castIdx, casted
            del castLine, castEnd
    # get polygon
#    polygons.append(polygoon)

# walk through all polygons
i = 48
j = 1

polygoon = polygons[i]
ridgeIJ = ridges[i]
ridgeI = [x[0] for x in ridgeIJ]
ridgeJ = [x[1] for x in ridgeIJ]
ridgeAzi = sunAz[ridgeI,ridgeJ]




selec = labels==48 # select a polygon
selec = ndimage.binary_dilation(selec, np.ones((5,5), dtype=bool))# create extra space at the borders
(rowMin, rowMax, colMin, colMax) = bboxBoolean(selec)
subIm = M[rowMin:rowMax,colMin:colMax]
subLb = selec[rowMin:rowMax,colMin:colMax]
subSel = subLb
subOr = mskOrient[rowMin:rowMax,colMin:colMax]
subLb = subLb.astype(np.int16)
subLb[subSel] = 48
shp = shapes(subLb, mask=subSel, connectivity=8)
subRot = np.mean(sunAz[colMin:colMax,rowMin:rowMax])

subIm = transform.rotate(subIm,subRot+180, resize=True)
subLb = transform.rotate(subLb,subRot+180, resize=True)

i = 50
sweepIm = subIm[:,i]
sweepLb = subLb[:,i]

Mcan = castOrientation(M,sunZn,sunAz) 

Mcan = castOrientation(msk,sunZn,sunAz) 
Mcan[Mcan<0] = 0
makeGeoIm(Mcan,subTransform,crs,"shadowRidges.tif")

# use azimuth angle to find selfshadow border


#processed_image = cv2.filter2D(image,-1,kernel)

(viwZn,viwAz) = read_view_angles(s2Path)
viwZn = viwZn[minI:maxI,minI:maxI]
viwAz = viwAz[minI:maxI,minI:maxI]



fig, ax = plt.subplots()
im = ax.imshow(viwZn)
fig.colorbar(im)
plt.show()




# create HSI bands
# (H,S,I) = RGB2HSI(B2,B3,B4)

# normalized saturation-value difference index
# NSVDI = (S-I)/(S+I) # following Ma et al. 2008

# Mixed property-based shadow index (MPSI)
# MPSI = (H-I)*(B3-B4) # following Han et al. 2018

# 

# plt.imshow(MPSI)
# plt.show()


# 
# SI = (PC1)# following Hui et al. 2013




