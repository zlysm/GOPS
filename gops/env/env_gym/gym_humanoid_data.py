#  Copyright (c). All Rights Reserved.
#  General Optimal control Problem Solver (GOPS)
#  Intelligent Driving Lab(iDLab), Tsinghua University
#
#  Creator: iDLab
#  Description: Mujoco Humanoid Environment
#  Update Date: 2021-11-22, Yuhang Zhang: create environment

import gym


def env_creator(**kwargs):
    try:
        return gym.make("Humanoid-v3")
    except:
        raise ModuleNotFoundError("Warning:  mujoco, mujoco-py and MSVC are not installed properly")


if __name__ == "__main__":
    env = env_creator()
    env.reset()
    for i in range(100):
        a = env.action_space.sample()
        env.step(a)
        env.render()