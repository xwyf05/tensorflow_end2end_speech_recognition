#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Base class of CTC model."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf


OPTIMIZER_CLS_NAMES = {
    "adagrad": tf.train.AdagradOptimizer,
    "adadelta": tf.train.AdadeltaOptimizer,
    "adam": tf.train.AdamOptimizer,
    "momentum": tf.train.MomentumOptimizer,
    "rmsprop": tf.train.RMSPropOptimizer,
    "sgd": tf.train.GradientDescentOptimizer,
}


class ctcBase(object):
    """Connectionist Temporal Classification (CTC) network.
    Args:
        input_size: int, the dimensions of input vectors
        num_unit: int, the number of units in each layer
        num_layer: int, the number of layers
        num_classes: int, the number of classes of target labels
            (except for a blank label)
        splice: int, frames to splice. Default is 1 frame.
        parameter_init: A float value. Range of uniform distribution to
            initialize weight parameters
        clip_grad: A float value. Range of gradient clipping (> 0)
        clip_activation: A float value. Range of activation clipping (> 0)
        dropout_ratio_input: A float value. Dropout ratio in input-hidden
            layers
        dropout_ratio_hidden: A float value. Dropout ratio in hidden-hidden
            layers
        dropout_ratio_output: A float value. Dropout ratio in hidden-output
            layers
        weight_decay: A float value. Regularization parameter for weight decay
        name: string, model name
    """

    def __init__(self,
                 input_size,
                 num_unit,
                 num_layer,
                 num_classes,
                 splice,
                 parameter_init,
                 clip_grad,
                 clip_activation,
                 dropout_ratio_input,
                 dropout_ratio_hidden,
                 dropout_ratio_output,
                 weight_decay,
                 name):

        # Network size
        assert input_size % 3 == 0, 'input_size must be divisible by 3.'
        # NOTE: input features are expected to including Δ and ΔΔ features
        self.input_size = int(input_size)
        assert splice % 2 == 1, 'splice must be the odd number'
        self.splice = int(splice)
        self.num_classes = int(num_classes)
        self.num_unit = int(num_unit)
        self.num_layer = int(num_layer)
        self.num_classes = int(num_classes) + 1  # plus blank label
        self.name = name

        # Regularization
        self.parameter_init = float(parameter_init)
        self.clip_grad = float(clip_grad)
        self.clip_activation = float(clip_activation)
        self.dropout_ratio_input = float(dropout_ratio_input)
        self.dropout_ratio_hidden = float(dropout_ratio_hidden)
        self.dropout_ratio_output = float(dropout_ratio_output)
        self.weight_decay = float(weight_decay)

        # Summaries for TensorBoard
        self.summaries_train = []
        self.summaries_dev = []

        # Placeholders
        self.inputs_pl_list = []
        self.labels_pl_list = []
        self.inputs_seq_len_pl_list = []
        self.keep_prob_input_pl_list = []
        self.keep_prob_hidden_pl_list = []
        self.keep_prob_output_pl_list = []

    def create_placeholders(self):
        """Create placeholders and append them to list."""
        self.inputs_pl_list.append(
            tf.placeholder(tf.float32,
                           shape=[None, None, self.input_size * self.splice],
                           name='input'))
        self.labels_pl_list.append(
            tf.SparseTensor(tf.placeholder(tf.int64, name='indices'),
                            tf.placeholder(tf.int32, name='values'),
                            tf.placeholder(tf.int64, name='shape')))
        self.inputs_seq_len_pl_list.append(
            tf.placeholder(tf.int64, shape=[None], name='inputs_seq_len'))
        self.keep_prob_input_pl_list.append(
            tf.placeholder(tf.float32, name='keep_prob_input'))
        self.keep_prob_hidden_pl_list.append(
            tf.placeholder(tf.float32, name='keep_prob_hidden'))
        self.keep_prob_output_pl_list.append(
            tf.placeholder(tf.float32, name='keep_prob_output'))

    def _add_noise_to_inputs(self, inputs, stddev=0.075):
        """Add gaussian noise to the inputs.
        Args:
            inputs: the noise free input-features.
            stddev: The standart deviation of the noise.
        Returns:
            inputs: Input features plus noise.
        """
        # if stddev != 0:
        #     with tf.variable_scope("input_noise"):
        #         # Add input noise with a standart deviation of stddev.
        #         inputs = tf.random_normal(
        #             tf.shape(inputs), 0.0, stddev) + inputs
        # return inputs
        raise NotImplementedError

    def _add_noise_to_gradients(grads_and_vars, gradient_noise_scale,
                                stddev=0.075):
        """Adds scaled noise from a 0-mean normal distribution to gradients.
        Args:
            grads_and_vars:
            gradient_noise_scale:
            stddev:
        Returns:
        """
        raise NotImplementedError

    def compute_loss(self, inputs, labels, inputs_seq_len, keep_prob_input,
                     keep_prob_hidden, keep_prob_output, scope=None):
        """Operation for computing ctc loss.
        Args:
            inputs: A tensor of size `[B, T, input_size]`
            labels: A SparseTensor of target labels
            inputs_seq_len: A tensor of size `[B]`
            keep_prob_input: A float value. A probability to keep nodes in
                the input-hidden layer
            keep_prob_hidden: A float value. A probability to keep nodes in
                the hidden-hidden layers
            keep_prob_output: A float value. A probability to keep nodes in
                the hidden-output layer
            scope: A scope in the model tower
        Returns:
            total_loss: operation for computing total ctc loss
            logits: A tensor of size `[T, B, input_size]`
        """
        # Build model graph
        logits = self._build(
            inputs, inputs_seq_len,
            keep_prob_input, keep_prob_hidden, keep_prob_output)

        # Weight decay
        if self.weight_decay > 0:
            with tf.name_scope("weight_decay_loss"):
                weight_sum = 0
                for var in tf.trainable_variables():
                    if 'bias' not in var.name.lower():
                        weight_sum += tf.nn.l2_loss(var)
                tf.add_to_collection('losses', weight_sum * self.weight_decay)

        with tf.name_scope("ctc_loss"):
            ctc_losses = tf.nn.ctc_loss(
                labels,
                logits,
                tf.cast(inputs_seq_len, tf.int32),
                preprocess_collapse_repeated=False,
                ctc_merge_repeated=True,
                ignore_longer_outputs_than_inputs=False,
                time_major=True)
            ctc_loss = tf.reduce_mean(ctc_losses, name='ctc_loss_mean')
            tf.add_to_collection('losses', ctc_loss)

        # Compute total loss
        total_loss = tf.add_n(tf.get_collection('losses', scope),
                              name='total_loss')

        # Add a scalar summary for the snapshot of loss
        if self.weight_decay > 0:
            self.summaries_train.append(
                tf.summary.scalar('weight_loss_train',
                                  weight_sum * self.weight_decay))
            self.summaries_dev.append(
                tf.summary.scalar('weight_loss_dev',
                                  weight_sum * self.weight_decay))
            self.summaries_train.append(
                tf.summary.scalar('total_loss_train', total_loss))
            self.summaries_dev.append(
                tf.summary.scalar('total_loss_dev', total_loss))

        self.summaries_train.append(
            tf.summary.scalar('ctc_loss_train', ctc_loss))
        self.summaries_dev.append(
            tf.summary.scalar('ctc_loss_dev', ctc_loss))

        return total_loss, logits

    def set_optimizer(self, optimizer_name, learning_rate):
        """Set optimizer.
        Args:
            optimizer: string, name of the optimizer in OPTIMIZER_CLS_NAMES
            learning_rate: A float value, a learning rate
        Returns:
            optimizer:
        """
        optimizer_name = optimizer_name.lower()
        if optimizer_name not in OPTIMIZER_CLS_NAMES:
            raise ValueError(
                "Optimizer name should be one of [%s], you provided %s." %
                (", ".join(OPTIMIZER_CLS_NAMES), optimizer_name))

        # Select optimizer
        if optimizer_name == 'momentum':
            return OPTIMIZER_CLS_NAMES[optimizer_name](
                learning_rate=learning_rate,
                momentum=0.9)
        else:
            return OPTIMIZER_CLS_NAMES[optimizer_name](
                learning_rate=learning_rate)

    def train(self, loss, optimizer, learning_rate=None, clip_norm=False):
        """Operation for training. Only the sigle GPU training is supported.
        Args:
            loss: An operation for computing loss
            optimizer: string, name of the optimizer in OPTIMIZER_CLS_NAMES
            learning_rate: A float value, a learning rate
            clip_norm: if True, clip gradients norm by self.clip_grad
        Returns:
            train_op: operation for training
        """
        # Create a variable to track the global step
        global_step = tf.Variable(0, name='global_step', trainable=False)

        # Set optimizer
        self.optimizer = self.set_optimizer(optimizer, learning_rate)

        if self.clip_grad is not None:
            # Compute gradients
            grads_and_vars = self.optimizer.compute_gradients(loss)

            # Clip gradients
            clipped_grads_and_vars = self._clip_gradients(grads_and_vars,
                                                          clip_norm)

            # Create gradient updates
            train_op = self.optimizer.apply_gradients(
                clipped_grads_and_vars,
                global_step=global_step)

        else:
            # Use the optimizer to apply the gradients that minimize the loss
            # and also increment the global step counter as a single training
            # step
            train_op = self.optimizer.minimize(loss, global_step=global_step)

        return train_op

    def _clip_gradients(self, grads_and_vars, _clip_norm):
        """Clip gradients.
        Args:
            grads_and_vars: list of (grads, vars) tuples
            _clip_norm: if True, clip gradients norm by self.clip_grad
        Returns:
            clipped_grads_and_vars: list of (clipped grads, vars)
        """
        # TODO: Optionally add gradient noise

        clipped_grads_and_vars = []

        if _clip_norm:
            # Clip gradient norm
            for grad, var in grads_and_vars:
                if grad is not None:
                    clipped_grads_and_vars.append(
                        (tf.clip_by_norm(grad, clip_norm=self.clip_grad), var))
        else:
            # Clip gradient
            for grad, var in grads_and_vars:
                if grad is not None:
                    clipped_grads_and_vars.append(
                        (tf.clip_by_value(grad,
                                          clip_value_min=-self.clip_grad,
                                          clip_value_max=self.clip_grad), var))

        # TODO: Add histograms for variables, gradients (norms)
        # self._tensorboard(trainable_vars)

        return clipped_grads_and_vars

    def decoder(self, logits, inputs_seq_len, decode_type, beam_width=None):
        """Operation for decoding.
        Args:
            logits: A tensor of size `[T, B, input_size]`
            inputs_seq_len: A tensor of size `[B]`
            decode_type: greedy or beam_search
            beam_width: beam width for beam search
        Return:
            decode_op: A SparseTensor
        """
        if decode_type not in ['greedy', 'beam_search']:
            raise ValueError('decode_type is "greedy" or "beam_search".')

        if decode_type == 'greedy':
            decoded, _ = tf.nn.ctc_greedy_decoder(
                logits, tf.cast(inputs_seq_len, tf.int32))
        elif decode_type == 'beam_search':
            if beam_width is None:
                raise ValueError('Set beam_width.')
            decoded, _ = tf.nn.ctc_beam_search_decoder(
                logits, tf.cast(inputs_seq_len, tf.int32),
                beam_width=beam_width)

        decode_op = tf.to_int32(decoded[0])

        return decode_op

    def posteriors(self, logits):
        """Operation for computing posteriors of each time steps.
        Args:
            logits: A tensor of size `[T, B, input_size]`
        Return:
            posteriors_op: operation for computing posteriors for each class
        """
        # Convert to batch-major: `[batch_size, max_time, num_classes]'
        logits = tf.transpose(logits, (1, 0, 2))

        logits_2d = tf.reshape(logits, [-1, self.num_classes])
        posteriors_op = tf.nn.softmax(logits_2d)

        return posteriors_op

    def compute_ler(self, decode_op, labels):
        """Operation for computing LER (Label Error Rate).
        Args:
            decode_op: operation for decoding
            labels: A SparseTensor of target labels
        Return:
            ler_op: operation for computing LER
        """
        # Compute LER (normalize by label length)
        ler_op = tf.reduce_mean(tf.edit_distance(
            decode_op, labels, normalize=True))

        # Add a scalar summary for the snapshot of LER
        self.summaries_train.append(tf.summary.scalar('ler_train', ler_op))
        self.summaries_dev.append(tf.summary.scalar('ler_dev', ler_op))

        return ler_op

    def _tensorboard(self, trainable_vars):
        """Compute statistics for TensorBoard plot.
        Args:
            trainable_vars:
        """
        # Histogram
        with tf.name_scope("train"):
            for var in trainable_vars:
                self.summaries_train.append(
                    tf.summary.histogram(var.name, var))
        with tf.name_scope("dev"):
            for var in trainable_vars:
                self.summaries_dev.append(
                    tf.summary.histogram(var.name, var))

        # Mean
        with tf.name_scope("mean_train"):
            for var in trainable_vars:
                self.summaries_train.append(
                    tf.summary.scalar(var.name,
                                      tf.reduce_mean(var)))
        with tf.name_scope("mean_dev"):
            for var in trainable_vars:
                self.summaries_dev.append(
                    tf.summary.scalar(var.name,
                                      tf.reduce_mean(var)))

        # Standard deviation
        with tf.name_scope("stddev_train"):
            for var in trainable_vars:
                self.summaries_train.append(
                    tf.summary.scalar(var.name, tf.sqrt(
                        tf.reduce_mean(tf.square(var - tf.reduce_mean(var))))))
        with tf.name_scope("stddev_dev"):
            for var in trainable_vars:
                self.summaries_dev.append(
                    tf.summary.scalar(var.name, tf.sqrt(
                        tf.reduce_mean(tf.square(var - tf.reduce_mean(var))))))

        # Max
        with tf.name_scope("max_train"):
            for var in trainable_vars:
                self.summaries_train.append(
                    tf.summary.scalar(var.name,
                                      tf.reduce_max(var)))
        with tf.name_scope("max_dev"):
            for var in trainable_vars:
                self.summaries_dev.append(
                    tf.summary.scalar(var.name, tf.reduce_max(var)))

        # Min
        with tf.name_scope("min_train"):
            for var in trainable_vars:
                self.summaries_train.append(
                    tf.summary.scalar(var.name,
                                      tf.reduce_min(var)))
        with tf.name_scope("min_dev"):
            for var in trainable_vars:
                self.summaries_dev.append(
                    tf.summary.scalar(var.name,
                                      tf.reduce_min(var)))
