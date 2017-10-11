#!/usr/bin/env python
__author__ = 'Jie Fu, jfu2@wpi.edu'
from NFA_DFA_Module.NFA import NFA
from MDP_solvers import MDP_solvers

from scipy import stats
import numpy as np


class MDP:
    """A Markov Decision Process, defined by an initial state,
        transition model --- the probability transition matrix, np.array
        prob[a][0,1] -- the probability of going from 0 to 1 with action a.
        and reward function. We also keep track of a gamma value, for
        use by algorithms. The transition model is represented
        somewhat differently from the text.  Instead of T(s, a, s')
        being probability number for each state/action/state triplet,
        we instead have T(s, a) return a list of (p, s') pairs.  We
        also keep track of the possible states, terminal states, and
        actions for each state.  The input transitions is a
        dictionary: (state,action): list of next state and probability
        tuple.  AP: a set of atomic propositions. Each proposition is
        identified by an index between 0 -N.  L: the labeling
        function, implemented as a dictionary: state: a subset of AP."""
    def __init__(self, init=None, actlist=[], states=[], prob=dict([]),
                 acc=None, gamma=.9, AP=set([]), L=dict([]), reward=dict([])):
        self.init=init
        self.actlist=actlist
        self.states=states
        self.acc=acc
        self.gamma=gamma
        self.reward=reward
        self.prob=prob
        self.AP=AP
        self.L=L

    def R(self, state):
        "Return a numeric reward for this state."
        return self.reward[state]

    def T(self, state, action):
        """
        Transition model.  From a state and an action, return a row in the
        matrix for next-state probability.
        """
        i=self.states.index(state)
        return self.prob[action][i, :]

    def P(self, state, action, next_state):
        """
        Derived from the transition model. For a state, an action and the
        next_state, return the probability of this transition.
        """
        i=self.states.index(state)
        j=self.states.index(next_state)
        return self.prob[action][i, j]

    def actions(self, state):
        N=len(self.states)
        S=set([])
        for _a in self.actlist:
            if not np.array_equal(self.T(state,_a), np.zeros(N)):
                S.add(_a)
        return S

    def labeling(self, s, A):
        self.L[s]=A

    def sample(self, state, action, num=1):
        """
        Sample the next state according to the current state, the action, and
        the transition probability.
        """
        if action not in self.actions(state):
            return None # Todo: considering adding the sink state
        N=len(self.states)
        i=self.states.index(state)
        # Note that only one element is chosen from the array, which is the
        # output by random.choice
        next_index= np.random.choice(N, num, p=self.prob[action][i,:])[0]
        return self.states[next_index]

    @staticmethod
    def productMDP(mdp, dra):
        pmdp=MDP()
        init=(mdp.init, dra.get_transition(mdp.L[mdp.init], dra.initial_state))
        states=[]
        for _s in mdp.states:
            for _q in dra.states:
                states.append((_s, _q))
        N=len(states)
        pmdp.init=init
        pmdp.actlist=list(mdp.actlist)
        pmdp.states=list(states)
        for _a in pmdp.actlist:
            pmdp.prob[_a]=np.zeros((N, N))
            for i in range(N):
                (_s,_q)=pmdp.states[i]
                pmdp.L[(_s,_q)]=mdp.L[_s]
                for _j in range(N):
                    (next_s,next_q)=pmdp.states[_j]
                    if next_q == dra.get_transition(mdp.L[next_s], _q):
                        _p=mdp.P(_s,_a,next_s)
                        pmdp.prob[_a][i, _j]= _p
        mdp_acc=[]
        for (J,K) in dra.acc:
            Jmdp=set([])
            Kmdp=set([])
            for _s in states:
                if _s[1] in J:
                    Jmdp.add(_s)
                if _s[1] in K:
                    Kmdp.add(_s)
            mdp_acc.append((Jmdp, Kmdp))
        pmdp.acc=mdp_acc
        return pmdp


    @staticmethod
    def get_NFA(mdp):
        """
        This function obtains the graph structure, which is essentially an
        non-deterministic finite state automaton from the original mdp.
        """
        nfa=NFA()
        nfa.initial_state=mdp.init
        nfa.states=mdp.states
        nfa.alphabet=mdp.actlist
        for _a in mdp.actlist:
            for s in mdp.states:
                next_state_list=[]
                for next_s in mdp.states:
                    if mdp.prob[_a][mdp.states.index(s), mdp.states.index(next_s)] != 0:
                        next_state_list.append(next_s)
                nfa.add_transition(_a, s, next_state_list)
        nfa.final_states=mdp.terminals
        return nfa

    @staticmethod
    def sub_MDP(mdp, H):
        """
        For a given MDP and a subset of the states H, construct a sub-mdp
        that only includes the set of states in H, and a sink states for
        all transitions to and from a state outside H.
        """
        if H == set(mdp.states):
            # If H is the set of states in mdp, return mdp as it is.
            return mdp
        submdp=MDP()
        submdp.states=list(H)
        submdp.states.append(-1) # -1 is the sink state.
        N=len(submdp.states)
        submdp.actlist=list(mdp.actlist)
        submdp.prob={_a:np.zeros((N, N)) for _a in submdp.actlist}
        temp=np.zeros(len(mdp.states))
        for k in set(mdp.states) - H:
            temp[mdp.states.index(k)]=1
        for _a in submdp.actlist:
            for s in H: # except the last sink state.
                i=submdp.states.index(s)
                for next_s in H:
                    j=submdp.states.index(next_s)
                    submdp.prob[_a][i, j] = mdp.P(s, _a, next_s)
                submdp.prob[_a][i, -1]= np.inner(mdp.T(s, _a), temp)
            submdp.prob[_a][submdp.states.index(-1), submdp.states.index(-1)]=1
        acc=[]
        for (J,K) in mdp.acc:
            Jsub = set(H).intersection(J)
            Ksub = set(H).intersection(K)
            acc.append((Jsub,Ksub))
        acc.append(({}, {-1}))
        submdp.acc = acc
        return submdp


    @staticmethod
    def read_from_file_MDP(fname):
        """
        This function takes the input file and construct an MDP based on thei
        transition relations. The first line of the file is the list of states.
        The second line of the file is the list of actions.
        Starting from the second line, we have
        state, action, next_state, probability
        """
        f=open(fname, 'r')
        array = []
        for line in f:
            array.append( line.strip('\n') )
        f.close()
        mdp=MDP()
        state_str=array[0].split(",")
        mdp.states=[int(i) for i in state_str]
        act_str=array[1].split(",")
        mdp.actlist=act_str
        mdp.prob=dict([])
        N=len(mdp.states)
        for _a in mdp.actlist:
            mdp.prob[_a]=np.zeros((N, N))
        for line in array[2: len(array)]:
            trans_str=line.split(",")
            state=int(trans_str[0])
            act=trans_str[1]
            next_state=int(trans_str[2])
            p=float(trans_str[3])
            mdp.prob[act][mdp.states.index(state), mdp.states.index(next_state)]=p
        return mdp

    def solve(self, method='valueIteration', **kwargs):
        """
        @brief Solves a given MDP. Defaults to the Value Iteration method.

        @param an instance of @ref MDP.
        @param a string matching a method name in @ref MDP_solvers.py.
        """
        MDP_solvers(self, method=method).solve(**kwargs)
