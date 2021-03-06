#!/usr/bin/env python

"""

NAME: 
   vis_sim_mpi.py
PURPOSE:
   Models visibilities of Healpix maps and creates a new Miriad UV file
EXAMPLE CALL:
   mpiexec -np 3 vis_sim_mpi.py --nchan 100 --inttime 10 --sfreq 0.1 --sdf 0.001 -C psa898_v003 --map gsm --mappath /Users/carinacheng/capo/ctc/images/gsm/gsm100/
IMPORTANT NOTE:
   Make sure sdf and sfreq options match those of the maps!
AUTHOR:
   Carina Cheng

"""

import aipy
import numpy
import pyfits
import optparse
import os, sys
from mpi4py import MPI

#user options

o = optparse.OptionParser()
o.set_usage('vis_sim_mpi.py [options] *.uv')
o.set_description(__doc__)
o.add_option('--mappath', dest='mappath', default='/Users/carinacheng/capo/ctc/images/gsm/gsm203/',
             help='Directory where maps are. Include final / when typing path.')
o.add_option('--map', dest='map', default='gsm',
             help='Map type (gsm or pspec).')
o.add_option('--filename', dest='filename', default='/Users/carinacheng/capo/ctc/tables/test.uv',
             help='Filename of created Miriad UV file (ex: test.uv).')
o.add_option('--nchan', dest='nchan', default=203, type='int',
             help='Number of channels in simulated data. Default is 203.')
o.add_option('--inttime', dest='inttime', default=10., type='float',
             help='Integration time (s). Default is 10.') 
o.add_option('--sfreq', dest='sfreq', default=0.1, type='float',
             help='Start frequency (GHz). Default is 0.1.')
o.add_option('--sdf', dest='sdf', default=0.1/203, type='float',
             help='Channel spacing (GHz).  Default is .1/203')
o.add_option('--startjd', dest='startjd', default=2454500., type='float',
             help='Julian Date to start observation.  Default is 2454500')
o.add_option('--endjd', dest='endjd', default=2454501., type='float',
             help='Julian Date to end observation.  Default is 2454501')
o.add_option('-C', dest='psa', default='psa898_v003', 
             help='Name of calfile.')
o.add_option('--bli', dest='bli', default=0,
             help='Baseline i. Default is 0.')
o.add_option('--blj', dest='blj', default=16,
             help='Baseline j. Default is 16.')
opts, args = o.parse_args(sys.argv[1:])

#MPI set-up

comm = MPI.COMM_WORLD #get MPI communicator object
size = comm.size      #total number of processors
rank = comm.rank      #rank of a process
status = MPI.Status() #MPI status object (contains source and tag)

if rank == 0:

    #miriad uv file set-up

    print '***Master is setting up miriad UV file...'

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

    print '***Master is getting antenna array...'

    calfile = opts.psa
    aa = aipy.cal.get_aa(calfile,uv['sdf'],uv['sfreq'],uv['nchan'])
    freqs = aa.get_afreqs()
    i = opts.bli
    j = opts.blj
    bl = aa.get_baseline(i,j) #array of length 3 in ns
    blx,bly,blz = bl[0],bl[1],bl[2]

    #more miriad variables
    
    uv.add_var('latitud','d'); uv['latitud'] = aa.lat
    uv.add_var('dec','d'); uv['dec'] = aa.lat
    uv.add_var('obsdec','d'); uv['obsdec'] = aa.lat
    uv.add_var('longitu','d'); uv['longitu'] = aa.long
    uv.add_var('antpos','d'); uv['antpos'] = (numpy.array([ant.pos for ant in aa],dtype=numpy.double)).transpose().flatten() #transpose is miriad convention

    #get coordinates and calculate beam response

    print '***Master is calculating beam response and getting coordinates...'

    img1 = aipy.map.Map(fromfits = opts.mappath + opts.map + '1001.fits', interp=True)

    px = numpy.arange(img1.npix()) #number of pixels in map
    crd = numpy.array(img1.px2crd(px,ncrd=3))
    t3 = numpy.asarray(crd)
    tx,ty,tz = t3[0],t3[1],t3[2] #1D topocentric coordinates
    bmxx = aa[0].bm_response((t3[0],t3[1],t3[2]),pol='x')**2
    #bmyy = aa[0].bm_response((t3[0],t3[1],t3[2]),pol='y')**2
    sum_bmxx = numpy.sum(bmxx,axis=1)
    #sum_bmyy = numpy.sum(bmyy,axis=1)

    e3 = numpy.asarray(crd)
    ex,ey,ez = e3[0],e3[1],e3[2] #1D equatorial coordinates

    task_index = 0
    num_workers = size-1
    closed_workers = 0

    print '***Master is starting with %d workers and %d frequencies...' % (num_workers, len(freqs))

    #loop through frequencies to get fluxes and fringes

    fngxx = {}
    #fngyy = {}
    fluxes = {}

    print '***Master is getting fluxes and fringes...'

    while closed_workers < num_workers:
        worker_data = comm.recv(source=MPI.ANY_SOURCE,tag=MPI.ANY_TAG,status=status)
        tag = status.Get_tag()
        source = status.Get_source()
        if tag == 0: #worker is ready
            if task_index < len(freqs):
                print 'Sending freq %.03f to processor %d' % (freqs[task_index],source)
                comm.send((task_index,freqs[task_index],blx,bly,blz,tx,ty,tz,bmxx[task_index],sum_bmxx[task_index],px),dest=source,tag=3)
                task_index += 1
            else:
                comm.send(None,dest=source,tag=2)
        elif tag == 1: #done tag
            f = worker_data[0]
            fngxx[f] = worker_data[1]
            fluxes[f] = worker_data[2]
            #fngyy[f] = worker_data[?]
            print 'Processor %d is done calculating fringe for freq %.03f' % (source,f)
        elif tag == 2: #no more workers needed tag
            print 'Processor %d is done' % source
            closed_workers += 1

else: #other processors do this

    print 'Processor %d is ready' % rank
    while True:
        comm.send(None,dest=0,tag=0) #worker stops until message is received
        task = comm.recv(source=0,tag=MPI.ANY_TAG,status=status)
        tag = status.Get_tag()
        if tag == 3: #start working here
            jj = task[0]
            f = task[1]
            blx,bly,blz = task[2],task[3],task[4]
            tx,ty,tz = task[5],task[6],task[7]
            bmxx,sum_bmxx = task[8],task[9]
            #bmyy,sum_bmyy = task[?],task[?]
            px = task[10]
            img = aipy.map.Map(fromfits = opts.mappath+opts.map+'1'+str(jj+1).zfill(3)+'.fits',interp=True)
            fng = numpy.exp(-2j*numpy.pi*(blx*tx+bly*ty+blz*tz)*f)
            fngxx = fng*bmxx/sum_bmxx
            #fngyy = fng*bmyy/sum_bmyy
            fluxes = img[px] #fluxes preserved in equatorial grid      
            comm.send((f,fngxx,fluxes),dest=0,tag=1) #done tag
        elif tag == 2:
            break
    comm.send(None,dest=0,tag=2)

comm.Barrier()

if rank == 0:

    #loop through time to write uv file

    print '***Master is simulating each time step...'

    times = numpy.arange(opts.startjd, opts.endjd, uv['inttime']/aipy.const.s_per_day)
    flags = numpy.zeros(len(freqs), dtype=numpy.int32)

    task_index = 0
    num_workers = size-1
    closed_workers = 0
    count = 1
    all_dataxx = numpy.zeros((len(times),len(freqs)),dtype=numpy.complex)
    #all_datayy = numpy.zeros((len(times),len(freqs)),dtype=numpy.complex)

    while closed_workers < num_workers:
        worker_data = comm.recv(source=MPI.ANY_SOURCE,tag=MPI.ANY_TAG,status=status)
        tag = status.Get_tag()
        source = status.Get_source()
        if tag == 0: #worker is ready
            if task_index < len(times):
                print 'Sending timestep %d/%d to processor %d' % (task_index+1,len(times),source)
                t = times[task_index]
                aa.set_jultime(t)
                uv['time'] = t
                uv['lst'] = aa.sidereal_time()
                uv['ra'] = aa.sidereal_time()
                uv['obsra'] = aa.sidereal_time()
                sid_time = float(aa.sidereal_time())
                lat = float(aa.lat)
                comm.send((task_index,t,sid_time,lat,e3,freqs,fngxx,fluxes),dest=source,tag=3)
                task_index += 1
            else:
                comm.send(None,dest=source,tag=2)
        elif tag == 1: #done tag
            ii = worker_data[0] #not necessarily sequential
            all_dataxx[ii] = worker_data[1]
            #all_datayy[ii] = worker_data[?]
            print 'Timestep %d/%d complete' % (count,len(times))
            count += 1
        elif tag == 2: #no more workers needed tag
            print 'Processor %d done' % source
            closed_workers += 1

    print '***Master finishing by writing UV file...'
    for kk,t in enumerate(times): #UV files must be written sequentially
        preamble = (bl,t,(i,j))
        uv['pol'] = aipy.miriad.str2pol['xx']
        uv.write(preamble,all_dataxx[kk],flags)
        #uv['pol'] = aipy.miriad.str2pol['yy']
        #uv.write(preamble,all_datayy[kk],flags)

else: #other processors do this

    print 'Processor %d is ready' % rank
    while True:
        comm.send(None,dest=0,tag=0)
        task = comm.recv(source=0,tag=MPI.ANY_TAG,status=status)
        tag = status.Get_tag()
        if tag == 3: #start tag
            ii = task[0]
            t = task[1]
            eq2top = aipy.coord.eq2top_m(task[2],task[3]) #conversion matrix
            t3 = numpy.dot(eq2top,task[4]) #topocentric coordinates
            tx,ty,tz = t3[0],t3[1],t3[2]

            dataxx = []
            #datayy = []

            img = aipy.map.Map(fromfits = opts.mappath+opts.map+'1001.fits',interp=True)
            px,wgts = img.crd2px(tx,ty,tz,interpolate=1)

            freqs = task[5]
            fngxx,fluxes = task[6],task[7]
            #fngyy = task[?]

            for jj,f in enumerate(freqs):
                efngxx = numpy.sum(fngxx[f][px]*wgts,axis=1)
                #enfngyy = numpy.sum(fngyy[f][px]*wgts,axis=1)
                visxx = numpy.sum(fluxes[f]*efngxx)
                #visyy = numpy.sum(fluxes[f]*efngyy)
                dataxx.append(visxx)
                #datayy.append(visyy)

            dataxx = numpy.asarray(dataxx)
            #datayy = numpy.asarray(datayy)

            comm.send((ii,dataxx),dest=0,tag=1)
        elif tag == 2:
            break
    comm.send(None,dest=0,tag=2)



