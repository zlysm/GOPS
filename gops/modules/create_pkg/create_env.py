#   Copyright (c) Intelligent Driving Lab(iDLab), Tsinghua University. All Rights Reserved.
#
#  Creator: Yuhang ZHANG
#  Description: Create environments
"""
resources:
env = create_env('gym_pendulum_diff')

1: Copy your environment file into env folder, and environment file is named as
    gym_***.py
    gym_***_diff.py
    pyth_***.py
    simu_***.py
2: The environment class is named in camel-case style after file name
    ex: GymMountaincarContiDiff in gym_mountaincar_conti_diff.py
    ex: GymCartpoleConti in gym_cartpole_conti.py
3: Define an instantiating function env_creator() which return a instance of the environment
Note: create_env() requires that either 2 or 3 is satisfied.
"""

#  Update Date: 2020-11-10, Yuhang ZHANG:


def create_env(env_name):
    # print(os.path.join(module_path, env_name))
    #
    try:
        file = __import__(env_name)
    except NotImplementedError:
        raise NotImplementedError('This environment does not exist')

    env_name_camel = formatter(env_name)

    if hasattr(file, "env_creator"):
        y = getattr(file, "env_creator")
        env = y()
    elif hasattr(file, env_name_camel):
        y = getattr(file, env_name_camel)
        env = y()
    else:
        raise NotImplementedError("This environment is not properly defined")
    print("Create environment successfully!")
    return env

def formatter(src: str, firstUpper: bool = True):
    arr = src.split('_')
    res = ''
    for i in arr:
        res = res + i[0].upper() + i[1:]

    if not firstUpper:
        res = res[0].lower() + res[1:]
    return res