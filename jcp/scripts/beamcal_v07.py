#! /usr/bin/env python
import aipy as a, pylab as p, numpy as n, sys, optparse

o = optparse.OptionParser()
o.set_usage('beamcal.py [options]')
a.scripting.add_standard_options(o, cal=True, pol=True, cmap=True, src=True)
o.add_option('-f', '--freq', dest='freq', type='float', default=.150,
    help='Frequency to plot beam for.  Default .150 GHz')
o.add_option('--nside', dest='nside', type='int', default=32,
    help='NSIDE parameter for HEALPix map of beam.')
o.add_option('-o', '--outfile', dest='outfile',
    help='The name of the fits file to create.')
             
opts,args = o.parse_args(sys.argv[1:])

cmap = p.get_cmap(opts.cmap)
print 'Modelling beam at %f GHz' % (opts.freq)

afreqs = n.load(args[0])['afreqs']
srcs = [f.split('__')[0] for f in args]
srcstring = ''
for src in srcs:
    srcstring+=src+','
srcstring=srcstring.rstrip(',')

aa = a.cal.get_aa(opts.cal, afreqs)
srclist, cutoff, catalogs = a.scripting.parse_srcs(srcstring, opts.cat)
cat = a.cal.get_catalog(opts.cal,srclist)
cat.compute(aa)

beama = a.map.Map(opts.nside,interp=True)
beamb = a.map.Map(opts.nside,interp=True)
beamc = a.map.Map(opts.nside,interp=True)

fluxcal = 'cyg'
srctimes = {}
srcfluxes = {}
srcgains = {}
for src, npz in zip(srcs,args):
    print 'Reading:', npz
    try: f = n.load(npz)
    except:
        print 'Load file failed.'
        continue
    if not srctimes.has_key(src):
        srctimes[src] = f['times']
    if not srcfluxes.has_key(src):
        srcfluxes[src] = f['spec']
        srcfluxes[src] = n.mean(srcfluxes[src].real,axis=1)
        if src == fluxcal:
            calflux = n.reshape(cat[fluxcal].jys,(1,afreqs.size))
            calflux = n.mean(calflux.real,axis=1)

alt, az = {},{}
x,y,z = {},{},{}

print 'Calculating source tracks...'
track = {}
tracks = n.array([]) 
for k in srcs:
    if not alt.has_key(k):
        alt[k], az[k] = [],[]
        x[k],y[k],z[k] = [],[],[]
    for i,t in enumerate(srctimes[k]):
        aa.set_jultime(t)
        cat[k].compute(aa)
        alt[k].append(cat[k].alt)
        az[k].append(cat[k].az)
    alt[k] = n.array(alt[k])
    az[k] = n.array(az[k])
    x[k],y[k],z[k] = a.coord.azalt2top((az[k], alt[k])) 
    track[k] = n.append(n.unique(beama.crd2px(x[k],y[k],z[k],interpolate=True)[0]), n.unique(beama.crd2px(-x[k],-y[k],z[k],interpolate=True)[0]))
    #track[k] = n.unique(n.append(beama.crd2px(x[k],y[k],z[k]), beam.crd2px(-x[k],-y[k],z[k])))
    tracks = n.append(tracks,track[k])
tracks = tracks.astype(n.long)

print 'Determining crossing points...'
cnt = {}
for i in xrange(max(tracks)+1):
    cnt[i] = n.where(tracks == i)[0].shape[0]
    crossing_pixels = n.where(n.array(cnt.values()) > 1)[0]

print 'Averaging measurements within a pixel...'
fluxtrack,wgttrack = {},{}
S,C,w,wM = [],[],[],[]
for k in srcs:
    fluxtrack[k],wgttrack[k] = {},{}
    for i, meas in enumerate(srcfluxes[k]):
        pcrd,pwgt = beama.crd2px(n.array([x[k][i]]),n.array([y[k][i]]),n.array([z[k][i]]),interpolate=True)
        ncrd,nwgt = beama.crd2px(n.array([-x[k][i]]),n.array([-y[k][i]]),n.array([z[k][i]]),interpolate=True)
        for ind,crd in enumerate(pcrd[0]):
            if crd in crossing_pixels:
                if not fluxtrack[k].has_key(crd):
                    fluxtrack[k][crd] = pwgt[0][ind]*meas
                    wgttrack[k][crd] = pwgt[0][ind]
                else:
                    fluxtrack[k][crd] += pwgt[0][ind]*meas
                    wgttrack[k][crd] += pwgt[0][ind]
        for ind,crd in enumerate(ncrd[0]):
            if crd in crossing_pixels:
                if not fluxtrack[k].has_key(crd):
                    fluxtrack[k][crd] = nwgt[0][ind]*meas
                    wgttrack[k][crd] = nwgt[0][ind]
                else:
                    fluxtrack[k][crd] += nwgt[0][ind]*meas
                    wgttrack[k][crd] += nwgt[0][ind]
    for crd in fluxtrack[k].keys():
        S.append(k)
        C.append(crd)
        fluxtrack[k][crd] /= wgttrack[k][crd]
        w.append((fluxtrack[k][crd]**2)*(wgttrack[k][crd]**2))
        wM.append(n.log10(fluxtrack[k][crd])*(fluxtrack[k][crd]**2)*(wgttrack[k][crd]**2))


#print n.where(n.array(w)==0)
print 'Constructing matrices...'
dC,dS = {},{}
for i,c in enumerate(crossing_pixels):
    dC[c] = i
for i,k in enumerate(srcs):
    if not dS.has_key(k): dS[k] = i
neq = len(wM)
npix = len(crossing_pixels)
nsrcs = len(srcs)
A = n.zeros((neq+1,npix+nsrcs),dtype=n.float32)

for k in srcs:
    for ind,wgt in enumerate(w):
        A[ind,dC[C[ind]]] = wgt
        A[ind,npix+dS[S[ind]]] = wgt
    if k == fluxcal:
        A[-1,npix+dS[fluxcal]] = 1e16

#p.imshow(A,aspect='auto',interpolation='nearest',vmax=1.5)
#p.colorbar
#p.show()

wM.append(1e16*n.log10(calflux))
wM = n.array(wM,dtype=n.float32)


print 'Solving equation...'
#B = n.dot(n.linalg.inv(n.dot(n.transpose(A),A)),n.dot(n.transpose(A),wM))
B = n.linalg.lstsq(A,wM)
n.savez(opts.outfile+'.npz',B[0])
#print 10**B
print 10**B[0]

print 'Making beams...'
#bm = 10**(B[:-nsrcs])
bm = 10**(B[0][:-nsrcs])
beama.add(crossing_pixels,n.ones_like(bm),bm)
if beama[0,0,1] != 0:
    print 'Normalizing...'
    for pix,gain in enumerate(beama):
        beama.put(n.array([pix]),beama.wgt[pix],gain/beama[0,0,1])
basename = opts.outfile.split('.')
outnamea = basename[0]+'a.'+basename[1]
beama.to_fits(outnamea, clobber=True)

if True:
    outnameb = basename[0]+'b.'+basename[1]
    outnamec = basename[0]+'c.'+basename[1]
    fluxes = 10**(B[0][npix:])
    #fluxes = 10**(B[npix:])
    for j,k in enumerate(srcs):
        srcgains = srcfluxes[k]/fluxes[j]
        beamb.add((x[k],y[k],z[k]),n.ones_like(srcgains),srcgains)
        beamb.add((-x[k],-y[k],z[k]),n.ones_like(srcgains),srcgains)
        beamc.add((x[k],y[k],z[k]),srcfluxes[k]**2,srcgains)
        beamc.add((-x[k],-y[k],z[k]),srcfluxes[k]**2,srcgains)
    beamb.to_fits(outnameb,clobber=True)
    beamc.to_fits(outnamec,clobber=True)
