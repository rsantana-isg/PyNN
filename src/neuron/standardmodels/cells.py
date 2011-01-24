# encoding: utf-8
"""
Standard cells for the neuron module.

$Id: cells.py 873 2010-12-13 22:40:03Z apdavison $
"""

from pyNN.standardmodels import cells, build_translations
from pyNN import errors
from pyNN.neuron.cells import StandardIF, SingleCompartmentTraub, RandomSpikeSource, VectorSpikeSource, BretteGerstnerIF, GsfaGrrIF
from math import pi
import logging

logger = logging.getLogger("PyNN")


class IF_curr_alpha(cells.IF_curr_alpha):
    """Leaky integrate and fire model with fixed threshold and alpha-function-
    shaped post-synaptic current."""
    
    translations = build_translations(
        ('tau_m',      'tau_m'),
        ('cm',         'c_m'),
        ('v_rest',     'v_rest'),
        ('v_thresh',   'v_thresh'),
        ('v_reset',    'v_reset'),
        ('tau_refrac', 't_refrac'),
        ('i_offset',   'i_offset'),
        ('tau_syn_E',  'tau_e'),
        ('tau_syn_I',  'tau_i'),
    )
    model = StandardIF
    
    def __init__(self, parameters):
        cells.IF_curr_alpha.__init__(self, parameters) # checks supplied parameters and adds default
                                                        # values for not-specified parameters.
        self.parameters['syn_type']  = 'current'
        self.parameters['syn_shape'] = 'alpha'

class IF_curr_exp(cells.IF_curr_exp):
    """Leaky integrate and fire model with fixed threshold and
    decaying-exponential post-synaptic current. (Separate synaptic currents for
    excitatory and inhibitory synapses."""
    
    translations = build_translations(
        ('tau_m',      'tau_m'),
        ('cm',         'c_m'),
        ('v_rest',     'v_rest'),
        ('v_thresh',   'v_thresh'),
        ('v_reset',    'v_reset'),
        ('tau_refrac', 't_refrac'),
        ('i_offset',   'i_offset'),
        ('tau_syn_E',  'tau_e'),
        ('tau_syn_I',  'tau_i'),
    )
    model = StandardIF
    
    def __init__(self, parameters):
        cells.IF_curr_exp.__init__(self, parameters)
        self.parameters['syn_type']  = 'current'
        self.parameters['syn_shape'] = 'exp'


class IF_cond_alpha(cells.IF_cond_alpha):
    """Leaky integrate and fire model with fixed threshold and alpha-function-
    shaped post-synaptic conductance."""
    
    translations = build_translations(
        ('tau_m',      'tau_m'),
        ('cm',         'c_m'),
        ('v_rest',     'v_rest'),
        ('v_thresh',   'v_thresh'),
        ('v_reset',    'v_reset'),
        ('tau_refrac', 't_refrac'),
        ('i_offset',   'i_offset'),
        ('tau_syn_E',  'tau_e'),
        ('tau_syn_I',  'tau_i'),
        ('e_rev_E',    'e_e'),
        ('e_rev_I',    'e_i')
    )
    model = StandardIF
    
    def __init__(self, parameters):
        cells.IF_cond_alpha.__init__(self, parameters) # checks supplied parameters and adds default
                                                       # values for not-specified parameters.
        self.parameters['syn_type']  = 'conductance'
        self.parameters['syn_shape'] = 'alpha'


class IF_cond_exp(cells.IF_cond_exp):
    """Leaky integrate and fire model with fixed threshold and 
    exponentially-decaying post-synaptic conductance."""
    
    translations = build_translations(
        ('tau_m',      'tau_m'),
        ('cm',         'c_m'),
        ('v_rest',     'v_rest'),
        ('v_thresh',   'v_thresh'),
        ('v_reset',    'v_reset'),
        ('tau_refrac', 't_refrac'),
        ('i_offset',   'i_offset'),
        ('tau_syn_E',  'tau_e'),
        ('tau_syn_I',  'tau_i'),
        ('e_rev_E',    'e_e'),
        ('e_rev_I',    'e_i')
    )
    model = StandardIF
    
    def __init__(self, parameters):
        cells.IF_cond_exp.__init__(self, parameters) # checks supplied parameters and adds default
                                                       # values for not-specified parameters.
        self.parameters['syn_type']  = 'conductance'
        self.parameters['syn_shape'] = 'exp'


class IF_facets_hardware1(cells.IF_facets_hardware1):
    """Leaky integrate and fire model with conductance-based synapses and fixed
    threshold as it is resembled by the FACETS Hardware Stage 1. For further
    details regarding the hardware model see the FACETS-internal Wiki:
    https://facets.kip.uni-heidelberg.de/private/wiki/index.php/WP7_NNM
    """

    translations = build_translations(
        ('v_rest',     'v_rest'),
        ('v_thresh',   'v_thresh'),
        ('v_reset',    'v_reset'),
        ('g_leak',     'tau_m',    "0.2*1000.0/g_leak", "0.2*1000.0/tau_m"),
        ('tau_syn_E',  'tau_e'),
        ('tau_syn_I',  'tau_i'),
        ('e_rev_I',    'e_i')
    )
    model = StandardIF

    def __init__(self, parameters):
        cells.IF_facets_hardware1.__init__(self, parameters)
        self.parameters['syn_type']  = 'conductance'
        self.parameters['syn_shape'] = 'exp'
        self.parameters['i_offset']  = 0.0
        self.parameters['c_m']       = 0.2
        self.parameters['t_refrac']  = 1.0
        self.parameters['e_e']       = 0.0
    
       
class HH_cond_exp(cells.HH_cond_exp):
    
    translations = build_translations(
        ('gbar_Na',    'gbar_Na',   1e-3),   # uS -> mS
        ('gbar_K',     'gbar_K',    1e-3),    
        ('g_leak',     'g_leak',    1e-3),    
        ('cm',         'c_m'),  
        ('v_offset',   'v_offset'),
        ('e_rev_Na',   'ena'),
        ('e_rev_K',    'ek'), 
        ('e_rev_leak', 'e_leak'),
        ('e_rev_E',    'e_e'),
        ('e_rev_I',    'e_i'),
        ('tau_syn_E',  'tau_e'),
        ('tau_syn_I',  'tau_i'),
        ('i_offset',   'i_offset'),
    )
    model = SingleCompartmentTraub

    def __init__(self, parameters):
        cells.HH_cond_exp.__init__(self, parameters) # checks supplied parameters and adds default
                                                     # values for not-specified parameters.
        self.parameters['syn_type']  = 'conductance'
        self.parameters['syn_shape'] = 'exp'


class IF_cond_exp_gsfa_grr(cells.IF_cond_exp_gsfa_grr):
    """
    Linear leaky integrate and fire model with fixed threshold,
    decaying-exponential post-synaptic conductance, conductance based
    spike-frequency adaptation, and a conductance-based relative refractory
    mechanism.

    See: Muller et al (2007) Spike-frequency adapting neural ensembles: Beyond
    mean-adaptation and renewal theories. Neural Computation 19: 2958-3010.

    See also: EIF_cond_alpha_isfa_ista
    """
    translations = build_translations(
        ('v_rest',     'v_reset'),
        ('v_reset',    'v_reset'),
        ('cm',         'c_m'),
        ('tau_m',      'tau_m'),
        ('tau_refrac', 't_refrac'),
        ('tau_syn_E',  'tau_e'),
        ('tau_syn_I',  'tau_i'),
        ('v_thresh',   'v_thresh'),
        ('i_offset',   'i_offset'),
        ('e_rev_E',    'e_e'),
        ('e_rev_I',    'e_i'),
        ('tau_sfa',    'tau_sfa'),
        ('e_rev_sfa',  'e_sfa'),
        ('q_sfa',      'q_sfa'),
        ('tau_rr',     'tau_rr'),
        ('e_rev_rr',   'e_rr'),
        ('q_rr',       'q_rr')
    )
    model = GsfaGrrIF
    
    def __init__(self, parameters):
        cells.IF_cond_exp_gsfa_grr.__init__(self, parameters) # checks supplied parameters and adds default
                                                              # values for not-specified parameters.
        self.parameters['syn_type']  = 'conductance'
        self.parameters['syn_shape'] = 'exp'



class SpikeSourcePoisson(cells.SpikeSourcePoisson):
    """Spike source, generating spikes according to a Poisson process."""

    translations = build_translations(
        ('start',    'start'),
        ('rate',     '_interval',  "1000.0/rate",  "1000.0/_interval"),
        ('duration', 'duration'),
    )
    model = RandomSpikeSource


class SpikeSourceArray(cells.SpikeSourceArray):
    """Spike source generating spikes at the times given in the spike_times array."""

    translations = build_translations(
        ('spike_times', 'spike_times'),
    )
    model = VectorSpikeSource
       
        
class EIF_cond_alpha_isfa_ista(cells.EIF_cond_alpha_isfa_ista):
    """
    Exponential integrate and fire neuron with spike triggered and sub-threshold
    adaptation currents (isfa, ista reps.) according to:
    
    Brette R and Gerstner W (2005) Adaptive Exponential Integrate-and-Fire Model as
    an Effective Description of Neuronal Activity. J Neurophysiol 94:3637-3642

    See also: IF_cond_exp_gsfa_grr
    """
    
    translations = build_translations(
        ('cm',         'c_m'),
        ('tau_refrac', 't_refrac'), 
        ('v_spike',    'v_spike'),
        ('v_reset',    'v_reset'),
        ('v_rest',     'v_rest'),
        ('tau_m',      'tau_m'),
        ('i_offset',   'i_offset'), 
        ('a',          'A',        0.001), # nS --> uS
        ('b',          'B'),
        ('delta_T',    'delta'), 
        ('tau_w',      'tau_w'), 
        ('v_thresh',   'v_thresh'), 
        ('e_rev_E',    'e_e'),
        ('tau_syn_E',  'tau_e'), 
        ('e_rev_I',    'e_i'), 
        ('tau_syn_I',  'tau_i'),
    )
    model = BretteGerstnerIF
    
    def __init__(self, parameters):
        cells.EIF_cond_alpha_isfa_ista.__init__(self, parameters)
        self.parameters['syn_type']  = 'conductance'
        self.parameters['syn_shape'] = 'alpha'

class EIF_cond_exp_isfa_ista(cells.EIF_cond_exp_isfa_ista):
    """Like EIF_cond_alpha_isfa_ista, but with single-exponential synapses."""
    
    translations = EIF_cond_alpha_isfa_ista.translations
    model = BretteGerstnerIF
    
    def __init__(self, parameters):
        cells.EIF_cond_exp_isfa_ista.__init__(self, parameters)
        self.parameters['syn_type']  = 'conductance'
        self.parameters['syn_shape'] = 'exp'