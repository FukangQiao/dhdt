import os
import numpy as np
import matplotlib.pyplot as plt

from osgeo import ogr, osr, gdal
from sklearn.neighbors import NearestNeighbors

from eratosthenes.generic.handler_s2 import meta_S2string
from eratosthenes.generic.mapping_tools import RefTrans, pix2map, map2pix, \
    castOrientation
from eratosthenes.generic.mapping_io import makeGeoIm, read_geo_image

from eratosthenes.preprocessing.read_s2 import read_band_s2, read_sun_angles_s2
from eratosthenes.preprocessing.shadow_geometry import medianFilShadows, \
    sturge, labelOccluderAndCasted
from eratosthenes.preprocessing.shadow_transforms import ruffenacht
from eratosthenes.preprocessing.handler_multispec import \
    create_caster_casted_list_from_polygons

from eratosthenes.processing.coregistration import coregister, get_coregistration

datPath = '/Users/Alten005/surfdrive/Eratosthenes/Denali/' 
#s2Path = 'Data/S2A_MSIL1C_20180225T214531_N0206_R129_T05VPL_20180225T232042/'
#fName = 'T05VPL_20180225T214531_B'

s2Path = ('Data/S2A_MSIL1C_20180225T214531_N0206_R129_T05VNK_20180225T232042/',
          'Data/S2B_MSIL1C_20190225T214529_N0207_R129_T05VNK_20190226T010218/',
          'Data/S2A_MSIL1C_20200225T214531_N0209_R129_T05VNK_20200225T231600/')
fName = ('T05VNK_20180225T214531_B', 'T05VNK_20190225T214529_B', 'T05VNK_20200225T214531_B')

# do a subset of the imagery
minI = 4000
maxI = 6000
minJ = 4000
maxJ = 6000

bbox = (minI, maxI, minJ, maxJ)

for i in range(len(s2Path)):
    sen2Path = datPath + s2Path[i]
    (S2time,S2orbit,S2tile) = meta_S2string(s2Path[i])
    
    # read imagery of the different bands
    (B2, crs, geoTransform, targetprj) = read_band_S2('02', sen2Path)
    (B3, crs, geoTransform, targetprj) = read_band_S2('03', sen2Path)
    (B4, crs, geoTransform, targetprj) = read_band_S2('04', sen2Path)
    (B8, crs, geoTransform, targetprj) = read_band_S2('08', sen2Path)
    
    mI = np.size(B2,axis=0)
    nI = np.size(B2,axis=1)
    
    # reduce image space, so it fit in memory
    B2 = B2[minI:maxI,minJ:maxJ]
    B3 = B3[minI:maxI,minJ:maxJ]
    B4 = B4[minI:maxI,minJ:maxJ]
    B8 = B8[minI:maxI,minJ:maxJ]
    
    subTransform = RefTrans(geoTransform,minI,minJ) # create georeference for subframe
    subM = np.size(B2,axis=0)
    subN = np.size(B2,axis=1)    
    # transform to shadow image
    M = ruffenacht(B2,B3,B4,B8)
    # makeGeoIm(M,subTransform,crs,sen2Path + "ruffenacht.tif")
    # M = shadowIndex(B2,B3,B4,B8)
    # makeGeoIm(M,subTransform,crs,sen2Path + "swIdx.tif") # pc1
    # M = shadeIndex(B2,B3,B4,B8)
    # makeGeoIm(M,subTransform,crs,sen2Path + "shIdx.tif")
    # M = nsvi(B2,B3,B4)
    # makeGeoIm(M,subTransform,crs,sen2Path + "nsvi.tif")
    # M = mpsi(B2,B3,B4)
    # makeGeoIm(M,subTransform,crs,sen2Path + "mpsi.tif")
    makeGeoIm(M,subTransform,crs,sen2Path + "shadows.tif")
    
    del B2,B3,B4,B8
    
    if not os.path.exists(sen2Path + 'labelCastConn.tif'):
        # classify into regions
        siz = 5
        loop = 100
        Mmed = medianFilShadows(M,siz,loop)
        labels = sturge(Mmed)
        
        # find self-shadow and cast-shadow
        (sunZn,sunAz) = read_sun_angles_S2(sen2Path)
        sunZn = sunZn[minI:maxI,minJ:maxJ]
        sunAz = sunAz[minI:maxI,minJ:maxJ]
        
        makeGeoIm(labels,subTransform,crs,sen2Path + "labelPolygons.tif")
        # raster-based
        (castList,shadowRid) = labelOccluderAndCasted(labels, sunZn, sunAz)#, subTransform)
        # write data 
        makeGeoIm(shadowRid,subTransform,crs,sen2Path + "labelRidges.tif")
        makeGeoIm(castList,subTransform,crs,sen2Path + "labelCastConn.tif")
        
#        # polygon-based
#        castList = listOccluderAndCasted(labels, sunZn, sunAz, subTransform)
#        # write data to txt-file
#        # Header = ('ridgeX', 'ridgeY', 'castX', 'castY', 'sunAzi', 'sunZn')
#        fCast = sen2Path+fName[i][0:-2]+'.txt'
#        with open(fCast, 'w') as f:
#            for item in castList:
#                np.savetxt(f,item.reshape(1,6), fmt="%.2f", delimiter=",", 
#                           newline='\n', header='', footer='', comments='# ')
#        #        np.savetxt("test2.txt", x, fmt="%2.1f", delimiter=",")
#        #        f.write("%s\n" % item)
        print('wrote '+ fName[i][0:-2])
    if not os.path.exists(sen2Path + 'rgi.tif'):
        
        if not os.path.exists(datPath + S2tile + '.tif'): # create RGI raster
            rgiPath = datPath+'GIS/'
            rgiFile = '01_rgi60_alaska.shp'
            
            outShp = rgiPath+rgiFile[:-4]+'_utm'+S2tile[1:3]+'.shp'
            if not os.path.exists(outShp): # project RGI shapefile
                #making the shapefile as an object.
                inputShp = ogr.Open(rgiPath+rgiFile)
                #getting layer information of shapefile.
                inLayer = inputShp.GetLayer()
                # get info for coordinate transformation
                inSpatialRef = inLayer.GetSpatialRef()
                # output SpatialReference
                outSpatialRef = osr.SpatialReference()
                outSpatialRef.ImportFromWkt(crs)
                coordTrans = osr.CoordinateTransformation(inSpatialRef, outSpatialRef)
                
                driver = ogr.GetDriverByName('ESRI Shapefile')
                # create the output layer
                if os.path.exists(outShp):
                    driver.DeleteDataSource(outShp)
                outDataSet = driver.CreateDataSource(outShp)
                outLayer = outDataSet.CreateLayer("reproject", outSpatialRef, geom_type=ogr.wkbMultiPolygon)
 #               outLayer = outDataSet.CreateLayer("reproject", geom_type=ogr.wkbMultiPolygon)
                
                # add fields
                fieldDefn = ogr.FieldDefn('RGIId', ogr.OFTInteger) 
                fieldDefn.SetWidth(14) 
                fieldDefn.SetPrecision(1)
                outLayer.CreateField(fieldDefn)
                # inLayerDefn = inLayer.GetLayerDefn()
                # for i in range(0, inLayerDefn.GetFieldCount()):
                #     fieldDefn = inLayerDefn.GetFieldDefn(i)
                #     outLayer.CreateField(fieldDefn)
                
                # get the output layer's feature definition
                outLayerDefn = outLayer.GetLayerDefn()
                
                # loop through the input features
                inFeature = inLayer.GetNextFeature()
                while inFeature:
                    # get the input geometry
                    geom = inFeature.GetGeometryRef()
                    # reproject the geometry
                    geom.Transform(coordTrans)
                    # create a new feature
                    outFeature = ogr.Feature(outLayerDefn)
                    # set the geometry and attribute
                    outFeature.SetGeometry(geom)
                    rgiStr = inFeature.GetField('RGIId')
                    outFeature.SetField('RGIId', int(rgiStr[9:]))
                    # add the feature to the shapefile
                    outLayer.CreateFeature(outFeature)
                    # dereference the features and get the next input feature
                    outFeature = None
                    inFeature = inLayer.GetNextFeature()
                outDataSet = None # this creates an error but is needed?????
            
            #making the shapefile as an object.
            rgiShp = ogr.Open(outShp)
            #getting layer information of shapefile.
            rgiLayer = rgiShp.GetLayer()
            #get required raster band.
            
            driver = gdal.GetDriverByName('GTiff')
            rgiRaster = driver.Create(datPath+S2tile+'.tif', mI, nI, 1, gdal.GDT_Int16)
#            rgiRaster = gdal.GetDriverByName('GTiff').Create(datPath+S2tile+'.tif', mI, nI, 1, gdal.GDT_Int16)           
            rgiRaster.SetGeoTransform(geoTransform)
            band = rgiRaster.GetRasterBand(1)
            #assign no data value to empty cells.
            band.SetNoDataValue(0)
            # band.FlushCache()
            
            #main conversion method
            err = gdal.RasterizeLayer(rgiRaster, [1], rgiLayer, options=['ATTRIBUTE=RGIId'])
            rgiRaster = None # missing link.....
        
        # create subset
        (Msk, crs, geoTransform, targetprj) = read_geo_image(datPath+S2tile+'.tif')
        (bboxX,bboxY) = pix2map(subTransform,np.array([0, subM]),np.array([0, subN]))
        (bboxI,bboxJ) = map2pix(geoTransform, bboxX,bboxY)
        bboxI = np.round(bboxI).astype(int)
        bboxJ = np.round(bboxJ).astype(int)
        msk = Msk[bboxI[0]:bboxI[1],bboxJ[0]:bboxJ[1]]
        makeGeoIm(msk,subTransform,crs,sen2Path + 'rgi.tif')
        

# make stack of Labels & Connectivity
for i in range(len(s2Path)):
    create_caster_casted_list_from_polygons(datPath, s2Path[i], bbox)

## processing



coregister(s2Path, datPath, connectivity=2, stepSize=True, tempSize=15,
               bbox=bbox, lstsq_mode='simple')
#lkTransform = RefScale(RefTrans(subTransform,tempSize/2,tempSize/2),tempSize)   
#makeGeoIm(Dstack[0],lkTransform,crs,"DispAx1.tif")


# get co-registration information
(coName,coReg) = get_coregistration(datPath,s2Path)

# construct connectivity
for i in range(GridIdxs.shape[1]):
    fnam1 = s2Path[GridIdxs[0][i]]
    fnam2 = s2Path[GridIdxs[1][i]]
    
    # get start and finish points of shadow edges
    conn1 = np.loadtxt(fname = datPath+fnam1+'conn.txt')
    conn2 = np.loadtxt(fname = datPath+fnam2+'conn.txt')
    
    # compensate for coregistration
    coid1 = coName.index(fnam1)
    coid2 = coName.index(fnam2)
    coDxy = coReg[coid1]-coReg[coid2]
    conn2[:,0] += coDxy[0]
    conn2[:,1] += coDxy[1]
    #conn2[:,2] += coDxy[0]
    #conn2[:,3] += coDxy[1]
       
    # find nearest
    nbrs = NearestNeighbors(n_neighbors=1, algorithm='auto').fit(conn1[:,0:2])
    distances, indices = nbrs.kneighbors(conn2[:,0:2])
    IN = distances<20
    idxConn = np.transpose(np.vstack((np.where(IN)[0], indices[distances<20])))
    
    
# walk through glacier polygons      
# rgiList = np.trim_zeros(np.unique(Rgi))
# for j in rgiList:
#selection of glacier polygon
    # selec = Rgi==j     
    
# keep it image-based
selec = Rgi!=0 

linIdx = np.where(IN)


listOfCoordinates= list(zip(linIdx[0], linIdx[1], linIdx[2]))

# find associated caster
fig, ax = plt.subplots()
im = ax.imshow(selec.astype(int))
fig.colorbar(im)
plt.show()    
    
        






# weights through observation angle

    
# makeGeoIm(Mcan,subTransform,crs,"shadowRidges.tif")

# merge lists
for i in range(len(s2Path)):
    print('getting together')
    
#processed_image = cv2.filter2D(image,-1,kernel)




fig, ax = plt.subplots()
im = ax.imshow(Rgi)
fig.colorbar(im)
plt.show()





