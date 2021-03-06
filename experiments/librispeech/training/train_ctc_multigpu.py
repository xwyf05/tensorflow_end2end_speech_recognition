#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Train the CTC model with multiple GPUs (Librispeech corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, isfile
import sys
import time
import tensorflow as tf
from setproctitle import setproctitle
import yaml
import shutil

sys.path.append('../../../')
from experiments.librispeech.data.load_dataset_ctc import Dataset
from experiments.librispeech.metrics.ctc import do_eval_cer, do_eval_wer
from experiments.utils.data.sparsetensor import list2sparsetensor
from experiments.utils.training.learning_rate_controller import Controller
from experiments.utils.training.plot import plot_loss, plot_ler
from experiments.utils.training.multi_gpu import average_gradients
from experiments.utils.directory import mkdir, mkdir_join
from experiments.utils.parameter import count_total_parameters
from models.ctc.load_model import load


def do_train(network, params, gpu_indices):
    """Run CTC training.
    Args:
        network: network to train
        params: A dictionary of parameters
        gpu_indices: list of GPU index
    """
    # Load dataset
    if params['train_data_size'] in ['train_clean100', 'train_clean360']:
        dev = 'dev_clean'
    else:
        dev = 'dev_other'
    train_data = Dataset(
        data_type=params['train_data_size'],
        train_data_size=params['train_data_size'],
        label_type=params['label_type'], batch_size=params['batch_size'],
        num_stack=params['num_stack'], num_skip=params['num_skip'],
        sort_utt=True, sort_stop_epoch=None,
        num_gpu=len(gpu_indices), is_gpu=True)
    dev_data = Dataset(
        data_type=dev, train_data_size=params['train_data_size'],
        label_type=params['label_type'], batch_size=params['batch_size'],
        num_stack=params['num_stack'], num_skip=params['num_skip'],
        sort_utt=False, num_gpu=len(gpu_indices), is_gpu=True)

    # Tell TensorFlow that the model will be built into the default graph
    with tf.Graph().as_default(), tf.device('/cpu:0'):

        # Create a variable to track the global step
        global_step = tf.Variable(0, name='global_step', trainable=False)

        # Set optimizer
        learning_rate_pl = tf.placeholder(tf.float32, name='learning_rate')
        optimizer = network.set_optimizer(
            params['optimizer'], learning_rate_pl)

        # Calculate the gradients for each model tower
        total_grads_and_vars, total_losses = [], []
        decode_ops, ler_ops = [], []
        all_devices = ['/gpu:%d' % i_gpu for i_gpu in range(len(gpu_indices))]
        # NOTE: /cpu:0 is prepared for evaluation
        with tf.variable_scope(tf.get_variable_scope()):
            for i_gpu in range(len(all_devices)):
                with tf.device(all_devices[i_gpu]):
                    with tf.name_scope('tower_gpu%d' % i_gpu) as scope:
                        # Define placeholders in each tower
                        network.create_placeholders()

                        # Calculate the total loss for the current tower of the
                        # model. This function constructs the entire model but
                        # shares the variables across all towers.
                        tower_loss, tower_logits = network.compute_loss(
                            network.inputs_pl_list[i_gpu],
                            network.labels_pl_list[i_gpu],
                            network.inputs_seq_len_pl_list[i_gpu],
                            network.keep_prob_input_pl_list[i_gpu],
                            network.keep_prob_hidden_pl_list[i_gpu],
                            network.keep_prob_output_pl_list[i_gpu],
                            scope)
                        tower_loss = tf.expand_dims(tower_loss, axis=0)
                        total_losses.append(tower_loss)

                        # Reuse variables for the next tower
                        tf.get_variable_scope().reuse_variables()

                        # Calculate the gradients for the batch of data on this
                        # tower
                        tower_grads_and_vars = optimizer.compute_gradients(
                            tower_loss)

                        # Gradient clipping
                        tower_grads_and_vars = network._clip_gradients(
                            tower_grads_and_vars, _clip_norm=False)

                        # TODO: Optionally add gradient noise

                        # Keep track of the gradients across all towers
                        total_grads_and_vars.append(tower_grads_and_vars)

                        # Add to the graph each operation per tower
                        decode_op_tower = network.decoder(
                            tower_logits,
                            network.inputs_seq_len_pl_list[i_gpu],
                            decode_type='beam_search',
                            beam_width=20)
                        decode_ops.append(decode_op_tower)
                        ler_op_tower = network.compute_ler(
                            decode_op_tower, network.labels_pl_list[i_gpu])
                        ler_op_tower = tf.expand_dims(ler_op_tower, axis=0)
                        ler_ops.append(ler_op_tower)

        # Aggregate losses, then calculate average loss
        total_losses = tf.concat(axis=0, values=total_losses)
        loss_op = tf.reduce_mean(total_losses, axis=0)
        ler_ops = tf.concat(axis=0, values=ler_ops)
        ler_op = tf.reduce_mean(ler_ops, axis=0)

        # We must calculate the mean of each gradient. Note that this is the
        # synchronization point across all towers
        average_grads_and_vars = average_gradients(total_grads_and_vars)

        # Apply the gradients to adjust the shared variables.
        train_op = optimizer.apply_gradients(average_grads_and_vars,
                                             global_step=global_step)

        # Define learning rate controller
        lr_controller = Controller(
            learning_rate_init=params['learning_rate'],
            decay_start_epoch=params['decay_start_epoch'],
            decay_rate=params['decay_rate'],
            decay_patient_epoch=1,
            lower_better=True)

        # Build the summary tensor based on the TensorFlow collection of
        # summaries
        summary_train = tf.summary.merge(network.summaries_train)
        summary_dev = tf.summary.merge(network.summaries_dev)

        # Add the variable initializer operation
        init_op = tf.global_variables_initializer()

        # Create a saver for writing training checkpoints
        saver = tf.train.Saver(max_to_keep=None)

        # Count total parameters
        parameters_dict, total_parameters = count_total_parameters(
            tf.trainable_variables())
        for parameter_name in sorted(parameters_dict.keys()):
            print("%s %d" % (parameter_name, parameters_dict[parameter_name]))
        print("Total %d variables, %s M parameters" %
              (len(parameters_dict.keys()),
               "{:,}".format(total_parameters / 1000000)))

        csv_steps, csv_loss_train, csv_loss_dev = [], [], []
        csv_ler_train, csv_ler_dev = [], []
        # Create a session for running operation on the graph
        # NOTE: Start running operations on the Graph. allow_soft_placement
        # must be set to True to build towers on GPU, as some of the ops do not
        # have GPU implementations.
        with tf.Session(config=tf.ConfigProto(allow_soft_placement=True,
                                              log_device_placement=False)) as sess:

            # Instantiate a SummaryWriter to output summaries and the graph
            summary_writer = tf.summary.FileWriter(
                network.model_dir, sess.graph)

            # Initialize parameters
            sess.run(init_op)

            # Train model
            start_time_train = time.time()
            start_time_epoch = time.time()
            start_time_step = time.time()
            ler_dev_best = 1
            learning_rate = float(params['learning_rate'])
            epoch = 1
            for step, (data, next_epoch_flag) in enumerate(train_data()):

                # Create feed dictionary for next mini batch (train)
                inputs, labels, inputs_seq_len, _ = data
                feed_dict_train = {}
                for i_gpu in range(len(gpu_indices)):
                    feed_dict_train[network.inputs_pl_list[i_gpu]
                                    ] = inputs[i_gpu]
                    feed_dict_train[network.labels_pl_list[i_gpu]] = list2sparsetensor(
                        labels[i_gpu], padded_value=train_data.padded_value)
                    feed_dict_train[network.inputs_seq_len_pl_list[i_gpu]
                                    ] = inputs_seq_len[i_gpu]
                    feed_dict_train[network.keep_prob_input_pl_list[i_gpu]
                                    ] = network.dropout_ratio_input
                    feed_dict_train[network.keep_prob_hidden_pl_list[i_gpu]
                                    ] = network.dropout_ratio_hidden
                    feed_dict_train[network.keep_prob_output_pl_list[i_gpu]
                                    ] = network.dropout_ratio_output
                feed_dict_train[learning_rate_pl] = learning_rate

                # Update parameters
                sess.run(train_op, feed_dict=feed_dict_train)

                if (step + 1) % 200 == 0:

                    # Create feed dictionary for next mini batch (dev)
                    (inputs, labels, inputs_seq_len, _), _ = dev_data().__next__()
                    feed_dict_dev = {}
                    for i_gpu in range(len(gpu_indices)):
                        feed_dict_dev[network.inputs_pl_list[i_gpu]
                                      ] = inputs[i_gpu]
                        feed_dict_dev[network.labels_pl_list[i_gpu]] = list2sparsetensor(
                            labels[i_gpu], padded_value=dev_data.padded_value)
                        feed_dict_dev[network.inputs_seq_len_pl_list[i_gpu]
                                      ] = inputs_seq_len[i_gpu]
                        feed_dict_dev[network.keep_prob_input_pl_list[i_gpu]] = 1.0
                        feed_dict_dev[network.keep_prob_hidden_pl_list[i_gpu]] = 1.0
                        feed_dict_dev[network.keep_prob_output_pl_list[i_gpu]] = 1.0

                    # Compute loss
                    loss_train = sess.run(loss_op, feed_dict=feed_dict_train)
                    loss_dev = sess.run(loss_op, feed_dict=feed_dict_dev)
                    csv_steps.append(step)
                    csv_loss_train.append(loss_train)
                    csv_loss_dev.append(loss_dev)

                    # Change to evaluation mode
                    for i_gpu in range(len(gpu_indices)):
                        feed_dict_train[network.keep_prob_input_pl_list[i_gpu]] = 1.0
                        feed_dict_train[network.keep_prob_hidden_pl_list[i_gpu]] = 1.0
                        feed_dict_train[network.keep_prob_output_pl_list[i_gpu]] = 1.0

                    # Compute accuracy & update event files
                    ler_train, summary_str_train = sess.run(
                        [ler_op, summary_train], feed_dict=feed_dict_train)
                    ler_dev, summary_str_dev = sess.run(
                        [ler_op, summary_dev], feed_dict=feed_dict_dev)
                    csv_ler_train.append(ler_train)
                    csv_ler_dev.append(ler_dev)
                    summary_writer.add_summary(summary_str_train, step + 1)
                    summary_writer.add_summary(summary_str_dev, step + 1)
                    summary_writer.flush()

                    duration_step = time.time() - start_time_step
                    print("Step %d: loss = %.3f (%.3f) / ler = %.4f (%.4f) / lr = %.5f (%.3f min)" %
                          (step + 1, loss_train, loss_dev, ler_train, ler_dev,
                           learning_rate, duration_step / 60))
                    sys.stdout.flush()
                    start_time_step = time.time()

                # Save checkpoint and evaluate model per epoch
                if next_epoch_flag:
                    duration_epoch = time.time() - start_time_epoch
                    print('-----EPOCH:%d (%.3f min)-----' %
                          (epoch, duration_epoch / 60))

                    # Save model (check point)
                    checkpoint_file = join(network.model_dir, 'model.ckpt')
                    save_path = saver.save(
                        sess, checkpoint_file, global_step=epoch)
                    print("Model saved in file: %s" % save_path)

                    # Save fugure of loss & ler
                    plot_loss(csv_loss_train, csv_loss_dev, csv_steps,
                              save_path=network.model_dir)
                    plot_ler(csv_ler_train, csv_ler_dev, csv_steps,
                             label_type=params['label_type'],
                             save_path=network.model_dir)

                    if epoch >= 1:
                        start_time_eval = time.time()
                        if params['label_type'] != 'word':
                            print('=== Dev Data Evaluation ===')
                            ler_dev_epoch = do_eval_cer(
                                session=sess,
                                decode_ops=decode_ops,
                                network=network,
                                dataset=dev_data,
                                label_type=params['label_type'],
                                eval_batch_size=params['batch_size'])
                            print('  CER: %f %%' % (ler_dev_epoch * 100))

                            if ler_dev_epoch < ler_dev_best:
                                ler_dev_best = ler_dev_epoch
                                print('■■■ ↑Best Score (CER)↑ ■■■')

                        else:
                            print('=== Dev Data Evaluation ===')
                            ler_dev_epoch = do_eval_wer(
                                session=sess,
                                decode_ops=decode_ops,
                                network=network,
                                dataset=dev_data,
                                label_type=params['label_type'],
                                train_data_size=params['train_data_size'],
                                eval_batch_size=params['batch_size'])
                            print('  WER: %f %%' % (ler_dev_epoch * 100))

                            if ler_dev_epoch < ler_dev_best:
                                ler_dev_best = ler_dev_epoch
                                print('■■■ ↑Best Score (WER)↑ ■■■')

                        duration_eval = time.time() - start_time_eval
                        print('Evaluation time: %.3f min' %
                              (duration_eval / 60))

                        # Update learning rate
                        learning_rate = lr_controller.decay_lr(
                            learning_rate=learning_rate,
                            epoch=epoch,
                            value=ler_dev_epoch)

                        if epoch == params['num_epoch']:
                            break

                    epoch += 1
                    start_time_epoch = time.time()

            duration_train = time.time() - start_time_train
            print('Total time: %.3f hour' % (duration_train / 3600))

            # Training was finished correctly
            with open(join(network.model_dir, 'complete.txt'), 'w') as f:
                f.write('')


def main(config_path, model_save_path, gpu_indices):

    # Load a config file (.yml)
    with open(config_path, "r") as f:
        config = yaml.load(f)
        params = config['param']

    # Except for a blank class
    if params['label_type'] == 'character':
        params['num_classes'] = 28
    elif params['label_type'] == 'character_capital_divide':
        params['num_classes'] = 77
    elif params['label_type'] == 'word':
        if params['train_data_size'] == 'train_clean100':
            params['num_classes'] = 7213
        elif params['train_data_size'] == 'train_clean360':
            params['num_classes'] = 16287
        elif params['train_data_size'] == 'train_other500':
            params['num_classes'] = 18669
        elif params['train_data_size'] == 'train_all':
            params['num_classes'] = 26642

    # Model setting
    model = load(model_type=params['model'])
    network = model(
        input_size=params['input_size'] * params['num_stack'],
        num_unit=params['num_unit'],
        num_layer=params['num_layer'],
        bottleneck_dim=params['bottleneck_dim'],
        num_classes=params['num_classes'],
        parameter_init=params['weight_init'],
        clip_grad=params['clip_grad'],
        clip_activation=params['clip_activation'],
        dropout_ratio_input=params['dropout_input'],
        dropout_ratio_hidden=params['dropout_hidden'],
        dropout_ratio_output=params['dropout_output'],
        num_proj=params['num_proj'],
        weight_decay=params['weight_decay'])

    network.model_name = params['model']
    network.model_name += '_' + str(params['num_unit'])
    network.model_name += '_' + str(params['num_layer'])
    network.model_name += '_' + params['optimizer']
    network.model_name += '_lr' + str(params['learning_rate'])
    if params['bottleneck_dim'] != 0:
        network.model_name += '_bottoleneck' + str(params['bottleneck_dim'])
    if params['num_proj'] != 0:
        network.model_name += '_proj' + str(params['num_proj'])
    if params['num_stack'] != 1:
        network.model_name += '_stack' + str(params['num_stack'])
    if params['weight_decay'] != 0:
        network.model_name += '_weightdecay' + str(params['weight_decay'])
    if len(gpu_indices) >= 2:
        network.model_name += '_gpu' + str(len(gpu_indices))

    # Set save path
    network.model_dir = mkdir(model_save_path)
    network.model_dir = mkdir_join(network.model_dir, 'ctc')
    network.model_dir = mkdir_join(network.model_dir, params['label_type'])
    network.model_dir = mkdir_join(
        network.model_dir, params['train_data_size'])
    network.model_dir = mkdir_join(network.model_dir, network.model_name)

    # Reset model directory
    if not isfile(join(network.model_dir, 'complete.txt')):
        tf.gfile.DeleteRecursively(network.model_dir)
        tf.gfile.MakeDirs(network.model_dir)
    else:
        raise ValueError('File exists.')

    # Set process name
    setproctitle('libri_ctc_' + params['label_type'])

    # Save config file
    shutil.copyfile(config_path, join(network.model_dir, 'config.yml'))

    sys.stdout = open(join(network.model_dir, 'train.log'), 'w')
    do_train(network=network, params=params, gpu_indices=gpu_indices)


if __name__ == '__main__':

    args = sys.argv
    if len(args) != 3 and len(args) != 4:
        raise ValueError
    main(config_path=args[1], model_save_path=args[2],
         gpu_indices=list(map(int, args[3].split(','))))
