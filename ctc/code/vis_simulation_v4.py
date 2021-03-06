#!/usr/bin/env python

"""

NAME: 
      vis_simulation_v4.py 
PURPOSE:
      Set-up for grid engine on folio
      Models visibilities using power spectra (pspecs) from pspec_sim_v2.py and creates a new Miriad UV file
      Differs from vis_simulation.py in that the sky image uses eq. coordinates and the fringe/beam is rotated with time (interpolation happens for fringe)
EXAMPLE CALL: 
      ./vis_simulation_v4.py --sdf 0.001 --sfreq 0.1 --nchan 10 --inttime 20000 --map pspec --mappath /Users/carinacheng/capo/ctc/images/pspecs/pspec100lmax100/ --filename test.uv -a 0_16 `python -c "import numpy; import aipy; print ' '.join(map(str,numpy.arange(2454500,2454501,20000/aipy.const.s_per_day)))"` -C psa898_v003
IMPORTANT NOTE: 
      Be careful when changing sdf and sfreq because they need to match the pspec files!
AUTHOR:
      Carina Cheng

"""

import aipy
import numpy
import ephem as e
import optparse
import os, sys

o = optparse.OptionParser()
o.set_usage('vis_simulation_v4.py [options] *.uv')
o.set_description(__doc__)
aipy.scripting.add_standard_options(o,cal=True,ant=True)
o.add_option('--mappath', dest='mappath', default='/Users/carinacheng/capo/ctc/images/pspecs/pspec40lmax110/',
             help='Directory where maps are. Include final / when typing path.')
o.add_option('--map', dest='map', default='gsm',
            help='Map type (gsm or pspec).')
o.add_option('--filename', dest='filename', default='/Users/carinacheng/capo/ctc/tables/testpspec.uv',
             help='Filename of created Miriad UV file (ex: test.uv).')
o.add_option('--nchan', dest='nchan', default=203, type='int',
             help='Number of channels in simulated data. Default is 203.')
o.add_option('--inttime', dest='inttime', default=10., type='float',
             help='Integration time (s). Default is 10.') 
o.add_option('--sfreq', dest='sfreq', default=0.1, type='float',
             help='Start frequency (GHz). Default is 0.1.')
o.add_option('--sdf', dest='sdf', default=0.1/203, type='float',
             help='Channel spacing (GHz).  Default is .1/203')
opts, args = o.parse_args(sys.argv[1:])

i,j = map(int,opts.ant.split('_'))
times = map(float,args) #converts args to floats

assert(not os.path.exists(opts.filename)) #checks if UV file exists already

print 'getting antenna array...'

aa = aipy.cal.get_aa(opts.cal, opts.sdf, opts.sfreq, opts.nchan)
freqs = aa.get_afreqs()
bl = aa.get_baseline(i,j) #[ns]
blx,bly,blz = bl[0],bl[1],bl[2]

#get topocentric coordinates and calculate beam response

print 'calculating beam response...'

img1 = aipy.map.Map(fromfits = opts.mappath+opts.map + '1001.fits', interp=True)

px = numpy.arange(img1.npix()) #number of pixels in map
crd = numpy.array(img1.px2crd(px,ncrd=3)) #aipy.healpix.HealpixMap.px2crd?
t3 = numpy.asarray(crd)
tx,ty,tz = t3[0], t3[1], t3[2] #1D arrays of top coordinates of img1 (can define to be whatever coordinate system)

g3 = numpy.asarray(crd) #map is in galactic coordinates

print 'getting maps and calculating fringes...'

shape = (len(times),len(freqs))
flags = numpy.zeros(shape, dtype=numpy.int32)
uvgridxx = numpy.zeros(shape, dtype=numpy.complex64)
uvgridyy = numpy.zeros(shape, dtype=numpy.complex64)

for jj, f in enumerate(freqs):
    img = aipy.map.Map(fromfits = opts.mappath+opts.map + '1' + str(jj+1).zfill(3) + '.fits', interp=True)
    #img = aipy.map.Map(fromfits = opts.mappath+opts.map + '1001.fits', interp=True) #reading same map over and over again
    fng = numpy.exp(-2j*numpy.pi*(blx*tx+bly*ty+blz*tz)*f) #fringe pattern
    aa.select_chans([jj]) #selects specific frequency
    bmxx = aa[0].bm_response((t3[0],t3[1],t3[2]), pol='x')[0]**2
    bmyy = aa[0].bm_response((t3[0],t3[1],t3[2]), pol='y')[0]**2
    sum_bmxx = numpy.sum(bmxx)
    sum_bmyy = numpy.sum(bmyy)
    fngxx = fng*bmxx/sum_bmxx #factor used later in visibility calculation
    fngyy = fng*bmyy/sum_bmyy
    fluxes = img[px] #fluxes preserved in galactic grid

    print 'Frequency %d/%d' % (jj+1, len(freqs)) 

    for ii, t in enumerate(times):

        print '   Timestep %d/%d' % (ii+1, len(times))
        aa.set_jultime(t)

        ga2eq = aipy.coord.convert_m('eq','ga',iepoch=e.J2000,oepoch=aa.epoch) #conversion matrix
        eq2top = aipy.coord.eq2top_m(-aa.sidereal_time(),aa.lat) #conversion matrix
        ga2eq2top = numpy.dot(eq2top,ga2eq)
        t3rot = numpy.dot(ga2eq2top,g3) #topocentric coordinates
        txrot = numpy.ma.compressed(numpy.ma.masked_where(t3rot[2]<0,t3rot[0]))
        tyrot = numpy.ma.compressed(numpy.ma.masked_where(t3rot[2]<0,t3rot[1]))
        tzrot = numpy.ma.compressed(numpy.ma.masked_where(t3rot[2]<0,t3rot[2])) #mask coordinates below horizon
        fluxes2 = numpy.ma.compressed(numpy.ma.masked_where(t3rot[2]<0,fluxes)) #mask data below horizon

        pxrot, wgts = img.crd2px(txrot,tyrot,tzrot, interpolate=1) 

        efngxx = numpy.sum(fngxx[pxrot]*wgts, axis=1)
        efngyy = numpy.sum(fngyy[pxrot]*wgts, axis=1)
        
        visxx = numpy.sum(fluxes2*efngxx)
        visyy = numpy.sum(fluxes2*efngyy)

        uvgridxx[ii,jj] = visxx
        uvgridyy[ii,jj] = visyy

    print ("%.8f" % f) + ' GHz done'

#miriad uv file set-up

print 'setting up miriad UV file...'

uv = aipy.miriad.UV(opts.filename, status='new')
uv._wrhd('obstype','mixed-auto-cross')
uv._wrhd('history','MDLVIS: created file.\nMDLVIS: ' + ' '.join(sys.argv) + '\n')

uv.add_var('telescop' ,'a'); uv['telescop'] = 'AIPY'
uv.add_var('operator' ,'a'); uv['operator'] = 'AIPY'
uv.add_var('version' ,'a'); uv['version'] = '0.0.1'
uv.add_var('epoch' ,'r'); uv['epoch'] = 2000.
uv.add_var('source'  ,'a'); uv['source'] = 'zenith'
uv.add_var('nchan' ,'i'); uv['nchan'] = opts.nchan
uv.add_var('sdf' ,'d'); uv['sdf'] = opts.sdf
uv.add_var('sfreq' ,'d'); uv['sfreq'] = opts.sfreq
uv.add_var('freq' ,'d'); uv['freq'] = opts.sfreq
uv.add_var('restfreq' ,'d'); uv['restfreq'] = opts.sfreq
uv.add_var('nschan' ,'i'); uv['nschan'] = uv['nchan']
uv.add_var('inttime' ,'r'); uv['inttime'] = opts.inttime
uv.add_var('npol' ,'i'); uv['npol'] = 1
uv.add_var('nspect' ,'i'); uv['nspect'] = 1
uv.add_var('nants' ,'i'); uv['nants'] = 32

#variables just set to dummy values

uv.add_var('vsource' ,'r'); uv['vsource'] = 0.
uv.add_var('ischan'  ,'i'); uv['ischan'] = 1
uv.add_var('tscale'  ,'r'); uv['tscale'] = 0.
uv.add_var('veldop'  ,'r'); uv['veldop'] = 0.

#variables to be updated

uv.add_var('coord' ,'d')
uv.add_var('time' ,'d')
uv.add_var('lst' ,'d')
uv.add_var('ra' ,'d')
uv.add_var('obsra' ,'d')
uv.add_var('baseline' ,'r')
uv.add_var('pol' ,'i')

#get antenna array

#more miriad variables

uv.add_var('latitud' ,'d'); uv['latitud'] = aa.lat
uv.add_var('dec' ,'d'); uv['dec'] = aa.lat
uv.add_var('obsdec' ,'d'); uv['obsdec'] = aa.lat
uv.add_var('longitu' ,'d'); uv['longitu'] = aa.long
uv.add_var('antpos' ,'d'); uv['antpos'] = (numpy.array([ant.pos for ant in aa], dtype = numpy.double)).transpose().flatten() #transpose is miriad convention

for ii, t in enumerate(times):

    print '%d/%d' % (ii+1, len(times))+' done'
    aa.set_jultime(t)
    uv['time'] = t
    uv['lst'] = aa.sidereal_time()
    uv['ra'] = aa.sidereal_time()
    uv['obsra'] = aa.sidereal_time()    

    preamble = (bl, t, (i,j))
    uv['pol'] = aipy.miriad.str2pol['xx']
    uv.write(preamble, uvgridxx[ii], flags[ii])
    uv['pol'] = aipy.miriad.str2pol['yy']
    uv.write(preamble, uvgridyy[ii], flags[ii])

del(uv)
