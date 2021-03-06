#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Load dataset for the multitask CTC model (CSJ corpus).
   In addition, frame stacking and skipping are used.
   You can use the multi-GPU version.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join
import pickle
import numpy as np

from experiments.utils.data.dataset_loader.each_load.multitask_ctc_each_load import DatasetBase


class Dataset(DatasetBase):

    def __init__(self, data_type, train_data_size, label_type_main,
                 label_type_sub, batch_size, num_stack=None, num_skip=None,
                 sort_utt=True, sorta_grad=False,
                 progressbar=False, num_gpu=1, is_gpu=True,
                 divide_by_space=False):
        """A class for loading dataset.
        Args:
            data_type: string, train or dev or eval1 or eval2 or eval3
            train_data_size: string, default or large
            label_type_main: string, character or kanji
            label_type_sub: string, character or phone
            batch_size: int, the size of mini-batch
            num_stack: int, the number of frames to stack
            num_skip: int, the number of frames to skip
            sort_utt: if True, sort all utterances by the number of frames and
                utteraces in each mini-batch are shuffled
            sorta_grad: if True, sorting utteraces are conducted only in the
                first epoch (not shuffled in each mini-batch). After the first
                epoch, training will revert back to a random order. If sort_utt
                is also True, it will be False.
            progressbar: if True, visualize progressbar
            num_gpu: int, if more than 1, divide batch_size by num_gpu
            is_gpu: bool, if True, use dataset in the GPU server. This is
                useful when data size is very large and you cannot load all
                dataset at once. Then, you should put dataset on the GPU server
                you will use to reduce data-communication time between servers.
            divide_by_space: if True, each subword will be diveded by space
        """
        if data_type not in ['train', 'dev', 'eval1', 'eval2', 'eval3']:
            raise ValueError(
                'data_type is "train" or "dev", "eval1", "eval2", "eval3".')

        self.data_type = data_type
        self.train_data_size = train_data_size
        self.label_type_main = label_type_main
        self.label_type_sub = label_type_sub
        self.batch_size = batch_size * num_gpu
        self.num_stack = num_stack
        self.num_skip = num_skip
        self.sort_utt = sort_utt if not sorta_grad else False
        self.sorta_grad = sorta_grad
        self.progressbar = progressbar
        self.num_gpu = num_gpu
        self.input_size = 123

        if is_gpu:
            # GPU server
            input_path = join('/data/inaguma/csj/inputs',
                              train_data_size, data_type)
            if divide_by_space:
                label_main_path = join(
                    '/data/inaguma/csj/labels/ctc_divide',
                    train_data_size, label_type_main, data_type)
                label_sub_path = join(
                    '/data/inaguma/csj/labels/ctc_divide',
                    train_data_size, label_type_sub, data_type)
            else:
                label_main_path = join(
                    '/data/inaguma/csj/labels/ctc',
                    train_data_size, label_type_main, data_type)
                label_sub_path = join(
                    '/data/inaguma/csj/labels/ctc',
                    train_data_size, label_type_sub, data_type)
        else:
            # CPU
            input_path = join('/n/sd8/inaguma/corpus/csj/dataset/inputs',
                              train_data_size, data_type)
            if divide_by_space:
                label_main_path = join(
                    '/n/sd8/inaguma/corpus/csj/dataset/labels/ctc_divide',
                    train_data_size, label_type_main, data_type)
                label_sub_path = join(
                    '/n/sd8/inaguma/corpus/csj/dataset/labels/ctc_divide',
                    train_data_size, label_type_sub, data_type)
            else:
                label_main_path = join(
                    '/n/sd8/inaguma/corpus/csj/dataset/labels/ctc',
                    train_data_size, label_type_main, data_type)
                label_sub_path = join(
                    '/n/sd8/inaguma/corpus/csj/dataset/labels/ctc',
                    train_data_size, label_type_sub, data_type)

        # Load the frame number dictionary
        with open(join(input_path, 'frame_num.pickle'), 'rb') as f:
            self.frame_num_dict = pickle.load(f)

        # Sort paths to input & label by frame num
        frame_num_tuple_sorted = sorted(self.frame_num_dict.items(),
                                        key=lambda x: x[1])
        input_paths, label_main_paths, label_sub_paths = [], [], []
        for input_name, frame_num in frame_num_tuple_sorted:
            speaker_name = input_name.split('_')[0]
            input_paths.append(
                join(input_path, speaker_name, input_name + '.npy'))
            label_main_paths.append(
                join(label_main_path, speaker_name, input_name + '.npy'))
            label_sub_paths.append(
                join(label_sub_path, speaker_name, input_name + '.npy'))
        self.input_paths = np.array(input_paths)
        self.label_main_paths = np.array(label_main_paths)
        self.label_sub_paths = np.array(label_sub_paths)
        self.data_num = len(self.input_paths)

        if (self.num_stack is not None) and (self.num_skip is not None):
            self.input_size = self.input_size * num_stack
        # NOTE: Not load dataset yet

        self.rest = set(range(0, self.data_num, 1))

        if data_type in ['eval1', 'eval2', 'eval3'] and label_type_sub != 'phone':
            self.is_test = True
        else:
            self.is_test = False
