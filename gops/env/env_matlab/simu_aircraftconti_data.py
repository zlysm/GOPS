#  Copyright (c). All Rights Reserved.
#  General Optimal control Problem Solver (GOPS)
#  Intelligent Driving Lab(iDLab), Tsinghua University
#
#  Creator: iDLab
#  Description: Aircraft Environment
#  Update Date: 2021-05-55, Yuhang Zhang: create environment

from gops.env.env_matlab.resources.simu_aircraft_v2.aircraft import GymEnv
from gops.env.env_matlab.resources.simu_aircraft_v2.aircraft._env import EnvSpec

from gym import spaces
import gym
from gym.utils import seeding
import numpy as np

def env_creator(**kwargs):
    spec = EnvSpec(
        id="SimuAircraftConti-v0",
        max_episode_steps=200
    )
    return GymEnv(spec)

