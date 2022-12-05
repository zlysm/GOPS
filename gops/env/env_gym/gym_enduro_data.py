#  Copyright (c). All Rights Reserved.
#  General Optimal control Problem Solver (GOPS)
#  Intelligent Driving Lab(iDLab), Tsinghua University
#
#  Creator: iDLab
#  Description: Enduro Environment
#  Update Date: 2021-05-55, Yuhang Zhang: create environment

import gym


def env_creator(**kwargs):
    try:
        return gym.make("Enduro-v0")
    except:
        raise ModuleNotFoundError("Warning: Atari_py is not installed")