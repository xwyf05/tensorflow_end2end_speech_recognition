#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Plot the trained multi-task CTC posteriors (TIMIT corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import sys
import tensorflow as tf
import yaml

sys.path.append('../../../')
from experiments.timit.data.load_dataset_multitask_ctc import Dataset
from experiments.timit.visualization.core.plot.ctc import posterior_test_multitask
from models.ctc.load_model import load


def do_plot(network, params, epoch=None):
    """Plot the multi-task CTC posteriors.
    Args:
        network: model to restore
        params: A dictionary of parameters
        epoch: int, the epoch to restore
    """
    # Load dataset
    test_data = Dataset(
        data_type='test', label_type_main=params['label_type_main'],
        label_type_sub=params['label_type_sub'],
        batch_size=1, splice=params['splice'],
        num_stack=params['num_stack'], num_skip=params['num_skip'],
        sort_utt=False, progressbar=True)

    # Define placeholders
    network.create_placeholders()

    # Add to the graph each operation (including model definition)
    _, logits_main, logits_sub = network.compute_loss(
        network.inputs_pl_list[0],
        network.labels_pl_list[0],
        network.labels_sub_pl_list[0],
        network.inputs_seq_len_pl_list[0],
        network.keep_prob_input_pl_list[0],
        network.keep_prob_hidden_pl_list[0],
        network.keep_prob_output_pl_list[0])
    posteriors_op_main, posteriors_op_sub = network.posteriors(
        logits_main, logits_sub)

    # Create a saver for writing training checkpoints
    saver = tf.train.Saver()

    with tf.Session() as sess:
        ckpt = tf.train.get_checkpoint_state(network.model_dir)

        # If check point exists
        if ckpt:
            # Use last saved model
            model_path = ckpt.model_checkpoint_path
            if epoch is not None:
                model_path = model_path.split('/')[:-1]
                model_path = '/'.join(model_path) + '/model.ckpt-' + str(epoch)
            saver.restore(sess, model_path)
            print("Model restored: " + model_path)
        else:
            raise ValueError('There are not any checkpoints.')

        # Visualize
        posterior_test_multitask(session=sess,
                                 posteriors_op_main=posteriors_op_main,
                                 posteriors_op_sub=posteriors_op_sub,
                                 network=network,
                                 dataset=test_data,
                                 label_type_main=params['label_type_main'],
                                 label_type_sub=params['label_type_sub'],
                                 save_path=network.model_dir,
                                 show=False)


def main(model_path, epoch):

    # Load config file
    with open(os.path.join(model_path, 'config.yml'), "r") as f:
        config = yaml.load(f)
        params = config['param']

    # Except for a blank label
    if params['label_type_main'] == 'character':
        params['num_classes_main'] = 28
    elif params['label_type_main'] == 'character_capital_divide':
        params['num_classes_main'] = 72

    if params['label_type_sub'] == 'phone61':
        params['num_classes_sub'] = 61
    elif params['label_type_sub'] == 'phone48':
        params['num_classes_sub'] = 48
    elif params['label_type_sub'] == 'phone39':
        params['num_classes_sub'] = 39

    # Model setting
    model = load(model_type=params['model'])
    network = model(
        input_size=params['input_size'] * params['num_stack'],
        num_unit=params['num_unit'],
        num_layer_main=params['num_layer_main'],
        num_layer_sub=params['num_layer_sub'],
        num_classes_main=params['num_classes_main'],
        num_classes_sub=params['num_classes_sub'],
        main_task_weight=params['main_task_weight'],
        clip_grad=params['clip_grad'],
        clip_activation=params['clip_activation'],
        dropout_ratio_input=params['dropout_input'],
        dropout_ratio_hidden=params['dropout_hidden'],
        dropout_ratio_output=params['dropout_output'],
        num_proj=params['num_proj'],
        weight_decay=params['weight_decay'])

    network.model_dir = model_path
    do_plot(network=network, params=params, epoch=epoch)


if __name__ == '__main__':

    args = sys.argv
    if len(args) == 2:
        model_path = args[1]
        epoch = None
    elif len(args) == 3:
        model_path = args[1]
        epoch = args[2]
    else:
        raise ValueError(
            ("Set a path to saved model.\n"
             "Usase: python plot_multitask_ctc_posterior.py path_to_saved_model"))
    main(model_path=model_path, epoch=epoch)
