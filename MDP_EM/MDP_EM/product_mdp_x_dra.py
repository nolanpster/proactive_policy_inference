#!/usr/bin/env python
__author__ = 'Nolan Poulin, nipoulin@wpi.edu'
from policy_inference import PolicyInference
from feature_vector import FeatureVector
from copy import deepcopy
from MDP import MDP
from multi_agent_mdp import MultiAgentMDP

import numpy as np
from scipy import sparse


class ProductMDPxDRA(MDP):
    """A Markov Decision Process, defined by an initial state, transition model --- the probability transition matrix,
    np.array prob[a][0,1] -- the probability of going from 0 to 1 with action a.  and reward function. We also keep
    track of a gamma value, for use by algorithms. The transition model is represented somewhat differently from the
    text.  Instead of T(s, a, s') being probability number for each state/action/state triplet, we instead have T(s, a)
    return a list of (p, s') pairs.  We also keep track of the possible states, terminal states, and actions for each
    state.  The input transitions is a dictionary: (state,action): list of next state and probability tuple.  AP: a set
    of atomic propositions. Each proposition is identified by an index between 0 -N.  L: the labeling function,
    implemented as a dictionary: state: a subset of AP."""
    def __init__(self, mdp, dra, sink_action=None, sink_list=[], losing_sink_label=None, winning_reward=None,
                 prob_dtype=np.float64, winning_label=None, skip_product_calcs=False):
        """
        @brief
        """
        self.dra = deepcopy(dra)
        self.mdp = deepcopy(mdp)
        # Set self to be an MDP instance. Build the product ontop of this, then call setSinks again now that the object
        # is fully populated.
        super(self.__class__, self).__init__(prob_dtype=prob_dtype)
        # cell_state_slicer: used to extract indices from the tuple of states. The joint-state tuples are used as
        # dictionary keys and this class augments the state tuple from (mdp_state) to ((mdp_state),dra_state).
        self.state_slice_length = 1
        self.cell_state_slicer = slice(None, self.state_slice_length, None)
        self.gamma=mdp.gamma
        self.grid_map = deepcopy(mdp.grid_map)
        self.sink_action = sink_action
        self.losing_sink_label = losing_sink_label
        self.winning_label = winning_label

        self.product_calcs_skipped = skip_product_calcs
        self.computeProductMDPxDRA(mdp, dra, skip_product_calcs)
        self.reconfigureConditionalInitialValues()
        self.setSinks(sink_list)
        if winning_reward is not None:
            self.configureReward(winning_reward)
        self.makeUniformPolicy()

    def reconfigureConditionalInitialValues(self):

        super(self.__class__, self).reconfigureConditionalInitialValues()
        # I'm so sorry for this hack, in too much of a rush to figure out multiple inheritance. <3 Nolan
        self.controllable_agent_idx = self.mdp.controllable_agent_idx
        self.executable_action_dict = self.mdp.executable_action_dict
        if type(self.mdp) is MultiAgentMDP:
            self.uncontrollable_agent_indices = self.mdp.uncontrollable_agent_indices
            self.env_policy = self.mdp.env_policy # TRUE Env Policy
            self.infer_env_mdp = self.mdp.infer_env_mdp # Contains ESTIMATED Env Policy

            # Hacky shit: change self.mdp! self.mdp is going to be handed _augmented_ MDPxDRA states to deal with, so we
            # need to update it's slice operator.
            #self.mdp.cell_state_slicer = self.cell_state_slicer
            #self.mdp.prob = self.prob

    def computeProductMDPxDRA(self, mdp, dra, skip_product_calcs=False):
        if skip_product_calcs:
            if mdp.init is not None:
                init = (mdp.init,)
            else:
                init = tuple()
            if mdp.init_set is not None:
                self.init_set = [(m_i,) for m_i in mdp.init_set]
            self.init = init
            prod_states = [(state,) for state in mdp.states]
            self.L ={(state,): label for state, label in mdp.L.iteritems()}
            N = len(prod_states)
            self.action_list = list(mdp.action_list)
            self.states = list(prod_states)
            self.prob = mdp.prob
            mdp_acc = set([])
            for state in self.states:
                if mdp.L[state[mdp.cell_state_slicer][0]] == self.winning_label:
                    mdp_acc.add(state,)
            self.acc = [(mdp_acc,)]
        else:
            # Create product MDP-times-DRA
            if mdp.init is not None:
                init = (mdp.init, dra.get_transition(mdp.L[mdp.init], dra.initial_state))
            else:
                init = tuple()
            if mdp.init_set is not None:
                self.init_set = [(m_i, dra.get_transition(mdp.L[m_i], dra.initial_state)) for m_i in mdp.init_set]
            self.init = init
            prod_states = []
            for _s in mdp.states:
                for _q in dra.states:
                    prod_states.append((_s, _q))
            N = len(prod_states)
            self.action_list = list(mdp.action_list)
            self.states = list(prod_states)
            for act in self.action_list:
                self.prob[act] = np.zeros((N, N), self.prob_dtype)
                for prod_state in range(N):
                    (_s,_q) = self.states[prod_state]
                    self.L[(_s, _q)] = mdp.L[_s]
                    for _j in range(N):
                        (next_s,next_q) = self.states[_j]
                        if next_q == dra.get_transition(mdp.L[next_s], _q):
                            _p = mdp.P(_s, act, next_s)
                            self.prob[act][prod_state, _j] =  _p
            mdp_acc = []
            for (J,K) in dra.acc:
                Jmdp = set([])
                Kmdp = set([])
                for prod_state in prod_states:
                    if prod_state[1] in J:
                        Jmdp.add(prod_state)
                    if prod_state[1] in K:
                        Kmdp.add(prod_state)
                mdp_acc.append((Jmdp, Kmdp))
            self.acc = mdp_acc

    def setSinks(self, sink_list):
        """
        @brief Finds augmented states that contain @c sink_frag and updates the row corresponding to their transition
               probabilities so that all transitions take a self loop with probability 1.

        Used for product MDPs (see @ref productMDP), to identify augmented states that include @c sink_frag. @c
        sink_frag is the DRA/DFA component of an augmented state that is terminal.
        """
        if type(self.mdp) is MultiAgentMDP:
            if any(sink_list):
                for sink_frag in sink_list:
                    for state in self.states:
                        if sink_frag in state:
                            # Set the transition probability of this state to always self loop.
                            self.sink_list.append(state)
                            s_idx = self.states.index(state)
                            for act in self.executable_action_dict[self.controllable_agent_idx]:
                                self.prob[act][s_idx, :] = np.zeros((1, self.num_states), self.prob_dtype)
                                self.prob[act][s_idx, s_idx] = 1.0
            else:
                self.sink_list = []
        else:
            super(self.__class__, self).setSinks(sink_list)

    def configureReward(self, winning_reward, bonus_reward_at_state=dict([])):
        """
        @breif Configure the reward dictionary for the MDPxDRA.

        A MDPxDRA emits a binary reward upon taking a 'winning action' at a 'winning state'. Upon taking this action,
        the MDPxDRA state transitions to a winning sink state. Once the specification of the DRA is completed, the
        winning state/action is available. Winning states are listed in ProductMDPxDRA.acc. By convention, if a state
        included in ProductMDPxDRA.acc but is labeled with the ProductMDPxDRA.losing_sink label, it is not given the
        winning action.

        @param winning_reward A dictionary specifiying the reward value for the winning action at the 'winning state'. Keys
        should include the entirety of ProductMDPxDRA.action_list.

        @note It is assumed that all actions are available at all states. This method generates a 'no_reward' dictionary
        from the keys in 'winning_reward' which is assigned to all states not in `acc`.

        @note This method assigns the same dictionary _reference_ to each winning state, so if you change one, you change
        them all.
        """
        no_reward = {act: 0.0 for act in self.action_list}
        # Go through each state and if it is a winning state, assign it's reward
        # to be the positive reward dictionary. I have to remove the state
        # ('5', 'q3') because there are conflicting actions due to the label of '4'
        # being 'red'.
        reward_dict = {}
        for state in self.states:
            if state in self.acc[0][0] and not self.L[state]==self.losing_sink_label:
                # Winning state
                reward_dict[state] = winning_reward
            else:
                # No reward when leaving current state.
                reward_dict[state] = no_reward
            if bonus_reward_at_state and 'q0' in state:
                env_state = state[self.cell_state_slicer][0]
                for robot_act, env_act in zip(reward_dict[state].keys(), bonus_reward_at_state[env_state].keys()):
                    reward_dict[state][robot_act] += bonus_reward_at_state[env_state][env_act]
        self.reward = reward_dict

    def makeUniformPolicy(self):
        # I'm so sorry for this hack, in too much of a rush to figure out multiple inheritance. <3 Nolan
        if type(self.mdp) is MultiAgentMDP:
            uninform_prob = 1.0 / len(self.executable_action_dict[self.controllable_agent_idx])
            uniform_policy_dist = {act: uninform_prob for act in
                                   self.executable_action_dict[self.controllable_agent_idx]}
            self.policy = {state: uniform_policy_dist.copy() for state in
                           self.states}
        else:
            super(self.__class__, self).makeUniformPolicy()

    def T(self, state, action):
        """
        Transition model.  From a state and an action, return a row in the matrix for next-state probability.
        """
        # I'm so sorry for this hack, in too much of a rush to figure out multiple inheritance. <3 Nolan
        if type(self.mdp) is MultiAgentMDP:
            est_env_policy = self.infer_env_mdp.policy[state[self.cell_state_slicer][0]]
            trans_prob = self.getMultiAgentTransDistribution(state, action, est_env_policy)
        else:
            trans_prob = super(self.__class__, self).T(state, action)
        return trans_prob

    def step(self):
        """
        @brief Given the current state and the policy, creates the joint distribution of
            next-states and actions. Then samples from that distribution.

        Returns the current state number as an integer.
        """
        if type(self.mdp) is MultiAgentMDP:
            true_env_policy = self.env_policy[self.uncontrollable_agent_indices[0]] \
                                             [self.current_state[self.cell_state_slicer][0]]
            # Creates a transition probability vector of the same dimesion as a row in the
            # transition probability matrix.
            this_trans_prob = np.zeros(self.num_states, self.prob_dtype)
            robot_policy = self.policy[self.current_state]
            for act in robot_policy.keys():
                joint_trans_prob = self.getMultiAgentTransDistribution(self.current_state, act, true_env_policy)
                this_trans_prob += robot_policy[act] * joint_trans_prob
            # Renormalize distribution - need to deal with this in a better way.
            this_trans_prob /= this_trans_prob.sum()
            # Sample a new state given joint distribution of states and actions.
            try:
                next_index= np.random.choice(self.num_states, 1, p=this_trans_prob)[0]
            except ValueError:
                import pdb; pdb.set_trace()
            self.current_state = self.states[next_index]
            observable_index = self.observable_states.index(self.current_state[self.cell_state_slicer])
            return self.current_state[self.cell_state_slicer], observable_index

        else:
            return super(self.__class__, self).step()

    def getMultiAgentTransDistribution(self, state, robot_action, env_policy):
        """
        @param env_policy A reference to the true or estimated policy to use for calculating the transition probability.
        """
        state_idx = self.states.index(state)
        # Creates a transition probability vector of the same dimesion as a row in the
        # transition probability matrix.
        intermediate_trans_prob = np.zeros(self.num_states, self.prob_dtype)
        for act in env_policy.keys():
            intermediate_trans_prob += env_policy[act] * self.prob[act][state_idx, :]
        # Renormalize distribution (sometimes sum of elements is a wee bit more or less than one) - need to deal with
        # this in a better way.
        intermediate_trans_prob /= intermediate_trans_prob.sum()
        _, next_state_indices, env_trans_probs = sparse.find(intermediate_trans_prob)

        final_trans_prob = np.zeros(self.num_states, self.prob_dtype)
        for next_state_idx, env_trans_prob in zip(next_state_indices, env_trans_probs):
            final_trans_prob += np.multiply(env_trans_prob, self.prob[robot_action][next_state_idx, :])
        # Renormalize, again.
        final_trans_prob /= final_trans_prob.sum()
        return final_trans_prob


