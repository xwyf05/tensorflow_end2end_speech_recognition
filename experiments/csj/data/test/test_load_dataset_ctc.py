#! /usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import re
import sys
import unittest
import tensorflow as tf

sys.path.append('../../../../')
from experiments.csj.data.load_dataset_ctc import Dataset
from experiments.utils.data.labels.character import num2char
from experiments.utils.data.labels.phone import num2phone
from experiments.utils.measure_time_func import measure_time


class TestLoadDatasetCTC(unittest.TestCase):
    def test(self):

        # label_type
        self.check_loading(label_type='kanji', num_gpu=1,
                           sort_utt=False, sorta_grad=False)
        self.check_loading(label_type='kana', num_gpu=1,
                           sort_utt=False, sorta_grad=False)
        self.check_loading(label_type='phone', num_gpu=1,
                           sort_utt=False, sorta_grad=False)

        # sort
        self.check_loading(label_type='kana', num_gpu=1,
                           sort_utt=True, sorta_grad=False)
        self.check_loading(label_type='kana', num_gpu=1,
                           sort_utt=False, sorta_grad=True)

        # multi-GPU
        self.check_loading(label_type='kana', num_gpu=2,
                           sort_utt=False, sorta_grad=False)
        self.check_loading(label_type='kana', num_gpu=7,
                           sort_utt=False, sorta_grad=False)

    @measure_time
    def check_loading(self, label_type, num_gpu, sort_utt, sorta_grad):
        print('----- label_type: ' + label_type + ', num_gpu: ' +
              str(num_gpu) + ', sort_utt: ' + str(sort_utt) + ' -----')

        batch_size = 64
        dataset = Dataset(data_type='train', train_data_size='default',
                          label_type=label_type, batch_size=batch_size,
                          num_stack=3, num_skip=3,
                          sort_utt=sort_utt, sorta_grad=sorta_grad,
                          progressbar=True, num_gpu=num_gpu)

        tf.reset_default_graph()
        with tf.Session().as_default() as sess:
            print('=> Loading mini-batch...')
            if label_type == 'kanji':
                map_file_path = '../../metrics/mapping_files/ctc/kanji2num.txt'
                map_fn = num2char
            elif label_type == 'kana':
                map_file_path = '../../metrics/mapping_files/ctc/kana2num.txt'
                map_fn = num2char
            elif label_type == 'phone':
                map_file_path = '../../metrics/mapping_files/ctc/phone2num.txt'
                map_fn = num2phone

            mini_batch = dataset.next_batch(session=sess)

            iter_per_epoch = int(dataset.data_num /
                                 (batch_size * num_gpu)) + 1
            for i in range(iter_per_epoch + 1):
                inputs, labels, inputs_seq_len, input_names = mini_batch.__next__()

                if num_gpu > 1:
                    # for inputs_gpu in inputs:
                    #     print(inputs_gpu.shape)
                    inputs = inputs[0]
                    labels = labels[0]

                if num_gpu == 1:
                    for inputs_i, labels_i in zip(inputs, labels):
                        if len(inputs_i) < len(labels_i):
                            print(len(inputs_i))
                            print(len(labels_i))
                            raise ValueError

                str_true = map_fn(labels[0], map_file_path)
                str_true = re.sub(r'_', ' ', str_true)
                print(str_true)


if __name__ == '__main__':
    unittest.main()
