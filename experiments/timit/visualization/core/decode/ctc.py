#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Utilities for decoding of the CTC model (TIMIT corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join
import sys

from experiments.utils.data.labels.character import num2char
from experiments.utils.data.labels.phone import num2phone
from experiments.utils.data.sparsetensor import sparsetensor2list


def decode_test(session, decode_op, network, dataset, label_type,
                save_path=None):
    """Visualize label outputs of CTC model.
    Args:
        session: session of training model
        decode_op: operation for decoding
        network: network to evaluate
        dataset: An instance of a `Dataset` class
        label_type: string, phone39 or phone48 or phone61 or character or
            character_capital_divide
        save_path: path to save decoding results
    """
    map_file_path = '../metrics/mapping_files/ctc/' + label_type + '_to_num.txt'

    if save_path is not None:
        sys.stdout = open(join(network.model_dir, 'decode.txt'), 'w')

    # Batch size is expected to be 1
    for data, next_epoch_flag in dataset(batch_size=1):
        # Create feed dictionary for next mini batch
        inputs, labels_true, inputs_seq_len, input_names = data

        feed_dict = {
            network.inputs_pl_list[0]: inputs,
            network.inputs_seq_len_pl_list[0]: inputs_seq_len,
            network.keep_prob_input_pl_list[0]: 1.0,
            network.keep_prob_hidden_pl_list[0]: 1.0,
            network.keep_prob_output_pl_list[0]: 1.0
        }

        # Visualize
        labels_pred_st = session.run(decode_op, feed_dict=feed_dict)
        try:
            labels_pred = sparsetensor2list(labels_pred_st, batch_size=1)
        except IndexError:
            # no output
            labels_pred = ['']
        finally:
            if label_type in ['character', 'character_capital_divide']:
                print('----- wav: %s -----' % input_names[0])
                print('True: %s' % num2char(
                    labels_true[0], map_file_path))
                print('Pred: %s' % num2char(
                    labels_pred[0], map_file_path))

            else:
                print('----- wav: %s -----' % input_names[0])
                print('True: %s' % num2phone(
                    labels_true[0], map_file_path))
                print('Pred: %s' % num2phone(
                    labels_pred[0], map_file_path))

        if next_epoch_flag:
            break


def decode_test_multitask(session, decode_op_main, decode_op_sub, network,
                          dataset, label_type_main, label_type_sub,
                          save_path=None):
    """Visualize label outputs of Multi-task CTC model.
    Args:
        session: session of training model
        decode_op_main: operation for decoding in the main task
        decode_op_sub: operation for decoding in the sub task
        network: network to evaluate
        dataset: An instance of a `Dataset` class
        label_type_main: string, character or character_capital_divide
        label_type_sub: string, phone39 or phone48 or phone61
        save_path: path to save decoding results
    """
    if save_path is not None:
        sys.stdout = open(join(network.model_dir, 'decode.txt'), 'w')

    # Decode character
    print('===== ' + label_type_main + ' =====')
    map_file_path = '../metrics/mapping_files/ctc/' + label_type_main + '_to_num.txt'
    # Batch size is expected to be 1
    for data, next_epoch_flag in dataset(batch_size=1):
        # Create feed dictionary for next mini batch
        inputs, labels_true, _, inputs_seq_len, input_names = data

        feed_dict = {
            network.inputs_pl_list[0]: inputs,
            network.inputs_seq_len_pl_list[0]: inputs_seq_len,
            network.keep_prob_input_pl_list[0]: 1.0,
            network.keep_prob_hidden_pl_list[0]: 1.0,
            network.keep_prob_output_pl_list[0]: 1.0
        }

        # Visualize
        labels_pred_st = session.run(decode_op_main, feed_dict=feed_dict)
        labels_pred = sparsetensor2list(labels_pred_st, batch_size=1)

        print('----- wav: %s -----' % input_names[0])
        print('True: %s' % num2char(
            labels_true[0], map_file_path))
        print('Pred: %s' % num2char(
            labels_pred[0], map_file_path))

        if next_epoch_flag:
            break

    # Decode phone
    print('\n===== ' + label_type_sub + ' =====')
    map_file_path = '../metrics/mapping_files/ctc/' + \
        label_type_sub + '_to_num.txt'
    # Batch size is expected to be 1
    for data, next_epoch_flag in dataset(batch_size=1):
        # Create feed dictionary for next mini batch
        inputs, _, labels_true, inputs_seq_len, input_names = data

        feed_dict = {
            network.inputs_pl_list[0]: inputs,
            network.inputs_seq_len_pl_list[0]: inputs_seq_len,
            network.keep_prob_input_pl_list[0]: 1.0,
            network.keep_prob_hidden_pl_list[0]: 1.0,
            network.keep_prob_output_pl_list[0]: 1.0
        }

        # Visualize
        labels_pred_st = session.run(decode_op_sub, feed_dict=feed_dict)
        try:
            labels_pred = sparsetensor2list(labels_pred_st, batch_size=1)
        except IndexError:
            # no output
            labels_pred = ['']
        finally:
            print('----- wav: %s -----' % input_names[0])
            print('True: %s' % num2phone(
                labels_true[0], map_file_path))
            print('Pred: %s' % num2phone(
                labels_pred[0], map_file_path))

        if next_epoch_flag:
            break
