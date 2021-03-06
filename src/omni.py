import numpy as np, omnical, aipy, math
import capo.red as red
import numpy.linalg as la
import warnings
with warnings.catch_warnings():
    warnings.filterwarnings("ignore",category=DeprecationWarning)
    import scipy.sparse as sps
    
POL_TYPES = 'xylrab'
#XXX this can't support restarts or changing # pols between runs
POLNUM = {} # factor to multiply ant index for internal ordering, 
NUMPOL = {}

def add_pol(p):
    global NUMPOL
    assert(p in POL_TYPES)
    POLNUM[p] = len(POLNUM)
    NUMPOL = dict(zip(POLNUM.values(), POLNUM.keys()))
    
class Antpol:
    def __init__(self, *args):
        try:
            ant,pol,nant = args
            if not POLNUM.has_key(pol): add_pol(pol)
            self.val, self.nant = POLNUM[pol] * nant + ant, nant
        except(ValueError): self.val, self.nant = args
    def antpol(self): return self.val % self.nant, NUMPOL[self.val / self.nant]
    def ant(self): return self.antpol()[0]
    def pol(self): return self.antpol()[1]
    def __int__(self): return self.val
    def __hash__(self): return self.ant()
    def __str__(self): return ''.join(map(str, self.antpol()))
    def __eq__(self, v): return self.ant() == v
    def __repr__(self): return str(self)
        
## XXX filter_reds w/ pol support should probably be in omnical
def filter_reds(reds, bls=None, ex_bls=None, ants=None, ex_ants=None, ubls=None, ex_ubls=None, crosspols=None, ex_crosspols=None):
    '''Filter redundancies to include/exclude the specified bls, antennas, and unique bl groups and polarizations.
    Assumes reds indices are Antpol objects.'''
    def pol(bl): return bl[0].pol() + bl[1].pol()
    if crosspols: reds = [r for r in reds if pol(r[0]) in crosspols]
    if ex_crosspols: reds = [r for r in reds if not pol(r[0]) in ex_crosspols]
    return omnical.arrayinfo.filter_reds(reds, bls=bls, ex_bls=ex_bls, ants=ants, ex_ants=ex_ants, ubls=ubls, ex_ubls=ex_ubls)

class RedundantInfo(omnical.info.RedundantInfo):
    def __init__(self, nant, filename=None):
        omnical.info.RedundantInfo.__init__(self, filename=filename)
        self.nant = nant
    def bl_order(self):
        '''Return (i,j) baseline tuples in the order that they should appear in data.  Antenna indicies
        are in real-world order (as opposed to the internal ordering used in subsetant).'''
        return [(Antpol(self.subsetant[i],self.nant),Antpol(self.subsetant[j],self.nant)) for (i,j) in self.bl2d]
    def order_data(self, dd):
        '''Create a data array ordered for use in _omnical.redcal.  'dd' is
        a dict whose keys are (i,j) antenna tuples; antennas i,j should be ordered to reflect
        the conjugation convention of the provided data.  'dd' values are 2D arrays
        of (time,freq) data.'''
        d = []
        for i,j in self.bl_order():
            bl = (i.ant(),j.ant())
            pol = i.pol() + j.pol()
            try: d.append(dd[bl][pol])
            except(KeyError): d.append(dd[bl[::-1]][pol[::-1]].conj())
        return np.array(d).transpose((1,2,0))

class FirstCalRedundantInfo(omnical.info.FirstCalRedundantInfo):
    def __init__(self, nant):
        omnical.info.FirstCalRedundantInfo.__init__(self)
        self.nant = nant
        print 'Loading FirstCalRedundantInfo class' 

def compute_reds(nant, pols, *args, **kwargs):
    _reds = omnical.arrayinfo.compute_reds(*args, **kwargs)
    reds = []
    for pi in pols:
        for pj in pols:
            reds += [[(Antpol(i,pi,nant),Antpol(j,pj,nant)) for i,j in gp] for gp in _reds]
    return reds
 
#def aa_to_info(aa, pols=['x'], **kwargs):
#    '''Use aa.ant_layout to generate redundances based on ideal placement.
#    The remaining arguments are passed to omnical.arrayinfo.filter_reds()'''
#    layout = aa.ant_layout
#    nant = len(aa)
#    antpos = -np.ones((nant*len(pols),3)) # -1 to flag unused antennas
#    xs,ys = np.indices(layout.shape)
#    for ant,x,y in zip(layout.flatten(), xs.flatten(), ys.flatten()):
#        for z,pol in enumerate(pols):
#            z = 2**z # exponential ensures diff xpols aren't redundant w/ each other
#            i = Antpol(ant,pol,len(aa)) # creates index in POLNUM/NUMPOL for pol
#            antpos[i,0],antpos[i,1],antpos[i,2] = x,y,z
#    reds = compute_reds(nant, pols, antpos[:nant],tol=.1) # only first nant b/c compute_reds treats pol redundancy separately
#    # XXX haven't enforced xy = yx yet.  need to conjoin red groups for that
#    ex_ants = [Antpol(i,nant).ant() for i in range(antpos.shape[0]) if antpos[i,0] < 0]
#    kwargs['ex_ants'] = kwargs.get('ex_ants',[]) + ex_ants
#    reds = filter_reds(reds, **kwargs)
#    info = RedundantInfo(nant)
#    info.init_from_reds(reds,antpos)
#    return info

def aa_to_info(aa, pols=['x'], fcal=False, **kwargs):
    '''Use aa.ant_layout to generate redundances based on ideal placement.
        The remaining arguments are passed to omnical.arrayinfo.filter_reds()'''
    nant = len(aa)
    try:
        antpos_ideal = aa.antpos_ideal
        xs,ys,zs = antpos_ideal.T
        layout = np.arange(len(xs))
        #antpos = np.concatenat([antpos_ideal for i in len(pols)])
    except(AttributeError):
        layout = aa.ant_layout
        xs,ys = np.indices(layout.shape)
    antpos = -np.ones((nant*len(pols),3)) #remake antpos with pol information. -1 to flag
    for ant,x,y in zip(layout.flatten(), xs.flatten(), ys.flatten()):
        for z, pol in enumerate(pols):
            z = 2**z
            i = Antpol(ant, pol, len(aa))
            antpos[i,0], antpos[i,1], antpos[i,2] = x,y,z
    reds = compute_reds(nant, pols, antpos[:nant], tol=.1)
    ex_ants = [Antpol(i,nant).ant() for i in range(antpos.shape[0]) if antpos[i,0] == -1]
    kwargs['ex_ants'] = kwargs.get('ex_ants',[]) + ex_ants
    reds = filter_reds(reds, **kwargs)
    if fcal:
        info = FirstCalRedundantInfo(nant)
    else:
        info = RedundantInfo(nant)
    info.init_from_reds(reds,antpos)
    return info

#generate info from real positions
####################################################################################################
def aa_pos_to_info(aa, pols=['x'], **kwargs):
    '''Use aa.ant_layout to generate redundances based on real placement.
        The remaining arguments are passed to omnical.arrayinfo.filter_reds()'''
    nant = len(aa)
    antpos = -np.ones((nant*len(pols),3)) # -1 to flag unused antennas
    xmin = 0
    ymin = 0
    for ant in xrange(nant):  #trying to shift the crd to make sure they are positive
        bl = aa.get_baseline(0,ant,src='z')
        x,y = bl[0], bl[1]
        if x < xmin: xmin = x
        if y < ymin: ymin = y
    for ant in xrange(nant):
        bl = aa.get_baseline(0,ant,src='z')
        x,y = bl[0] - xmin + 0.1, bl[1] - ymin + 0.1  #w is currently not included
        for z,pol in enumerate(pols):
            z = 2**z # exponential ensures diff xpols aren't redundant w/ each other
            i = Antpol(ant,pol,len(aa)) # creates index in POLNUM/NUMPOL for pol
            antpos[i,0],antpos[i,1],antpos[i,2] = x,y,z
    reds = compute_reds(nant, pols, antpos[:nant],tol=0.0001) # only first nant b/c compute_reds treats pol redundancy separately
    # XXX haven't enforced xy = yx yet.  need to conjoin red groups for that
    ex_ants = [Antpol(i,nant).ant() for i in range(antpos.shape[0]) if antpos[i,0] < 0]
    kwargs['ex_ants'] = kwargs.get('ex_ants',[]) + ex_ants
    reds = filter_reds(reds, **kwargs)
    info = RedundantInfo(nant)
    info.init_from_reds(reds,antpos)
    return info
####################################################################################################


def redcal(data, info, xtalk=None, gains=None, vis=None,removedegen=False, uselogcal=True, maxiter=50, conv=1e-3, stepsize=.3, computeUBLFit=True, trust_period=1):
    #add layer to support new gains format
    if gains:
        _gains = {}
        for pol in gains:
            for i in gains[pol]:
                ai = Antpol(i,pol,info.nant)
                _gains[int(ai)] = gains[pol][i].conj()
    else: _gains = gains
    if vis:
        _vis = {}
        for pol in vis:
            for i,j in vis[pol]:
                ai,aj = Antpol(i,pol[0],info.nant), Antpol(j,pol[1],info.nant)
                _vis[(int(ai),int(aj))] = vis[pol][(i,j)]
    else: _vis = vis
    meta, gains, vis = omnical.calib.redcal(data, info, xtalk=xtalk, gains=_gains, vis=_vis, removedegen=removedegen, uselogcal=uselogcal, maxiter=maxiter, conv=conv, stepsize=stepsize, computeUBLFit=computeUBLFit, trust_period=trust_period)    
    # rewrap to new format
    def mk_ap(a): return Antpol(a, info.nant)
    for i,j in meta['res'].keys():
        api,apj = mk_ap(i),mk_ap(j)
        pol = api.pol() + apj.pol()
        bl = (api.ant(), apj.ant())
        if not meta['res'].has_key(pol): meta['res'][pol] = {}
        meta['res'][pol][bl] = meta['res'].pop((i,j))
    #XXX make chisq a nested dict, with individual antpol keys?
    for k in [k for k in meta.keys() if k.startswith('chisq')]:
        try:
            ant = int(k.split('chisq')[1])
            meta['chisq'+str(mk_ap(ant))] = meta.pop(k)
        except(ValueError): pass
    for i in gains.keys():
        ap = mk_ap(i)
        if not gains.has_key(ap.pol()): gains[ap.pol()] = {}
        gains[ap.pol()][ap.ant()] = gains.pop(i).conj()
    for i,j in vis.keys():
        api,apj = mk_ap(i),mk_ap(j)
        pol = api.pol() + apj.pol()
        bl = (api.ant(), apj.ant())
        if not vis.has_key(pol): vis[pol] = {}
        vis[pol][bl] = vis.pop((i,j))
    return meta, gains, vis

def compute_xtalk(res, wgts):
    '''Estimate xtalk as time-average of omnical residuals.'''
    xtalk = {}
    for pol in res.keys():
        xtalk[pol] = {}
        for key in res[pol]: 
            r,w = np.where(wgts[pol][key] > 0, res[pol][key], 0), wgts[pol][key].sum(axis=0)
            w = np.where(w == 0, 1, w)
            xtalk[pol][key] = (r.sum(axis=0) / w).astype(res[pol][key].dtype) # avg over time
    return xtalk

def to_npz(filename, meta, gains, vismdl, xtalk):
    '''Write results from omnical.calib.redcal (meta,gains,vismdl,xtalk) to npz file.
    Each of these is assumed to be a dict keyed by pol, and then by bl/ant/keyword'''
    d = {}
    metakeys = ['jds','lsts','freqs','history']#,chisq]
    for key in meta:
        if key.startswith('chisq'): d[key] = meta[key] #separate if statements  pending changes to chisqs
        for k in metakeys: 
            if key.startswith(k): d[key] = meta[key]
    for pol in gains:
        for ant in gains[pol]:
            d['%d%s' % (ant,pol)] = gains[pol][ant] 
    for pol in vismdl:
        for bl in vismdl[pol]:
            d['<%d,%d> %s' % (bl[0],bl[1],pol)] = vismdl[pol][bl]
    for pol in xtalk:
        for bl in xtalk[pol]: 
            d['(%d,%d) %s' % (bl[0],bl[1],pol)] = xtalk[pol][bl]
    np.savez(filename,**d)

def from_npz(filename, verbose=False):
    '''Reconstitute results from to_npz, returns meta, gains, vismdl, xtalk, each
    keyed first by polarization, and then by bl/ant/keyword.'''
    if type(filename) is str: filename = [filename]
    meta, gains, vismdl, xtalk = {}, {}, {}, {}
    def parse_key(k):
        bl,pol = k.split()
        bl = tuple(map(int,bl[1:-1].split(',')))
        return pol,bl
    for f in filename:
        if verbose: print 'Reading', f
        npz = np.load(f)
        for k in [f for f in npz.files if f.startswith('<')]:
            pol,bl = parse_key(k)
            if not vismdl.has_key(pol): vismdl[pol] = {}
            vismdl[pol][bl] = vismdl[pol].get(bl,[]) + [np.copy(npz[k])]
        for k in [f for f in npz.files if f.startswith('(')]:
            pol,bl = parse_key(k)
            if not xtalk.has_key(pol): xtalk[pol] = {}
            dat = np.resize(np.copy(npz[k]),vismdl[pol][vismdl[pol].keys()[0]][0].shape) #resize xtalk to be like vismdl (with a time dimension too)
            if xtalk[pol].get(bl) is None: #no bl key yet
                xtalk[pol][bl] = dat
            else: #append to array
                xtalk[pol][bl] = np.vstack((xtalk[pol].get(bl),dat))
        for k in [f for f in npz.files if f[0].isdigit()]:
            pol,ant = k[-1:],int(k[:-1])
            if not gains.has_key(pol): gains[pol] = {}
            gains[pol][ant] = gains[pol].get(ant,[]) + [np.copy(npz[k])]
        kws = ['chi','hist','j','l','f']
        for kw in kws:
            for k in [f for f in npz.files if f.startswith(kw)]:
                meta[k] = meta.get(k,[]) + [np.copy(npz[k])]
    #for pol in xtalk: #this is already done above now
        #for bl in xtalk[pol]: xtalk[pol][bl] = np.concatenate(xtalk[pol][bl])
    for pol in vismdl:
        for bl in vismdl[pol]: vismdl[pol][bl] = np.concatenate(vismdl[pol][bl])
    for pol in gains:
        for bl in gains[pol]: gains[pol][bl] = np.concatenate(gains[pol][bl])
    for k in meta:
        try: meta[k] = np.concatenate(meta[k])
        except(ValueError): pass
    return meta, gains, vismdl, xtalk

class FirstCal(object):
    def __init__(self, data, fqs, info):
        self.data = data
        self.fqs = fqs
        self.info = info
    def data_to_delays(self, verbose=False, **kwargs):
        '''data = dictionary of visibilities. 
           info = FirstCalRedundantInfo class
           can give it kwargs:
                supports 'window': window function for fourier transform. default is none
           Returns a dictionary with keys baseline pairs and values delays.'''
        window=kwargs.get('window','none')
        tune=kwargs.get('tune','True')
        self.blpair2delay = {}
        dd = self.info.order_data(self.data)
#        ww = self.info.order_data(self.wgts)
        for (bl1,bl2) in self.info.bl_pairs:
            if verbose:
                print (bl1, bl2)
            d1 = dd[:,:,self.info.bl_index(bl1)]
#            w1 = ww[:,:,self.info.bl_index(bl1)]
            d2 = dd[:,:,self.info.bl_index(bl2)]
#            w2 = ww[:,:,self.info.bl_index(bl2)]
            #delay = red.redundant_bl_cal_simple(d1,w1,d2,w2,self.fqs)
            delay = red.redundant_bl_cal_simple(d1,d2,self.fqs,window=window,tune=tune)
            self.blpair2delay[(bl1,bl2)] = delay
        return self.blpair2delay
    def get_N(self,nblpairs):
        return np.identity(nblpairs) 
    def get_M(self, verbose=False, **kwargs):
        M = np.zeros((len(self.info.bl_pairs),1))
        blpair2delay = self.data_to_delays(verbose=verbose, **kwargs)
        for pair in blpair2delay:
            M[self.info.blpair_index(pair)] = blpair2delay[pair]
        return M
    def run(self, verbose=False, **kwargs):
        #make measurement matrix 
        self.M = self.get_M(verbose=verbose, **kwargs)
        #make noise matrix
        N = self.get_N(len(self.info.bl_pairs)) 
        self._N = np.linalg.inv(N)
        #get coefficients matrix,A
        self.A = self.info.A
        #solve for delays
        invert = np.dot(self.A.T,np.dot(self._N,self.A))
        dontinvert = np.dot(self.A.T,np.dot(self._N,self.M))
        self.xhat = np.dot(np.linalg.pinv(invert), dontinvert)
        #turn solutions into dictionary
        return dict(zip(self.info.subsetant,self.xhat))
    def get_solved_delay(self):
        solved_delays = []
        for pair in self.info.bl_pairs:
            ant_indexes = self.info.blpair2antind(pair)
            dlys = self.xhat[ant_indexes]
            solved_delays.append(dlys[0]-dlys[1]-dlys[2]+dlys[3])
        self.solved_delays = np.array(solved_delays)


def get_phase(fqs,tau):
    return np.exp(-2j*np.pi*fqs*tau)



