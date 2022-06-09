import numpy as np

from pysolar.solar import get_azimuth, get_altitude
from datetime import datetime
from pytz import timezone

from scipy import ndimage
from scipy.spatial.transform import Rotation

from skimage import transform

# general location functions
def annual_solar_graph(latitude=51.707524, longitude=6.244362, deg_sep=.5,
                       year = 2018, sec_resol=20):
    """ calculate the solar graph of a location

    Parameters
    ----------
    latitude : float, unit=degrees, range=-90...+90
        latitude of the location of interest
    longitude : float, unit=degrees, range=-180...+180
        longitude of the location of interest
    deg_sep : float, unit=degrees
        resolution of the solargraph grid
    year : integer
        year of interest
    sec_resol : float, unit=seconds, default=20
        resolution of sun location calculation

    Returns
    -------
    Sky : np.array, size=(k,l), dtype=integer
        array with solargraph
    az : np.array, size=(l,_), dtype=float, unit=degrees
        azimuth values, that is the axis ticks of the solar graph
    zenit : np.array, size=(k,_), dtype=float, unit=degrees
        zenit values, that is the axis ticks of the solar graph
    """
    az = np.arange(0, 360, deg_sep)
    zn = np.flip(np.arange(-.5, +90, deg_sep))

    Sol = np.zeros((zn.shape[0], az.shape[0]))

    month = np.array([12, 6])     # 21/12 typical winter solstice - lower bound
    day = np.array([21, 21])      # 21/06 typical summer solstice - upper bound

    # loop through all times to get sun paths
    for i in range(0,2):
        for hour in range(0, 24):
            for minu in range(0, 60):
                for sec in range(0, 60, sec_resol):
                    sun_zen = get_altitude(latitude, longitude, \
                                          datetime(year, month[i], day[i], \
                                                   hour, minu, sec, \
                                                   tzinfo=timezone('UTC')))
                    sun_azi = get_azimuth(latitude, longitude, \
                                          datetime(year, month[i], day[i], \
                                                   hour, minu, sec, \
                                                   tzinfo=timezone('UTC')))

                az_id = (np.abs(az - sun_azi)).argmin()
                zn_id = (np.abs(zn - sun_zen)).argmin()
                if i==0:
                    Sol[zn_id,az_id] = -1
                else:
                    Sol[zn_id,az_id] = +1
    # remove the line below the horizon
    Sol = Sol[:-1,:]

    # mathematical morphology to do infilling, and extent the boundaries a bit
    Sol_plu, Sol_min = Sol==+1, Sol==-1
    Sol_plu = ndimage.binary_dilation(Sol_plu, np.ones((5,5))).cumsum(axis=0)==1
    Sol_min = np.flipud(ndimage.binary_dilation(Sol_min, np.ones((5,5))))
    Sol_min = np.flipud(Sol_min.cumsum(axis=0)==1)

    # populated the solargraph between the upper and lower bound
    Sky = np.zeros(Sol.shape)
    for i in range(0,Sol.shape[1]):
        mat_idx = np.where(Sol_plu[:,i]==+1)
        if len(mat_idx[0]) > 0:
            start_idx = mat_idx[0][0]
            mat_idx = np.where(Sol_min[:,i]==1)
            if len(mat_idx[0]) > 0:
                end_idx = mat_idx[0][-1]
            else:
                end_idx = Sol.shape[1]
            Sky[start_idx:end_idx,i] = 1

    return Sky, az, zn

def az_to_sun_vector(az, indexing='ij'):
    """ transform azimuth angle to 2D-unit vector

    Parameters
    ----------
    az : float, unit=degrees
        azimuth of sun.
    indexing : {‘xy’, ‘ij’}
         * "xy" : using map coordinates
         * "ij" : using local image  coordinates

    Returns
    -------
    sun : numpy.array, size=(2,1), range=0...1
        unit vector in the direction of the sun.

    See Also
    --------
    sun_angles_to_vector

    Notes
    -----
    The azimuth angle declared in the following coordinate frame:

        .. code-block:: text

                 ^ North & y
                 |
            - <--┼--> +
                 |
                 ┼----> East & x

    The angles related to the suns' heading are as follows:

        .. code-block:: text

          surface normal              * sun
          ^                     ^    /
          |                     |   /
          ├-- zenith angle      |  /
          | /                   | /|
          |/                    |/ | elevation angle
          └----                 └--┴---

    Two different coordinate system are used here:

        .. code-block:: text

          indexing   |           indexing    ^ y
          system 'ij'|           system 'xy' |
                     |                       |
                     |       i               |       x
             --------┼-------->      --------┼-------->
                     |                       |
                     |                       |
          image      | j         map         |
          based      v           based       |

    """
    if indexing=='ij':
        sun = np.array([[ -np.cos(np.radians(az)) ],
                        [ +np.sin(np.radians(az)) ]])
    else: # 'xy' that is a map coordinate system
        sun = np.array([[ +np.sin(np.radians(az)) ],
                        [ +np.cos(np.radians(az)) ]])
    return sun

def sun_angles_to_vector(az, zn, indexing='ij'):
    """ transform azimuth and zenith angle to 3D-unit vector

    Parameters
    ----------
    az : float, unit=degrees
        azimuth angle of sun.
    zn : float, unit=degrees
        zenith angle of sun.
    indexing : {‘xy’, ‘ij’}
         * "xy" : using map coordinates
         * "ij" : using local image  coordinates

    Returns
    -------
    sun : numpy.array, size=(3,1), dtype=float, range=0...1
        unit vector in the direction of the sun.

    See Also
    --------
    az_to_sun_vector

    Notes
    -----
    The azimuth angle declared in the following coordinate frame:

        .. code-block:: text

                 ^ North & y
                 |
            - <--┼--> +
                 |
                 ┼----> East & x

    The angles related to the sun are as follows:

        .. code-block:: text

          surface normal              * sun
          ^                     ^    /
          |                     |   /
          ├-- zenith angle      |  /
          | /                   | /|
          |/                    |/ | elevation angle
          └---- surface -----   └--┴---

    Two different coordinate system are used here:

        .. code-block:: text

          indexing   |           indexing    ^ y
          system 'ij'|           system 'xy' |
                     |                       |
                     |       i               |       x
             --------┼-------->      --------┼-------->
                     |                       |
                     |                       |
          image      | j         map         |
          based      v           based       |

    """
    if indexing=='ij': # local image system
        sun = np.dstack((-np.cos(np.radians(az)), \
                         +np.sin(np.radians(az)), \
                         +np.tan(np.radians(zn)))
                        )
    else: # 'xy' that is map coordinates
        sun = np.dstack((+np.sin(np.radians(az)), \
                         +np.cos(np.radians(az)), \
                         +np.tan(np.radians(zn)))
                        )

    n = np.linalg.norm(sun, axis=2)
    sun[:, :, 0] /= n
    sun[:, :, 1] /= n
    sun[:, :, 2] /= n
    return sun

# elevation model based functions
def make_shadowing(Z, az, zn, spac=10):
    """ create synthetic shadow image from given sun angles

    Parameters
    ----------
    Z : numpy.array, size=(m,n), dtype={integer,float}
        grid with elevation data
    az : float, unit=degrees
        azimuth angle
    zn : float, unit=degrees
        zenith angle
    spac : float, optional
        resolution of the square grid. The default is 10.

    Returns
    -------
    Sw : numpy.array, size=(m,n), dtype=bool
        estimated shadow grid

    Notes
    -----
    The azimuth angle declared in the following coordinate frame:

        .. code-block:: text

                 ^ North & y
                 |
            - <--┼--> +
                 |
                 ┼----> East & x

    The angles related to the sun are as follows:

        .. code-block:: text

          surface normal              * sun
          ^                     ^    /
          |                     |   /
          ├-- zenith angle      |  /
          | /                   | /|
          |/                    |/ | elevation angle
          └----                 └--┴---
    """
    Zr = ndimage.rotate(Z, az, axes=(1, 0), cval=-1, order=3)
    # mask based
    Mr = ndimage.rotate(np.zeros(Z.shape, dtype=bool), az, axes=(1, 0), \
                        cval=False, order=0, prefilter=False)

    dZ = np.tan(np.radians(90-zn))*spac
    for i in range(1,Zr.shape[0]):
        Mr[i,:] = (Zr[i,:])<(Zr[i-1,:]-dZ)
        Zr[i,:] = np.maximum(Zr[i,:], Zr[i-1,:]-dZ)

    Ms = ndimage.interpolation.rotate(Mr, -az, axes=(1, 0), cval=False, order=0, \
                                      mode='constant', prefilter=False)
    i_min = int(np.floor((Ms.shape[0] - Z.shape[0]) / 2))
    i_max = int(np.floor((Ms.shape[0] + Z.shape[0]) / 2))
    j_min = int(np.floor((Ms.shape[1] - Z.shape[1]) / 2))
    j_max = int(np.floor((Ms.shape[1] + Z.shape[1]) / 2))

    Sw = Ms[i_min:i_max, j_min:j_max]
    return Sw

def make_shading(Z, az, zn, spac=10):
    """ create synthetic shading image from given sun angles

    A simple Lambertian reflection model is used here.

    Parameters
    ----------
    Z : numpy.array, size=(m,n), dtype={integer,float}, unit=meter
        grid with elevation data
    az : float, unit=degrees
        azimuth angle
    zn : float, unit=degrees
        zenith angle
    spac : float, default=10, unit=meter
        resolution of the square grid.

    Returns
    -------
    Sh : numpy.array, size=(m,n), dtype=float, range=0...1
        estimated shading grid

    Notes
    -----
    The azimuth angle declared in the following coordinate frame:

        .. code-block:: text

                 ^ North & y
                 |
            - <--┼--> +
                 |
                 ┼----> East & x

    The angles related to the sun are as follows:

        .. code-block:: text

          surface normal              * sun
          ^                     ^    /
          |                     |   /
          ├-- zenith angle      |  /
          | /                   | /|
          |/                    |/ | elevation angle
          └----                 └--┴---
    """
    sun = sun_angles_to_vector(az, zn, indexing='xy')

    # estimate surface normals

    # the first array stands for the gradient in rows and
    # the second one in columns direction
    dy, dx = np.gradient(Z*spac)

    normal = np.dstack((dx, dy, np.ones_like(Z)))
    n = np.linalg.norm(normal, axis=2)
    normal[:, :, 0] /= n
    normal[:, :, 1] /= n
    normal[:, :, 2] /= n

    Sh = normal[:,:,0]*sun[:,:,0] + \
        normal[:,:,1]*sun[:,:,1] + \
        normal[:,:,2]*sun[:,:,2]
    return Sh

def make_doppler_range(Z, az, zn, Lambertian=True, spac=10):
    """

    Parameters
    ----------
    Z : numpy.array, unit=meters
        array with elevation values
    az : float, unit=degrees, range=-180...+180
        flight orientation of the satellite
    zn : {float,array},  unit=degrees, range=0...+90
        illumination angle from the satellite

    Returns
    -------

    Notes
    -----


    """

    # rotate
    Z_r = ndimage.rotate(Z, az, axes=(1, 0), cval=-1, order=3)
    # mask based
    M_r = ndimage.rotate(np.ones_like(Z, dtype=bool), az, axes=(1, 0), \
                        cval=False, order=0, prefilter=False)

    K_r = np.fliplr(np.meshgrid(np.linspace(0,M_r.shape[0]-1,M_r.shape[0]),
                                np.linspace(0,M_r.shape[1]-1,M_r.shape[1]))[0])
    np.putmask(K_r, ~M_r, 0)

    D_r = np.multiply(np.cos(np.deg2rad(zn)), Z_r) + \
          np.multiply(np.sin(np.deg2rad(zn)), K_r*spac)

    if Lambertian: # do a weighted histogram
        Sd = make_shading(Z, az, zn, spac=10)
        Sd_r = ndimage.rotate(Sd, az, axes=(1, 0), cval=-1, order=3)
        np.putmask(Sd_r, ~M_r, 0)

    # loop through the rows and create histogram
    S_r = np.zeros_like(Z_r, dtype=float)
    for i in range(Z_r.shape[0]):
        if Lambertian:
            his,_ = np.histogram(D_r[i,:],
                                 bins=np.arange(0, K_r.shape[1]+1),
                                 weights=Sd_r[i,:])
        else:
            his,_ = np.histogram(D_r[i,:],
                                 bins=np.arange(0, K_r.shape[1]+1),
                                 weights=M_r[i,:].astype(float))
        S_r[i,:] = his
    return

def make_shading_minnaert(Z, az, zn, k=1, spac=10):
    """ create synthetic shading image from given sun angles

    A simple Minnaert reflection model is used here.

    Parameters
    ----------
    Z : numpy.array, size=(m,n), dtype={integer,float}, unit=meter
        grid with elevation data
    az : float, unit=degrees
        azimuth angle
    zn : float, unit=degrees
        zenith angle
    spac : float, default=10, unit=meter
        resolution of the square grid.

    Returns
    -------
    Sh : numpy.array, size=(m,n), dtype=float, range=0...1
        estimated shading grid

    Notes
    -----
    The azimuth angle declared in the following coordinate frame:

        .. code-block:: text

                 ^ North & y
                 |
            - <--┼--> +
                 |
                 ┼----> East & x

    The angles related to the sun are as follows:

        .. code-block:: text

          surface normal              * sun
          ^                     ^    /
          |                     |   /
          ├-- zenith angle      |  /
          | /                   | /|
          |/                    |/ | elevation angle
          └----                 └--┴---
    """
    sun = sun_angles_to_vector(az, zn, indexing='xy')

    # estimate surface normals
    dy, dx = np.gradient(Z*spac)

    normal = np.dstack((dx, dy, np.ones_like(Z)))
    n = np.linalg.norm(normal, axis=2)
    normal[:, :, 0] /= n
    normal[:, :, 1] /= n
    normal[:, :, 2] /= n

    L = normal[:,:,0]*sun[:,:,0] + \
        normal[:,:,1]*sun[:,:,1] + \
        normal[:,:,2]*sun[:,:,2]
    # assume overhead
    Sh = L**(k+1) * (1-normal[:,:,2])**(1-k)
    return Sh

# topocalc has horizon calculations
# based upon Dozier & Frew 1990
# implemented by Maxime: https://github.com/maximlamare/REDRESS


