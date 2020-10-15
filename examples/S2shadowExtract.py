import os
import glob
import numpy as np
import matplotlib.pyplot as plt

from scipy import interpolate

from osgeo import ogr, osr, gdal

from eratosthenes.generic.handler_s2 import meta_S2string
from eratosthenes.generic.handler_www import bulk_download_and_mosaic, \
    reduce_deplicate_urls
from eratosthenes.generic.mapping_io import makeGeoIm, read_geo_image, \
    read_geo_info
from eratosthenes.generic.mapping_tools import get_bbox_polygon, \
    find_overlapping_DEM_tiles, get_bbox, map2pix, bilinear_interp_excluding_nodat
    
from eratosthenes.generic.gis_tools import ll2utm, shape2raster, \
    reproject_shapefile

from eratosthenes.preprocessing.handler_multispec import create_shadow_image, \
    create_caster_casted_list_from_polygons
from eratosthenes.preprocessing.handler_rgi import which_rgi_region
from eratosthenes.preprocessing.shadow_geometry import create_shadow_polygons, \
    make_shadowing

from eratosthenes.processing.coregistration import coregister, \
    get_coregistration, getNetworkBySunangles
from eratosthenes.processing.coupling_tools import couple_pair

from eratosthenes.postprocessing.mapping_io import dh_txt2shp

dat_path = '/Users/Alten005/surfdrive/Eratosthenes/Denali/'
#im_path = 'Data/S2A_MSIL1C_20180225T214531_N0206_R129_T05VPL_20180225T232042/'
#fName = 'T05VPL_20180225T214531_B'

im_path = ('Data/S2A_MSIL1C_20180225T214531_N0206_R129_T05VNK_20180225T232042/',
          'Data/S2B_MSIL1C_20190225T214529_N0207_R129_T05VNK_20190226T010218/',
          'Data/S2A_MSIL1C_20200225T214531_N0209_R129_T05VNK_20200225T231600/')
fName = ('T05VNK_20180225T214531_B', 'T05VNK_20190225T214529_B', 'T05VNK_20200225T214531_B')

shadow_transform = 'ruffenacht' # method to deploy for shadow enhancement

poi = np.array([62.7095217, -151.8519815]) # lat,lon point of interest

# do a subset of the imagery
minI = 4000 # minimal row coordiante
maxI = 6000 # maximum row coordiante
minJ = 4000 # minimal collumn coordiante
maxJ = 6000 # maximum collumn coordiante

bbox = (minI, maxI, minJ, maxJ)


sen2Path = dat_path + im_path[0]
(sat_time,sat_orbit,sat_tile) = meta_S2string(im_path[0])

# make raster with elevation data for the tile
if not os.path.exists(dat_path + sat_tile + '_DEM.tif'):
    print('building digital elevation model (DEM) for '+ sat_tile )
    # get geo info of tile
    crs, geoTransform, targetprj, rows, cols, bands = read_geo_info(dat_path + 
                                                                    sat_tile + 
                                                                    '.tif')
    ### OBS
    # randolph tile seems to have a missing crs... etc OGR does not see anything
    ###
    
    fname = dat_path + im_path[0] + fName[0] + '04.jp2'
    crs, geoTransform, targetprj, rows, cols, bands = read_geo_info(fname)
    
    # get DEM tile structure
    dem_path = dat_path+'GIS/'
    dem_file = 'ArcticDEM_Tile_Index_Rel7.shp'
    
    # find overlapping tiles of the granual
    poly_tile = get_bbox_polygon(geoTransform, rows, cols)
    dem_proj_file = reproject_shapefile(dem_path, dem_file, targetprj)
    url_list = find_overlapping_DEM_tiles(dem_path,dem_proj_file, poly_tile)
    print('found '+str(len(url_list))+ ' elevation chips connected to this tile')
    
    # create sampling grid   
    bbox_tile = get_bbox(geoTransform, rows, cols)
    
    new_res = 10 # change to 10meter url
    
    url_list = reduce_deplicate_urls(url_list)
    bulk_download_and_mosaic(url_list, dem_path, sat_tile, bbox_tile, crs, new_res)
    
    os.rename(dem_path + sat_tile + '_DEM.tif', dat_path + sat_tile + '_DEM.tif')

for i in range(len(im_path)):
    sen2Path = dat_path + im_path[i]
    (sat_time,sat_orbit,sat_tile) = meta_S2string(im_path[i])
    print('working on '+ fName[i][0:-2])
    if not os.path.exists(sen2Path + 'shadows.tif'):
        if len([n for n in ['matte'] if n in shadow_transform])==1:
            # shading estimate is needed as auxillary data
            Shw = make_shadowing(dat_path, sat_tile + '_DEM.tif',
                           dat_path, im_path[i])       
        
        (M, geoTransform, crs) = create_shadow_image(dat_path, im_path[i], \
                                                   shadow_transform, \
                                                   minI, maxI, minJ, maxJ \
                                                   )
        print('produced shadow transform for '+ fName[i][0:-2])
        makeGeoIm(M, geoTransform, crs, sen2Path + 'shadows.tif')
    else:
        (M, crs, geoTransform, targetprj) = read_geo_image(
            sen2Path + 'shadows.tif')

    if not os.path.exists(sen2Path + 'labelCastConn.tif'):
        (labels, cast_conn) = create_shadow_polygons(M,sen2Path, \
                                                     minI, maxI, minJ, maxJ \
                                                     )

        makeGeoIm(labels, geoTransform, crs, sen2Path + 'labelPolygons.tif')
        makeGeoIm(cast_conn, geoTransform, crs, sen2Path + 'labelCastConn.tif')
        print('labelled shadow polygons for '+ fName[i][0:-2])

# make raster with Randolph glacier mask for the tile
if not os.path.exists(dat_path + sat_tile + '.tif'):
    rgi_path = dat_path+'GIS/'
    # discover which randolph region is used
    rgi_file = which_rgi_region(rgi_path,poi)

    if len(rgi_file)==1:  
        # create RGI raster for the extent of the image   
        rgi_file = rgi_file[0]
        # rgi_file = '01_rgi60_Alaska.shp'
        out_shp = rgi_path+rgi_file[:-4]+'_utm'+sat_tile[1:3]+'.shp'
        # get geo-meta data for a tile
        fname = dat_path + im_path[0] + fName[0] + '04.jp2'
        crs, geoTransform, targetprj, rows, cols, bands = read_geo_info(fname)
        aoi = 'RGIId'
        if not os.path.exists(out_shp):  # project RGI shapefile
            # transform shapefile from lat-long to UTM
            ll2utm(rgi_path+rgi_file,out_shp,crs,aoi)
        # convert polygon file to raster file
        shape2raster(out_shp, dat_path+sat_tile, geoTransform, rows, cols, aoi)
  

(rgi_mask, crs, geoTransform, targetprj) = read_geo_image(dat_path
                                                          +sat_tile+'.tif')
rgi_mask = rgi_mask[minI:maxI,minJ:maxJ]

(dem_mask, crs, geoTransform, targetprj) = read_geo_image(dat_path
                                                          +sat_tile+'_DEM.tif')
# -9999 is no-data
dem_mask = dem_mask[minI:maxI,minJ:maxJ]

# TO DO:
# make raster with elevation values for the tile


# make stack of Labels & Connectivity
rgi_glac_id = 22216 # None,  select a single glacier
if rgi_glac_id is not None:
    print(f'looking at glacier with Randolph ID { rgi_glac_id }.')
for i in range(len(im_path)):
    create_caster_casted_list_from_polygons(dat_path, im_path[i], rgi_mask, 
                                            bbox, rgi_glac_id)

# get co-registration information
(co_name,co_reg) = get_coregistration(dat_path, im_path)

im_selec = (set(co_name)^set(im_path))&set(im_path)
if bool(im_selec): # imagery in set which have not been co-registered
    print('co-registring imagery')
    coregister(im_path, dat_path, connectivity=2, step_size=True, temp_size=15,
               bbox=bbox, lstsq_mode='ordinary')
    #lkTransform = RefScale(RefTrans(subTransform,tempSize/2,tempSize/2),tempSize)
    #makeGeoIm(Dstack[0],lkTransform,crs,"DispAx1.tif")
    
    # get co-registration information
    (co_name,co_reg) = get_coregistration(dat_path, im_path)

## processing
print('pairing imagery')
# construct connectivity
connectivity = 2
GridIdxs = getNetworkBySunangles(dat_path, im_path, connectivity)
for i in range(GridIdxs.shape[1]):
    
    fname1 = im_path[GridIdxs[0][i]]
    fname2 = im_path[GridIdxs[1][i]]
    
    xy_1, xy_2, casters, dh = couple_pair(dat_path, fname1, fname2, bbox,
                                          co_name, co_reg, rgi_glac_id)

    # write elevation distance    
    (time_1, orbit_1, tile_1) = meta_S2string(fname1)
    (time_2, orbit_2, tile_2) = meta_S2string(fname2)
    dh_fname = ('dh-' + time_1 +'-'+ time_2 +'-'+ 
                orbit_1 + '-' + orbit_2 +'-'+ 
                tile_1 +'-'+ tile_2)
    if rgi_glac_id is None:
        dh_fname = (dh_fname + '.txt')
    else:
        dh_fname = (dh_fname + '-' + '{:08d}'.format(rgi_glac_id) + '.txt')
        
    f = open(dat_path + dh_fname, 'w')
    for k in range(dh.shape[0]):
        line = ('{:+8.2f}'.format(   xy_1[k, 0]) + ' ' + 
                '{:+8.2f}'.format(   xy_1[k, 1]) + ' ' +
                '{:+8.2f}'.format(   xy_2[k, 0]) + ' ' +
                '{:+8.2f}'.format(   xy_2[k, 1]) + ' ' +
                '{:+8.2f}'.format(casters[k, 0]) + ' ' +
                '{:+8.2f}'.format(casters[k, 1]) + ' ' +
                '{:+4.3f}'.format(     dh[k]))
        f.write(line + '\n')
    f.close()

# post-processing
print('post-processing')
# test dem with DEM

# get elevation change files
dh_files = glob.glob(dat_path+'/dh*.txt')
for i in range(len(dh_files)):
    full_path = dh_files[i].split('/')
    dh_meta = full_path[-1].split('-')
    # resolve metadata
    
    # read data
    with open(dh_files[i]) as f:
        lines = f.read().splitlines()
        dh_mat = np.array([list(map(float,line.split(' '))) for line in lines])
    del lines
   
    # look at DEM
    DEM, crs_DEM, geoTran_DEM, prj_DEM = read_geo_image(
        os.path.join( dat_path, dh_meta[5] + '_DEM.tif'))
    i1_DEM, j1_DEM = map2pix(geoTran_DEM, dh_mat[:,0].copy() , dh_mat[:,1])
    i2_DEM, j2_DEM = map2pix(geoTran_DEM, dh_mat[:,2], dh_mat[:,3])
   
    DEM_1 = bilinear_interp_excluding_nodat(DEM, i1_DEM, j1_DEM, -9999)
    DEM_2 = bilinear_interp_excluding_nodat(DEM, i2_DEM, j2_DEM, -9999)
    del i1_DEM, i2_DEM, j1_DEM, j2_DEM
    
    # add DEM data to file
    #DH = np.concatenate((dh_mat, np.vstack((DEM_1, DEM_2)).T), axis=1)
    
    ### OBS
    # python is strange and adjust dh_mat....
    
    with open(dh_files[i]) as f:
        lines = f.read().splitlines()
        dh_mat = np.array([list(map(float,line.split(' '))) for line in lines])
    del lines

    ## make shapefile
    shp_name = dh_files[i][:-3] + 'shp'
    dh_txt2shp(dh_mat, DEM_1, DEM_2, shp_name, prj_DEM)

    
   
    
    