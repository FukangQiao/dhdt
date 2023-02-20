# functions to work with the coastal dataset
import os
import re

import geopandas

from dhdt.generic.handler_sentinel2 import \
    get_geom_for_tile_code, get_utmzone_from_tile_code, \
    get_epsg_from_mgrs_tile, _check_mgrs_code
from dhdt.generic.handler_landsat import \
    get_bbox_from_path_row
from dhdt.generic.handler_www import get_zip_file

def get_gshhg_url(url_type='ftp'):
    if url_type in ('ftp'):
        gshhg_url = 'ftp://ftp.soest.hawaii.edu/gshhg/gshhg-shp-2.3.7.zip'
    else:
        gshhg_url = 'http://www.soest.hawaii.edu/pwessel/gshhg/gshhg-shp-2.3.7.zip'
    return gshhg_url

def get_coastal_dataset(geom_dir, geom_name=None, minimal_level=1,
                        resolution='f'):
    """ get geospatial data of the coast, see also [1] & [2].

    Parameters
    ----------
    geom_dir : string
        location where the geometric data can be placed
    geom_name : string
        file name of the geometric coastal data
    minimal_level : integer, default=1
        Different levels of coasts and islands exist, hte higher the better:
            * 1: boundary between land and ocean, except Antarctica.
            * 2: boundary between lake and land.
            * 3: boundary between island-in-lake and lake.
            * 4: boundary between pond-in-island and island.
    resolution : {'f','h','i','l','c'}, default='f'
        the following options are possible:
            * f: full resolution: Original (full) data resolution.
            * h: high resolution: About 80 % reduction in size and quality.
            * i: intermediate resolution: Another ~80 % reduction.
            * l: low resolution: Another ~80 % reduction.
            * c: crude resolution: Another ~80 % reduction.

    References
    ----------
    .. [1] Wessel, & Smith. "A global, self‐consistent, hierarchical,
       high‐resolution shoreline database." Journal of geophysical research:
       solid Earth vol.101(B4) pp.8741-8743, 1996.
    .. [2] http://www.soest.hawaii.edu/pwessel/gshhg/
    """
    assert isinstance(minimal_level, int), 'please provide an integer'
    assert 0 < minimal_level < 5, 'please provide correct detail'
    assert resolution in ('f','h','i','l','c',), 'please provide correct letter'
    if not os.path.isdir(geom_dir): os.makedirs(geom_dir)
    if geom_name is None:
        geom_name = 'GSHHS_' + resolution + '_L' + str(minimal_level) + \
                    '.geojson'

    ffull = os.path.join(geom_dir, geom_name)
    if os.path.exists(ffull):
        return ffull

    gshhg_url = get_gshhg_url(url_type='http')
    file_list = get_zip_file(gshhg_url, dump_dir=geom_dir)

    for level in range(minimal_level):
        soi = 'GSHHS_shp' + os.sep + resolution + os.sep + \
              'GSHHS_' + resolution + '_L' + str(level+1) + '.shp'
        sfull = os.path.join(geom_dir,soi) # full path of shapefile of interest
        if level == 0:
            gshhs = geopandas.read_file(sfull)
        else:
            print('starting to cut geometry, this can take a while')
            hole = geopandas.read_file(sfull)
            gshhs = gshhs.overlay(hole, how='symmetric_difference')
            print('finished overlay analysis')
            del hole

    # write out the geometry to a GeoJSON file
    gshhs.to_file(ffull, driver='GeoJSON')

    for f in file_list:
        os.remove(os.path.join(geom_dir, f))
    return ffull

def get_coastal_polygon_of_tile(tile_code, tile_system='MGRS', out_dir=None,
                                geom_dir=None, geom_name=None):
    tile_code = _check_mgrs_code(tile_code)
    if geom_dir is None:
        rot_dir = os.sep.join(os.path.realpath(__file__).split(os.sep)[:-3])
        geom_dir = os.path.join(rot_dir, 'data')
    if geom_name is None: geom_name='GSHHS_f_L1.geojson'
    if out_dir is None: out_dir=os.getcwd()
    if not os.path.isdir(out_dir): os.makedirs(out_dir)

    if tile_system=='MGRS':
        toi = get_geom_for_tile_code(tile_code) # tile of interest
        utm_epsg = get_epsg_from_mgrs_tile(tile_code)
    else: # WRS2
        #todo
        path,row = [],[]
        toi = get_bbox_from_path_row(path,row)

    # get UTM extent, since not the whole world needs to be included
    utm_zone = get_utmzone_from_tile_code(tile_code)

    geom_path = os.path.join(geom_dir, geom_name)
    assert os.path.exists(geom_path), 'make sure data is present'

    gshhs = geopandas.read_file(geom_path)
    tile = geopandas.GeoDataFrame(index=[0], crs='epsg:4326',
                                  geometry=geopandas.GeoSeries.from_wkt([toi]))
    bound = gshhs.clip(tile)
    bound = bound.to_crs(epsg=utm_epsg)

    # create the output layer
    fname_json_utm = geom_name.split('.')[0]+'_utm'+str(utm_zone).zfill(2) + \
                    '.geojson'

    bound.to_file(os.path.join(out_dir, fname_json_utm), driver='GeoJSON')
    print('written ' + fname_json_utm)
    return
