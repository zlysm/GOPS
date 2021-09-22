#  Copyright (c). All Rights Reserved.
#  General Optimal control Problem Solver (GOPS)
#  Intelligent Driving Lab(iDLab), Tsinghua University
#
#  Creator: Sun Hao
#  Description: Discrete version of Cartpole Enviroment
#
#  Update Date: 2020-11-10, Hao SUN: renew env para
#  Update Date: 2021-05-21, Shengbo Li: Reformualte code formats

import argparse
import copy
import datetime
import json
import os

import numpy as np

from modules.create_pkg.create_alg import create_alg
from modules.create_pkg.create_buffer import create_buffer
from modules.create_pkg.create_env import create_env
from modules.create_pkg.create_evaluator import create_evaluator
from modules.create_pkg.create_sampler import create_sampler
from modules.create_pkg.create_trainer import create_trainer
from modules.utils.init_args import init_args
from modules.utils.plot import plot_all
from modules.utils.utils import change_type
from modules.utils.tensorboard_tools import start_tensorboard



if __name__ == "__main__":
    # Parameters Setup
    parser = argparse.ArgumentParser()

    ################################################
    # Key Parameters for users
    parser.add_argument('--env_id', type=str, default='gym_carracing2')
    parser.add_argument('--algorithm', type=str, default='DDPG')
    parser.add_argument('--enable_cuda', default=True, help='Disable CUDA')
    ################################################
    # 1. Parameters for environment
    parser.add_argument('--obsv_dim', type=int, default=None, help='dim(State)')
    parser.add_argument('--action_dim', type=int, default=None, help='dim(Action)')
    parser.add_argument('--action_high_limit', type=list, default=None)
    parser.add_argument('--action_low_limit', type=list, default=None)
    parser.add_argument('--action_type', type=str, default='continu', help='Options: continu/discret')
    parser.add_argument('--is_render', type=bool, default=True, help='Draw environment animation')

    ################################################
    # 2.1 Parameters of value approximate function
    parser.add_argument('--value_func_name', type=str, default='ActionValue',
                        help='Options: StateValue/ActionValue/ActionValueDis')
    parser.add_argument('--value_func_type', type=str, default='CNN',
                        help='Options: MLP/CNN/RNN/POLY/GAUSS')
    value_func_type = parser.parse_args().value_func_type
    # 2.1.1 MLP, CNN, RNN
    if value_func_type == 'MLP':  # Hidden Layer Options: relu/gelu/elu/sigmoid/tanh;  Output Layer: linear
        parser.add_argument('--value_hidden_sizes', type=list, default=[256, 256, 128])
        parser.add_argument('--value_hidden_activation', type=str, default='relu')
        parser.add_argument('--value_output_activation', type=str, default='linear')
    # 2.1.2 Gauss Radical Func
    elif value_func_type == 'GAUSS':
        parser.add_argument('--value_num_kernel', type=int, default=30)

    elif value_func_type == 'CNN':  # Hidden Layer Options: relu/gelu/elu/sigmoid/tanh;  Output Layer: linear
        parser.add_argument('--value_hidden_activation', type=str, default='relu')
        parser.add_argument('--value_output_activation', type=str, default='linear')
        parser.add_argument('--value_conv_type', type=str, default='type_2')

    # 2.2 Parameters of policy approximate function
    parser.add_argument('--policy_func_name', type=str, default='DetermPolicy',
                        help='Options: None/DetermPolicy/StochaPolicy')
    parser.add_argument('--policy_func_type', type=str, default='CNN',
                        help='Options: MLP/CNN/RNN/POLY/GAUSS')
    policy_func_type = parser.parse_args().policy_func_type
    ### 2.2.1 MLP, CNN, RNN
    if policy_func_type == 'MLP':  # Hidden Layer Options: relu/gelu/elu/sigmoid/tanh: Output Layer: tanh
        parser.add_argument('--policy_hidden_sizes', type=list, default=[256, 256])
        parser.add_argument('--policy_hidden_activation', type=str, default='relu', help='')
        parser.add_argument('--policy_output_activation', type=str, default='tanh', help='')
    # 2.2.2 Polynominal
    elif policy_func_type == 'POLY':
        parser.add_argument('--policy_poly_degree', type=list, default=2)
    # 2.2.3 Gauss Radical Func
    elif policy_func_type == 'GAUSS':
        parser.add_argument('--policy_num_kernel', type=int, default=35)
    elif policy_func_type == 'CNN':  # Hidden Layer Options: relu/gelu/elu/sigmoid/tanh: Output Layer: tanh
        parser.add_argument('--policy_hidden_activation', type=str, default='relu', help='')
        parser.add_argument('--policy_output_activation', type=str, default='linear', help='')
        parser.add_argument('--policy_conv_type', type=str, default='type_2')
    ################################################
    # 3. Parameters for RL algorithm
    parser.add_argument('--gamma', type=float, default=0.98)
    parser.add_argument('--tau', type=float, default=0.005, help='')
    parser.add_argument('--value_learning_rate', type=float, default=1e-3, help='')
    parser.add_argument('--policy_learning_rate', type=float, default=1e-4, help='')
    parser.add_argument('--delay_update', type=int, default=1, help='')
    parser.add_argument('--reward_scale', type=float, default=1, help='Reward = reward_scale * environment.Reward')

    ################################################
    # 4. Parameters for trainer
    parser.add_argument('--trainer', type=str, default='off_serial_trainer',
                        help='on_serial_trainer'
                             'on_sync_trainer'
                             'off_serial_trainer'
                             'off_async_trainer')
    parser.add_argument('--max_iteration', type=int, default=500000,
                        help='Maximum iteration number')
    trainer_type = parser.parse_args().trainer
    parser.add_argument('--ini_network_dir', type=str, default=None)
    # 4.1. Parameters for on_serial_trainer
    if trainer_type == 'on_serial_trainer':
        pass
    # 4.2. Parameters for on_sync_trainer
    elif trainer_type == 'on_sync_trainer':
        pass
    # 4.3. Parameters for off_serial_trainer
    elif trainer_type == 'off_serial_trainer':
        parser.add_argument('--buffer_name', type=str, default='replay_buffer')
        parser.add_argument('--buffer_warm_size', type=int, default=512,
                            help='Size of collected samples before training')
        parser.add_argument('--buffer_max_size', type=int, default=30000,
                            help='Max size of buffer')
        parser.add_argument('--replay_batch_size', type=int, default=128,
                            help='Batch size of replay samples from buffer')
        parser.add_argument('--sampler_sync_interval', type=int, default=1,
                            help='Period of sync central policy of each sampler')
    # 4.4. Parameters for off_async_trainer
    elif trainer_type == 'off_async_trainer':
        pass
    else:
        raise ValueError

    ################################################
    # 5. Parameters for sampler
    parser.add_argument('--sampler_name', type=str, default='off_sampler')
    parser.add_argument('--sample_batch_size', type=int, default=10,
                        help='Batch size of sampler for buffer store')
    parser.add_argument('--noise_params', type=dict,
                        default={'mean': np.array([0], dtype=np.float32),
                                 'std': np.array([0.2], dtype=np.float32)},
                        help='Add noise to actions for exploration')

    ################################################
    # 7. Parameters for evaluator
    parser.add_argument('--evaluator_name', type=str, default='evaluator')
    parser.add_argument('--num_eval_episode', type=int, default=5)
    parser.add_argument('--eval_interval', type=int, default=100)
    parser.add_argument('--eval_save', type=bool, default=False)

    ################################################
    # 8. Data savings
    parser.add_argument('--save_folder', type=str, default=None)
    parser.add_argument('--apprfunc_save_interval', type=int, default=500,
                        help='Save value/policy every N updates')
    parser.add_argument('--log_save_interval', type=int, default=100,
                        help='Save gradient time/critic loss/actor loss/average value every N updates')

    # Get parameter dictionary
    args = vars(parser.parse_args())
    env = create_env(**args)
    args = init_args(env, **args)

    start_tensorboard(args['save_folder'])
    # Step 1: create algorithm and approximate function
    alg = create_alg(**args)
    # Step 2: create sampler in trainer
    sampler = create_sampler(**args)
    # Step 3: create buffer in trainer
    buffer = create_buffer(**args)
    # Step 4: create evaluator in trainer
    evaluator = create_evaluator(**args)
    # Step 5: create trainer
    if trainer_type == 'off_serial_trainer' or trainer_type == 'off_async_trainer':
        trainer = create_trainer(alg, sampler, buffer, evaluator, **args)
    elif trainer_type == 'on_serial_trainer' or trainer_type == 'on_sync_trainer':
        trainer = create_trainer(alg, sampler, None, evaluator, **args)

    # Start training ... ...
    trainer.train()
    print('Training is finished!')

    # Plot and save training figures
    plot_all(args['save_folder'])
