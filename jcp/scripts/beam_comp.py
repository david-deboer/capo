#!/usr/global/paper/bin/python

import aipy as a, numpy as n, pylab as p, sys, os, ephem, optparse
from mpl_toolkits.basemap import Basemap

class InputError(Exception):
    pass
    #def __init__(self, msg):
    #    self.msg = msg

o = optparse.OptionParser()
o.set_usage('plot_beam.py [options] mapfile')
o.set_description(__doc__)
a.scripting.add_standard_options(o, cmap=True, max=True, drng=True,cal=True)
o.add_option('--res', dest='res', type='float', default=0.25,
    help="Resolution of plot (in degrees).  Default 0.25.")
o.add_option('-m', '--mod', dest='model', type='string', default=None,
    help="The model to compare with.")
o.add_option('-d', '--dirty', dest='dirty', type='string', default=None,
    help="The original dirty beam.")
o.add_option('--mask',dest='mask',action='store_true',
    help="Mask all beams with the sampling pattern from the dirty beam.")

opts,args = o.parse_args(sys.argv[1:])

if opts.model == None:
    raise InputError('You need a beam model.')

cmap = p.get_cmap(opts.cmap)
aa = a.cal.get_aa(opts.cal,n.array([.150]))


dirty = a.map.Map(fromfits=opts.dirty)

smooth = a.map.Map(fromfits=args[0])
smooth.map.map /= smooth[0,0,1]

model = a.map.Map(fromfits=opts.model)
model.map.map /= model[0,0,1]
    
diff = a.map.Map(32)
#diff.map.map = h.map.map-model.map.map
for pix,val in enumerate(diff):
    diff.put(pix,1,(smooth[pix] - model[pix])/model[pix])
print 'SCHEME:', smooth.scheme()
print 'NSIDE:', smooth.nside()
mask = dirty.wgt


for index,bm in enumerate([smooth,model,diff]):
    map = Basemap(projection='ortho',lat_0=90,lon_0=180,rsphere=1.)
    lons,lats,x,y = map.makegrid(360/opts.res,180/opts.res, returnxy=True)
    lons = 360 - lons
    lats *= a.img.deg2rad; lons *= a.img.deg2rad
    y,x,z = a.coord.radec2eq(n.array([lons.flatten(), lats.flatten()]))
    if opts.model == 'sdipole_05e_eg_ffx_150.hmap' and bm == model:
        x,y,z = a.coord.radec2eq(n.array([lons.flatten(), lats.flatten()]))
    ax,ay,az = a.coord.latlong2xyz(n.array([aa.lat,0]))
    if opts.mask:
        data = bm[x,y,z]*mask[x,y,z]
    else:
        data = bm[x,y,z]
    data.shape = lats.shape

    p.subplot(1,3,index+1)
    map.drawmapboundary()
    map.drawmeridians(n.arange(0, 360, 30))
    map.drawparallels(n.arange(0, 90, 10))

    if opts.max is None: max = data.max()
    else: max = opts.max
    if opts.drng is None:
        min = data.min()
#    if min < (max - 10): min = max-10
    else: min = max - opts.drng
    step = (max - min) / 10
    levels = n.arange(min-step, max+step, step)
    print min,max
#data = data.clip(min, max)
#data = n.ma.array(data, mask=mask)
#min=0
    if bm == diff:
        max,min = .03,-.03
    map.imshow(data, vmax=max, vmin=min, cmap=cmap)
#map.contourf(cx,cy,data,levels,linewidth=0,cmap=cmap)
    p.colorbar(shrink=0.5)

p.show()
