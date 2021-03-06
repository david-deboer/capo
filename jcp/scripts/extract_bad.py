#! /usr/bin/env python

import aipy as a, sys, optparse, os

o = optparse.OptionParser()
a.scripting.add_standard_options(o, ant=True)
opts,args = o.parse_args(sys.argv[1:])

for filename in args:
    print filename, '->', filename+'E'
    uvi = a.miriad.UV(filename)
    if os.path.exists(filename+'E'):
        print '    File exists... skipping.'
        continue
    opts.ant='all,'+opts.ant
    a.scripting.uv_selector(uvi, ants=opts.ant)
    uvo = a.miriad.UV(filename+'E',status='new')
    uvo.init_from_uv(uvi)
    uvo.pipe(uvi,append2hist='Removed bad antennas.\n')
