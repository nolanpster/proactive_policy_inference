#!/usr/bin/env python
__author__ = 'Nolan Poulin, nipoulin@wpi.edu'

from MDP_EM.MDP_EM.inference_mdp import InferenceMDP

from copy import deepcopy
from MDP import MDP
import numpy as np


class MultiAgentMDP(MDP):
    """
    @brief Construct a Markov Decision Process.

    An MDP isdefined by an initial state, transition model --- the probability transition matrix, np.array prob[a][0,1]
    -- the probability of going from 0 to 1 with action a.  and reward function. We also keep track of a gamma value,
    for use by algorithms. The transition model is represented somewhat differently from the text.  Instead of T(s, a,
    s') being probability number for each state/action/state triplet, we instead have T(s, a) return a list of (p, s')
    pairs.  We also keep track of the possible states, terminal states, and actions for each state.  The input
    transitions is a dictionary: (state,action): list of next state and probability tuple.  AP: a set of atomic
    propositions. Each proposition is identified by an index between 0 -N.  L: the labeling function, implemented as a
    dictionary: state: a subset of AP.

    @param init_set Overrides the initial state value from a state to a list of initial states. see
           @c MDP.setInitialProbDist.
    """
    def __init__(self, init=None, action_dict={}, states=[], prob=dict([]), gamma=.9, AP=set([]), L=dict([]),
                 reward=dict([]), grid_map=None, act_prob=dict([]), init_set=None, prob_dtype=np.float64,
                 index_of_controllable_agent=0, infer_dtype=np.float64):
        """
        @brief Construct an MDP meant to perform inference.
        @param init @todo
        @param action_dict An entry for each agent index that lists the actionas available to them.
        @param states @todo
        @param prob @todo
        @param acc @todo
        @param gamma @todo
        @param AP @todo
        @param L @todo
        @param reward @todo
        @param grid_map @todo
        @param act_prob @todo
        @param ggk_centers a list of length G of Geodesic Gaussian Kernel locations in the grid.
        @param ogk_centers a list of length O of Ordinary Gaussian Kernel locations in the grid.
        @param kernel_sigmas a @ref numpy.array() of length G+O of standard deviations.
        """
        self.action_dict = action_dict
        self.num_agents = len(action_dict)
        self.joint_action_list = [str(agent_idx) + '_'+ act for agent_idx in xrange(self.num_agents) for act in
                                  self.action_dict[agent_idx]]

        self.controllable_agent_idx = index_of_controllable_agent
        self.uncontrollable_agent_indices = [idx for idx in xrange(self.num_agents) if idx is not
                                             self.controllable_agent_idx]
        self.executable_action_dict = {self.controllable_agent_idx:
                                       [str(self.controllable_agent_idx) + '_' + act for act in
                                        self.action_dict[self.controllable_agent_idx]]
                                       }
        self.executable_action_dict.update(
            {unc_agent_idx: [str(unc_agent_idx) + '_' + act for act in self.action_dict[unc_agent_idx]]
             for unc_agent_idx in self.uncontrollable_agent_indices})
# Perform super call with just one agent's action list (assumes the agents have same actions for now). Then
        # update self.action_list to be joint action space.
        super(self.__class__, self).__init__(init=init, action_list=self.action_dict[0], states=states, prob=prob,
                                             gamma=gamma, AP=AP, L=L, reward=reward, grid_map=grid_map,
                                             act_prob=act_prob, init_set=init_set, prob_dtype=prob_dtype)

        self.action_list = self.joint_action_list

        # Reset any values 'uninitialize' by base-class constructor. @TODO These variables are manually copied in
        # ProductMDPxDRA.reconfigureConditionalInitialValues(). That's a shitty hack. Fix that. xoxo Nolan
        # Current flow is:
        # 1) multi_agent_mdp = MultiAgentMDP()
        # 2) construct a prod_mdp_dra = ProductMDPxDRA() with the multi_agent_mdp as an argument
        #    a) Note that a ProductMDPxDRA is inititalized with an empty MDP()
        # 3) copy over necessary properties from the multi_agent_mdp to the prod_mdp_dra
        #    a) Some ProductMDPxDRA methods overload MDP() methods if they were constructed with a MultiAgentMDP() to
        #       give some semblance of polymorphism.
        # I essentially created the 'dreaded diamond'.
        # ------------ Must be manually referenced in ProductMDPxDRA.reconfigureConditionalInitialValues() ------------#
        self.controllable_agent_idx = index_of_controllable_agent
        self.uncontrollable_agent_indices = [idx for idx in xrange(self.num_agents) if idx is not
                                             self.controllable_agent_idx]
        self.executable_action_dict = {self.controllable_agent_idx:
                                       [str(self.controllable_agent_idx) + '_' + act for act in
                                        self.action_dict[self.controllable_agent_idx]]
                                       }
        self.executable_action_dict.update(
            {unc_agent_idx: [str(unc_agent_idx) + '_' + act for act in self.action_dict[unc_agent_idx]]
             for unc_agent_idx in self.uncontrollable_agent_indices})
        #### !!! This is the container for the TRUE environmental policy !!! ####
        self.env_policy = {agent_idx:{} for agent_idx in self.uncontrollable_agent_indices}
        ####                                                                 ####
        kernel_centers = [frozenset([0, 2, 4, 6, 8])]
        num_kernels_in_set = len(kernel_centers[0])
        kernel_sigmas = np.array([1.]*num_kernels_in_set, dtype=infer_dtype)
        self.infer_env_mdp = InferenceMDP(init=self.init,
            action_list=self.executable_action_dict[self.uncontrollable_agent_indices[0]], states=states,
            prob=deepcopy(self.prob), grid_map=self.grid_map, L=None, gg_kernel_centers=kernel_centers,
            kernel_sigmas=kernel_sigmas)

        self.env_policy = {agent_idx:{} for agent_idx in self.uncontrollable_agent_indices}

        # ------------- ------------ ----------- ------ end mandatory copy ------ ------------ ------------ -----------#

        # Initialize environmental policies.
        self.buildUniformEnvironmentPolicy()

    def buildProbDict(self):
        """
        @brief Given a dictionary of action probabilities, create the true prob mat dictionary structure.

        @note This is built in a turn-based arena
        """
        grid_prob = {}
        if self.neighbor_dict is None:
            self.buildNeighborDict()
        for act in self.action_list:
            grid_prob[act]=np.zeros((self.num_cells, self.num_cells), self.prob_dtype)
            for starting_cell in self.grid_cell_vec:
                for next_cell, act_to_next_state in self.neighbor_dict[starting_cell].iteritems():
                    grid_prob[act][starting_cell, next_cell] = self.act_prob[act]\
                        [self.act_prob_row_idx_of_grid_cell[starting_cell], self.action_list.index(act_to_next_state)]

        self.prob = {}
        for acting_agent in xrange(self.num_agents):
            joint_action_range = slice(acting_agent * self.num_actions, (acting_agent * self.num_actions) +
                                                                        self.num_actions)
            for joint_act, grid_act in zip(self.joint_action_list[joint_action_range], self.action_dict[acting_agent]):
                self.prob[joint_act] = np.zeros((self.num_states, self.num_states), self.prob_dtype)
                for state_0_idx, state_0 in enumerate(self.states):
                    for state_N_idx, state_N in enumerate(self.states):
                        for other_agent in xrange(self.num_agents):
                            if other_agent == acting_agent:
                                # Ignore this case, there's not entry in the transition matrix it.
                                pass
                            elif state_0[other_agent] != state_N[other_agent]:
                                # The other agent can't change positions when the acting_agent acts.
                                self.prob[joint_act][state_0_idx, state_N_idx] = 0.
                            else:
                                # Fill in transition probability for the acting agents motion.
                                self.prob[joint_act][state_0_idx, state_N_idx] = \
                                    grid_prob[grid_act][state_0[acting_agent], state_N[acting_agent]]

    def buildUniformEnvironmentPolicy(self, agent_idx=None):
        uninform_prob = 1.0/self.num_actions
        if agent_idx is None:
            # Assign uniform policy to all agents.
            for unc_agent_idx in self.uncontrollable_agent_indices:
                uniform_policy_dist = {act: deepcopy(uninform_prob) for act in
                                       self.executable_action_dict[unc_agent_idx]}
                self.env_policy[unc_agent_idx] = {state: deepcopy(uniform_policy_dist) for state in self.states}
        else:
            self.env_policy[agent_idx] = {state: deepcopy(uniform_policy_dist) for state in self.states}


    def makeUniformPolicy(self):
        uninform_prob = 1.0/self.num_actions
        uniform_policy_dist = {act: uninform_prob for act in self.executable_action_dict[self.controllable_agent_idx]}
        self.policy = {state: uniform_policy_dist.copy() for state in
                       self.states}