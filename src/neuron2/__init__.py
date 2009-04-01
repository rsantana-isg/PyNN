# encoding: utf-8
"""
nrnpython implementation of the PyNN API.
                                                      
$Id:__init__.py 188 2008-01-29 10:03:59Z apdavison $
"""
__version__ = "$Rev: 191 $"

from pyNN.random import *
from pyNN.neuron2 import simulator
from pyNN import common, utility
from pyNN.neuron2.cells import *
from pyNN.neuron2.connectors import *
from pyNN.neuron2.synapses import *
from pyNN.neuron2.electrodes import *

from math import *
import sys
import numpy
import logging
import operator

# Global variables
quit_on_end = True
recorder_list = []

# ==============================================================================
#   Functions for simulation set-up and control
# ==============================================================================

def setup(timestep=0.1, min_delay=0.1, max_delay=10.0, debug=False,**extra_params):
    """
    Should be called at the very beginning of a script.
    extra_params contains any keyword arguments that are required by a given
    simulator but not by others.
    """
    global quit_on_end
    if not simulator.state.initialized:
        utility.init_logging("neuron2.log", debug, num_processes(), rank())
        logging.info("Initialization of NEURON (use setup(.., debug=True) to see a full logfile)")
        simulator.state.initialized = True
    simulator.state.dt = timestep
    simulator.state.min_delay = min_delay
    simulator.reset()
    if 'quit_on_end' in extra_params:
        quit_on_end = extra_params['quit_on_end']
    if extra_params.has_key('use_cvode'):
        simulator.state.cvode.active(int(extra_params['use_cvode']))
    return rank()

def end(compatible_output=True):
    """Do any necessary cleaning up before exiting."""
    for recorder in simulator.recorder_list:
        recorder.write(gather=False, compatible_output=compatible_output)
    simulator.finalize(quit_on_end)
        
def run(simtime):
    """Run the simulation for simtime ms."""
    simulator.run(simtime)

# ==============================================================================
#   Functions returning information about the simulation state
# ==============================================================================

def get_current_time():
    """Return the current time in the simulation."""
    return simulator.state.t
#common.get_current_time = get_current_time

def get_time_step():
    return simulator.state.dt
#common.get_time_step = get_time_step

def get_min_delay():
    return simulator.state.min_delay
common.get_min_delay = get_min_delay

def num_processes():
    return simulator.state.num_processes

def rank():
    """Return the MPI rank."""
    return simulator.state.mpi_rank

def list_standard_models():
    return [obj for obj in globals().values() if isinstance(obj, type) and issubclass(obj, common.StandardCellType)]

class ID(int, common.IDMixin):
    
    def __init__(self, n):
        int.__init__(n)
        common.IDMixin.__init__(self)
    
    def _build_cell(self, cell_model, cell_parameters, parent=None):
        gid = int(self)
        self._cell = cell_model(**cell_parameters)          # create the cell object
        simulator.register_gid(gid, self._cell.source, section=self._cell) # not adequate for multi-compartmental cells
        self.parent = parent
    
    def get_native_parameters(self):
        D = {}
        for name in self._cell.parameter_names:
            D[name] = getattr(self._cell, name)
        return D
    
    def set_native_parameters(self, parameters):
        for name, val in parameters.items():
            setattr(self._cell, name, val)
            

# ==============================================================================
#   Low-level API for creating, connecting and recording from individual neurons
# ==============================================================================

def _create(cellclass, cellparams, n, parent=None):
    """
    Function used by both `create()` and `Population.__init__()`
    """
    assert n > 0, 'n must be a positive integer'
    if isinstance(cellclass, basestring): # cell defined in hoc template
        try:
            cell_model = getattr(simulator.h, cellclass)
        except AttributeError:
            raise common.InvalidModelError("There is no hoc template called %s" % cellclass)
        cell_parameters = cellparams or {}
    elif isinstance(cellclass, type) and issubclass(cellclass, common.StandardCellType):
        celltype = cellclass(cellparams)
        cell_model = celltype.model
        cell_parameters = celltype.parameters
    else:
        cell_model = cellclass
        cell_parameters = cellparams
    first_id = simulator.state.gid_counter
    last_id = simulator.state.gid_counter + n - 1
    all_ids = numpy.array([id for id in range(first_id, last_id+1)], ID)
    # mask_local is used to extract those elements from arrays that apply to the cells on the current node
    mask_local = all_ids%num_processes()==rank() # round-robin distribution of cells between nodes
    for i,(id,is_local) in enumerate(zip(all_ids, mask_local)):
        if is_local:
            all_ids[i] = ID(id)
            all_ids[i]._build_cell(cell_model, cell_parameters, parent=parent)
    simulator.initializer.register(*all_ids[mask_local])
    simulator.state.gid_counter += n
    return all_ids, mask_local, first_id, last_id

create = common.build_create(_create)

def connect(source, target, weight=None, delay=None, synapse_type=None, p=1, rng=None):
    """Connect a source of spikes to a synaptic target. source and target can
    both be individual cells or lists of cells, in which case all possible
    connections are made with probability p, using either the random number
    generator supplied, or the default rng otherwise.
    Weights should be in nA or µS."""
    logging.debug("connecting %s to %s on host %d" % (source, target, rank()))
    if not common.is_listlike(source):
        source = [source]
    if not common.is_listlike(target):
        target = [target]
    if p < 1:
        rng = rng or numpy.random
    connection_list = []
    for tgt in target:
        sources = numpy.array(source)
        if p < 1:
            rarr = rng.uniform(0, 1, len(source))
            sources = sources[rarr<p]
        for src in sources:
            nc = simulator.single_connect(src, tgt, weight, delay, synapse_type)
            connection_list.append(nc)
    return connection_list

set = common.set

def record(source, filename):
    """Record spikes to a file. source can be an individual cell or a list of
    cells."""
    # would actually like to be able to record to an array and choose later
    # whether to write to a file.
    if not hasattr(source, '__len__'):
        source = [source]
    recorder = simulator.Recorder('spikes', file=filename)
    recorder.record(source)
    simulator.recorder_list.append(recorder)

def record_v(source, filename):
    """
    Record membrane potential to a file. source can be an individual cell or
    a list of cells."""
    # would actually like to be able to record to an array and
    # choose later whether to write to a file.
    if not hasattr(source, '__len__'):
        source = [source]
    recorder = simulator.Recorder('v', file=filename)
    recorder.record(source)
    simulator.recorder_list.append(recorder)

# ==============================================================================
#   High-level API for creating, connecting and recording from populations of
#   neurons.
# ==============================================================================

class Population(common.Population):
    """
    An array of neurons all of the same type. `Population' is used as a generic
    term intended to include layers, columns, nuclei, etc., of cells.
    All cells have both an address (a tuple) and an id (an integer). If p is a
    Population object, the address and id can be inter-converted using :
    id = p[address]
    address = p.locate(id)
    """
    nPop = 0
    
    def __init__(self, dims, cellclass, cellparams=None, label=None):
        """
        dims should be a tuple containing the population dimensions, or a single
          integer, for a one-dimensional population.
          e.g., (10,10) will create a two-dimensional population of size 10x10.
        cellclass should either be a standardized cell class (a class inheriting
        from common.StandardCellType) or a string giving the name of the
        simulator-specific model that makes up the population.
        cellparams should be a dict which is passed to the neuron model
          constructor
        label is an optional name for the population.
        """
        common.Population.__init__(self, dims, cellclass, cellparams, label)
        self.recorders = {'spikes': simulator.Recorder('spikes', population=self),
                          'v': simulator.Recorder('v', population=self)}
        self.label = self.label or 'population%d' % Population.nPop
        if isinstance(cellclass, type) and issubclass(cellclass, common.StandardCellType):
            self.celltype = cellclass(cellparams)
        else:
            self.celltype = cellclass

        # Build the arrays of cell ids
        # Cells on the local node are represented as ID objects, other cells by integers
        # All are stored in a single numpy array for easy lookup by address
        # The local cells are also stored in a list, for easy iteration
        self.all_cells, self._mask_local, self.first_id, self.last_id = _create(cellclass, cellparams, self.size, parent=self)
        self.local_cells = self.all_cells[self._mask_local]
        self.all_cells = self.all_cells.reshape(self.dim)
        self._mask_local = self._mask_local.reshape(self.dim)
        self.cell = self.all_cells # temporary, awaiting harmonisation
        
        simulator.initializer.register(self)
        Population.nPop += 1
        logging.info(self.describe('Creating Population "$label" of shape $dim, '+
                                   'containing `$celltype`s with indices between $first_id and $last_id'))
        logging.debug(self.describe())
    
    def __getitem__(self, addr):
        """Return a representation of the cell with coordinates given by addr,
           suitable for being passed to other methods that require a cell id.
           Note that __getitem__ is called when using [] access, e.g.
             p = Population(...)
             p[2,3] is equivalent to p.__getitem__((2,3)).
        """
        if isinstance(addr, int):
            addr = (addr,)
        if len(addr) == self.ndim:
            id = self.all_cells[addr]
        else:
            raise common.InvalidDimensionsError, "Population has %d dimensions. Address was %s" % (self.ndim, str(addr))
        if addr != self.locate(id):
            raise IndexError, 'Invalid cell address %s' % str(addr)
        return id
    
    def __iter__(self):
        """Iterator over cell ids on the local node."""
        return iter(self.local_cells)

    def __address_gen(self):
        """
        Generator to produce an iterator over all cells on this node,
        returning addresses.
        """
        for i in self.__iter__():
            yield self.locate(i)

    def addresses(self):
        """Iterator over cell addresses."""
        return self.__address_gen()

    def ids(self):
        """Iterator over cell ids on the local node."""
        return self.__iter__()
    
    def all(self):
        """Iterator over cell ids on all nodes."""
        return self.all_cells.flat
    
    def locate(self, id):
        """Given an element id in a Population, return the coordinates.
               e.g. for  4 6  , element 2 has coordinates (1,0) and value 7
                         7 9
        """
        id = id - self.first_id
        if self.ndim == 3:
            rows = self.dim[1]; cols = self.dim[2]
            i = id/(rows*cols); remainder = id%(rows*cols)
            j = remainder/cols; k = remainder%cols
            coords = (i,j,k)
        elif self.ndim == 2:
            cols = self.dim[1]
            i = id/cols; j = id%cols
            coords = (i,j)
        elif self.ndim == 1:
            coords = (id,)
        else:
            raise common.InvalidDimensionsError
        return coords

    def index(self, n):
        """Return the nth cell in the population (Indexing starts at 0)."""
        if hasattr(n, '__len__'):
            n = numpy.array(n)
        return self.all_cells.flatten()[n]

    def get(self, parameter_name, as_array=False):
        """
        Get the values of a parameter for every cell in the population.
        """
        values = [getattr(cell, parameter_name) for cell in self]
        if as_array:
            values = numpy.array(values).reshape(self.dim)
        return values

    def set(self, param, val=None):
        """
        Set one or more parameters for every cell in the population. param
        can be a dict, in which case val should not be supplied, or a string
        giving the parameter name, in which case val is the parameter value.
        val can be a numeric value, or list of such (e.g. for setting spike times).
        e.g. p.set("tau_m",20.0).
             p.set({'tau_m':20,'v_rest':-65})
        """
        if isinstance(param, str):
            if isinstance(val, (str, float, int)):
                param_dict = {param: float(val)}
            elif isinstance(val, (list, numpy.ndarray)):
                param_dict = {param: val}
            else:
                raise common.InvalidParameterValueError
        elif isinstance(param, dict):
            param_dict = param
        else:
            raise common.InvalidParameterValueError
        logging.info("%s.set(%s)", self.label, param_dict)
        for cell in self:
            cell.set_parameters(**param_dict)
    
    def tset(self, parametername, value_array):
        """
        'Topographic' set. Set the value of parametername to the values in
        value_array, which must have the same dimensions as the Population.
        """
        if self.dim == value_array.shape: # the values are numbers or non-array objects
            local_values = value_array[self._mask_local]
            assert local_values.size == self.local_cells.size, "%d != %d" % (local_values.size, self.local_cells.size)
        elif len(value_array.shape) == len(self.dim)+1: # the values are themselves 1D arrays
            #values = numpy.reshape(value_array, (self.dim, value_array.size/self.size))
            local_values = value_array[self._mask_local] # not sure this works
        else:
            raise common.InvalidDimensionsError, "Population: %s, value_array: %s" % (str(self.dim),
                                                                                      str(value_array.shape))
        ##local_indices = numpy.array([cell.gid for cell in self]) - self.first_id
        ##values = values.take(local_indices) # take just the values for cells on this machine
        assert local_values.shape[0] == self.local_cells.size, "%d != %d" % (local_values.size, self.local_cells.size)
        try:
            logging.info("%s.tset('%s', array(shape=%s, min=%s, max=%s))",
                         self.label, parametername, value_array.shape,
                         value_array.min(), value_array.max())
        except TypeError: # min() and max() won't work for non-numeric values
            logging.info("%s.tset('%s', non_numeric_array(shape=%s))",
                         self.label, parametername, value_array.shape)
        # Set the values for each cell
        
        for cell, val in zip(self, local_values):
            setattr(cell, parametername, val)

    def rset(self, parametername, rand_distr):
        """
        'Random' set. Set the value of parametername to a value taken from
        rand_distr, which should be a RandomDistribution object.
        """
        # Note that we generate enough random numbers for all cells on all nodes
        # but use only those relevant to this node. This ensures that the
        # sequence of random numbers does not depend on the number of nodes,
        # provided that the same rng with the same seed is used on each node.
        if isinstance(rand_distr.rng, NativeRNG):
            rng = simulator.h.Random(rand_distr.rng.seed or 0)
            native_rand_distr = getattr(rng, rand_distr.name)
            rarr = [native_rand_distr(*rand_distr.parameters)] + [rng.repick() for i in range(self.all_cells.size-1)]
        else:
            rarr = rand_distr.next(n=self.all_cells.size)
        rarr = numpy.array(rarr)
        logging.info("%s.rset('%s', %s)", self.label, parametername, rand_distr)
        for cell,val in zip(self, rarr[self._mask_local.flatten()]):
            setattr(cell, parametername, val)

    def randomInit(self, rand_distr):
        """
        Set initial membrane potentials for all the cells in the population to
        random values.
        """
        self.rset('v_init', rand_distr)

    def __record(self, record_what, record_from=None, rng=None):
        """
        Private method called by record() and record_v().
        """
        fixed_list=False
        if isinstance(record_from, list): #record from the fixed list specified by user
            fixed_list=True
        elif record_from is None: # record from all cells:
            record_from = self.all_cells.flatten()
        elif isinstance(record_from, int): # record from a number of cells, selected at random  
            # Each node will record N/nhost cells...
            nrec = int(record_from/num_processes())
            if not rng:
                rng = numpy.random
            record_from = rng.permutation(self.all_cells.flatten())[0:nrec]
            # need ID objects, permutation returns integers
            # ???
        else:
            raise Exception("record_from must be either a list of cells or the number of cells to record from")
        # record_from is now a list or numpy array. We do not have to worry about whether the cells are
        # local because the Recorder object takes care of this.
        logging.info("%s.record('%s', %s)", self.label, record_what, record_from[:5])
        self.recorders[record_what].record(record_from)

    def record(self, record_from=None, rng=None):
        """
        If record_from is not given, record spikes from all cells in the Population.
        record_from can be an integer - the number of cells to record from, chosen
        at random (in this case a random number generator can also be supplied)
        - or a list containing the ids of the cells to record.
        """
        self.__record('spikes', record_from, rng)

    def record_v(self, record_from=None, rng=None):
        """
        If record_from is not given, record the membrane potential for all cells in
        the Population.
        record_from can be an integer - the number of cells to record from, chosen
        at random (in this case a random number generator can also be supplied)
        - or a list containing the ids of the cells to record.
        """
        self.__record('v', record_from, rng)

    def printSpikes(self, filename, gather=True, compatible_output=True):
        """
        Write spike times to file.

        If compatible_output is True, the format is "spiketime cell_id",
        where cell_id is the index of the cell counting along rows and down
        columns (and the extension of that for 3-D).
        This allows easy plotting of a `raster' plot of spiketimes, with one
        line for each cell.
        The timestep, first id, last id, and number of data points per cell are
        written in a header, indicated by a '#' at the beginning of the line.

        If compatible_output is False, the raw format produced by the simulator
        is used. This may be faster, since it avoids any post-processing of the
        spike files.

        For parallel simulators, if gather is True, all data will be gathered
        to the master node and a single output file created there. Otherwise, a
        file will be written on each node, containing only the cells simulated
        on that node.
        """
        self.recorders['spikes'].write(filename, gather, compatible_output)

    def print_v(self, filename, gather=True, compatible_output=True):
        """
        Write membrane potential traces to file.

        If compatible_output is True, the format is "v cell_id",
        where cell_id is the index of the cell counting along rows and down
        columns (and the extension of that for 3-D).
        The timestep, first id, last id, and number of data points per cell are
        written in a header, indicated by a '#' at the beginning of the line.

        If compatible_output is False, the raw format produced by the simulator
        is used. This may be faster, since it avoids any post-processing of the
        voltage files.

        For parallel simulators, if gather is True, all data will be gathered
        to the master node and a single output file created there. Otherwise, a
        file will be written on each node, containing only the cells simulated
        on that node.
        """
        self.recorders['v'].write(filename, gather, compatible_output)

    def getSpikes(self, gather=True):
        """
        Return a 2-column numpy array containing cell ids and spike times for
        recorded cells.
        """
        return self.recorders['spikes'].get(gather)

    def get_v(self, gather=True):
        """
        Return a 2-column numpy array containing cell ids and spike times for
        recorded cells.
        """
        return self.recorders['v'].get(gather)

    def meanSpikeCount(self, gather=True):
        """
        Returns the mean number of spikes per neuron.
        """
        n_spikes = len(self.recorders['spikes'].get(gather))
        n_rec = len(self.recorders['spikes'].recorded)
        return float(n_spikes)/n_rec


        
class Projection(common.Projection):
    """
    A container for all the connections of a given type (same synapse type and
    plasticity mechanisms) between two populations, together with methods to set
    parameters of those connections, including of plasticity mechanisms.
    """
    
    nProj = 0
    
    def __init__(self, presynaptic_population, postsynaptic_population, method,
                 source=None, target=None,
                 synapse_dynamics=None, label=None, rng=None):
        """
        presynaptic_population and postsynaptic_population - Population objects.
        
        source - string specifying which attribute of the presynaptic cell
                 signals action potentials
                 
        target - string specifying which synapse on the postsynaptic cell to
                 connect to
                 
        If source and/or target are not given, default values are used.
        
        method - a Connector object, encapsulating the algorithm to use for
                 connecting the neurons.
        
        synapse_dynamics - a `SynapseDynamics` object specifying which
        synaptic plasticity mechanisms to use.
        
        rng - since most of the connection methods need uniform random numbers,
        it is probably more convenient to specify a RNG object here rather
        than within method_parameters, particularly since some methods also use
        random numbers to give variability in the number of connections per cell.
        """
        common.Projection.__init__(self, presynaptic_population, postsynaptic_population, method,
                                   source, target, synapse_dynamics, label, rng)
        self.connections = []
        if not label:
            self.label = 'projection%d' % Projection.nProj
        if not rng:
            self.rng = NumpyRNG()
        self.synapse_type = target or 'excitatory'
        
        ## Deal with short-term synaptic plasticity
        if self.short_term_plasticity_mechanism:
            U = self._short_term_plasticity_parameters['U']
            tau_rec = self._short_term_plasticity_parameters['tau_rec']
            tau_facil = self._short_term_plasticity_parameters['tau_facil']
            u0 = self._short_term_plasticity_parameters['u0']
            for cell in self.post:
                cell._cell.use_Tsodyks_Markram_synapses(self.synapse_type, U, tau_rec, tau_facil, u0)
                
        ## Create connections
        method.connect(self)
            
        logging.info("--- Projection[%s].__init__() ---" %self.label)
               
        ## Deal with long-term synaptic plasticity
        if self.long_term_plasticity_mechanism:
            ddf = self.synapse_dynamics.slow.dendritic_delay_fraction
            if ddf > 0.5 and num_processes() > 1:
                # depending on delays, can run into problems with the delay from the
                # pre-synaptic neuron to the weight-adjuster mechanism being zero.
                # The best (only?) solution would be to create connections on the
                # node with the pre-synaptic neurons for ddf>0.5 and on the node
                # with the post-synaptic neuron (as is done now) for ddf<0.5
                raise Exception("STDP with dendritic_delay_fraction > 0.5 is not yet supported for parallel computation.")
            for c in self.connections:
                c.useSTDP(self.long_term_plasticity_mechanism, self._stdp_parameters, ddf)
        
        # Check none of the delays are out of bounds. This should be redundant,
        # as this should already have been done in the Connector object, so
        # we could probably remove it.
        delays = [c.nc.delay for c in self.connections]
        assert min(delays) >= get_min_delay()
        
        Projection.nProj += 1

    def __len__(self):
        """Return the total number of connections."""
        return len(self.connections)            
    
    # --- Methods for setting connection parameters ----------------------------
    
    def setWeights(self, w):
        """
        w can be a single number, in which case all weights are set to this
        value, or a list/1D array of length equal to the number of connections
        in the population.
        Weights should be in nA for current-based and µS for conductance-based
        synapses.
        """
        if isinstance(w, float) or isinstance(w, int):
            logging.info("Projection %s: setWeights(%s)" % (self.label, w))
            for c in self.connections:
                c.nc.weight[0] = w # should first check weight value is ok, i.e. +ve for conductance-based, -ve for inhibitory current-based, not outside the weight limits for STDP... 
        elif isinstance(w, list) or isinstance(w, numpy.ndarray):
            assert len(w) == len(self), "List of weights has length %d, Projection %s has length %d" % (len(w), self.label, len(self))
            logging.info("Projection %s: setWeights(iterable(min=%s, max=%s))" % (self.label, min(w), max(w)))
            for c, weight in zip(self.connections, w):
                c.nc.weight[0] = weight
        else:
            raise TypeError("Argument should be a numeric type (int, float...), a list, or a numpy array.")
        
    def setDelays(self, d):
        """
        d can be a single number, in which case all delays are set to this
        value, or a list/1D array of length equal to the number of connections
        in the population.
        """
        if isinstance(d, float) or isinstance(d, int):
            if d < get_min_delay():
                raise Exception("Delays must be greater than or equal to the minimum delay, currently %g ms" % get_min_delay())
            logging.info("Projection %s: setDelays(%s)" % (self.label, d))
            for c in self.connections:
                c.nc.delay = d
            # if we have STDP, need to update pre2wa and post2wa delays as well
            if self.synapse_dynamics and self.synapse_dynamics.slow:
                ddf = self.synapse_dynamics.slow.dendritic_delay_fraction
                for pre2wa, post2wa in self.stdp_connections:
                    pre2wa.delay = float(d)*(1-ddf)
                    post2wa.delay = float(d)*ddf
        elif isinstance(d, list) or isinstance(d, numpy.ndarray):
            d = numpy.array(d)
            if not (d-get_min_delay()>=0).all():
                raise Exception("Delays must be greater than or equal to the minimum delay, currently %g ms" % get_min_delay())
            assert len(d) == len(self), "List of delays has length %d, Projection %s has length %d" % (len(d), self.label, len(self))
            logging.info("Projection %s: setDelays(iterable(min=%s, max=%s))" % (self.label, min(d), max(d)))
            for c, delay in zip(self.connections, d):
                c.nc.delay = delay
            # if we have STDP, need to update pre2wa and post2wa delays as well
            if self.synapse_dynamics and self.synapse_dynamics.slow:
                ddf = self.synapse_dynamics.slow.dendritic_delay_fraction
                for (pre2wa, post2wa), delay in zip(self.stdp_connections, d):
                    pre2wa.delay = float(delay)*(1-ddf)
                    post2wa.delay = float(delay)*ddf
        else:
            raise TypeError("Argument should be a numeric type (int, float...), a list, or a numpy array.")
    
    def randomizeWeights(self, rand_distr):
        """
        Set weights to random values taken from rand_distr.
        """
        # If we have a native rng, we do the loops in hoc. Otherwise, we do the loops in
        # Python
        if isinstance(rand_distr.rng, NativeRNG):
            rarr = simulator.nativeRNG_pick(len(self),
                                            rand_distr.rng,
                                            rand_distr.name,
                                            rand_distr.parameters)
        else:       
            rarr = rand_distr.next(len(self))  
        logging.info("--- Projection[%s].__randomizeWeights__() ---" % self.label)
        self.setWeights(rarr)
    
    def randomizeDelays(self, rand_distr):
        """
        Set delays to random values taken from rand_distr.
        """
        # If we have a native rng, we do the loops in hoc. Otherwise, we do the loops in
        # Python
        if isinstance(rand_distr.rng, NativeRNG):
            rarr = simulator.nativeRNG_pick(len(self),
                                            rand_distr.rng,
                                            rand_distr.name,
                                            rand_distr.parameters)
        else:       
            rarr = rand_distr.next(len(self))  
        logging.info("--- Projection[%s].__randomizeDelays__() ---" % self.label)
        self.setDelays(rarr)
    
    # --- Methods for writing/reading information to/from file. ----------------
    
    def getWeights(self, format='list', gather=True):
        """
        Possible formats are: a list of length equal to the number of connections
        in the projection, a 2D weight array (with zero or None for non-existent
        connections).
        """
        if gather:
            raise Exception("getWeights() with gather=True not yet implemented")
        if format == 'list':
            weights = [c.nc.weight[0] for c in self.connections]
        elif format == 'array':
            weights = numpy.zeros((self.pre.size, self.post.size))
            pre_ids = self.pre.all_cells.flatten().tolist()
            post_ids = self.post.all_cells.flatten().tolist()
            for c in self.connections:
                weights[pre_ids.index(c.pre), post_ids.index(c.post)] = c.nc.weight[0]
        else:
            raise Exception("format must be 'list' or 'array'")
        return weights
            
    def getDelays(self, format='list', gather=True):
        """
        Possible formats are: a list of length equal to the number of connections
        in the projection, a 2D delay array (with None or 1e12 for non-existent
        connections).
        """
        if gather:
            raise Exception("getDelays() with gather=True not yet implemented")
        if format == 'list':
            delays = [c.nc.delay for c in self.connections]
        elif format == 'array':
            delays = 1e12*numpy.ones((self.pre.size, self.post.size))
            pre_ids = self.pre.all_cells.flatten().tolist()
            post_ids = self.post.all_cells.flatten().tolist()
            for c in self.connections:
                delays[pre_ids.index(c.pre), post_ids.index(c.post)] = c.nc.delay
        else:
            raise Exception("format must be 'list' or 'array'")
        return delays
            
    def saveConnections(self, filename, gather=False):
        """Save connections to file in a format suitable for reading in with the
        'fromFile' method."""
        if gather:
            raise Exception("saveConnections() with gather=True not yet implemented")
        elif num_processes() > 1:
            filename += '.%d' % rank()
        logging.debug("--- Projection[%s].__saveConnections__() ---" % self.label)
        f = open(filename, 'w', 10000)
        for c in self.connections:
            line = "%s%s\t%s%s\t%g\t%g\n" % (self.pre.label,
                                     self.pre.locate(c.pre),
                                     self.post.label,
                                     self.post.locate(c.post),
                                     c.nc.weight[0],
                                     c.nc.delay)
            line = line.replace('(','[').replace(')',']')
            f.write(line)
        f.close()

# ==============================================================================
#   Utility classes
# ==============================================================================

Timer = common.Timer

# ==============================================================================