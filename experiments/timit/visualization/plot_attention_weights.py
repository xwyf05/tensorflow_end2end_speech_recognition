#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Plot attention weights (TIMIT corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import sys
import tensorflow as tf
import yaml

sys.path.append('../../../')
from experiments.timit.data.load_dataset_attention import Dataset
from experiments.timit.visualization.core.plot.attention import attention_test
from models.attention import blstm_attention_seq2seq


def do_plot(network, params, epoch=None):
    """Plot attention weights.
    Args:
        network: model to restore
        params: A dictionary of parameters
        epoch: int, the epoch to restore
    """
    # Load dataset
    test_data = Dataset(
        data_type='test', label_type=params['label_type'], batch_size=1,
        eos_index=params['eos_index'], sort_utt=False, progressbar=True)

    # Define placeholders
    network.create_placeholders()

    # Add to the graph each operation (including model definition)
    _, _, decoder_outputs_train, decoder_outputs_infer = network.compute_loss(
        network.inputs_pl_list[0],
        network.labels_pl_list[0],
        network.inputs_seq_len_pl_list[0],
        network.labels_seq_len_pl_list[0],
        network.keep_prob_input_pl_list[0],
        network.keep_prob_hidden_pl_list[0],
        network.keep_prob_output_pl_list[0])
    _, decode_op_infer = network.decoder(
        decoder_outputs_train,
        decoder_outputs_infer)
    attention_weights_op = decoder_outputs_infer.attention_weights

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
        attention_test(session=sess,
                       decode_op=decode_op_infer,
                       attention_weights_op=attention_weights_op,
                       network=network,
                       dataset=test_data,
                       label_type=params['label_type'],
                       save_path=None,
                       show=True)


def main(model_path, epoch):

    # Load config file
    with open(os.path.join(model_path, 'config.yml'), "r") as f:
        config = yaml.load(f)
        params = config['param']

    params['sos_index'] = 0
    params['eos_index'] = 1
    if params['label_type'] == 'phone61':
        params['num_classes'] = 63
    elif params['label_type'] == 'phone48':
        params['num_classes'] = 50
    elif params['label_type'] == 'phone39':
        params['num_classes'] = 41
    elif params['label_type'] == 'character':
        params['num_classes'] = 30
    elif params['label_type'] == 'character_capital_divide':
        params['num_classes'] = 74

    # Model setting
    # AttentionModel = load(model_type=params['model'])
    network = blstm_attention_seq2seq.BLSTMAttetion(
        input_size=params['input_size'],
        encoder_num_unit=params['encoder_num_unit'],
        encoder_num_layer=params['encoder_num_layer'],
        attention_dim=params['attention_dim'],
        attention_type=params['attention_type'],
        decoder_num_unit=params['decoder_num_unit'],
        decoder_num_layer=params['decoder_num_layer'],
        embedding_dim=params['embedding_dim'],
        num_classes=params['num_classes'],
        sos_index=params['sos_index'],
        eos_index=params['eos_index'],
        max_decode_length=params['max_decode_length'],
        attention_smoothing=params['attention_smoothing'],
        attention_weights_tempareture=params['attention_weights_tempareture'],
        logits_tempareture=params['logits_tempareture'],
        parameter_init=params['weight_init'],
        clip_grad=params['clip_grad'],
        clip_activation_encoder=params['clip_activation_encoder'],
        clip_activation_decoder=params['clip_activation_decoder'],
        dropout_ratio_input=params['dropout_input'],
        dropout_ratio_hidden=params['dropout_hidden'],
        dropout_ratio_output=params['dropout_output'],
        weight_decay=params['weight_decay'])

    network.model_dir = model_path
    print(network.model_dir)
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
             "Usase: python plot_attention_weights.py path_to_saved_model (epoch)"))
    main(model_path=model_path, epoch=epoch)
