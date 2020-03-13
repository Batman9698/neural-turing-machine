"""An NTM's memory implementation."""
import numpy as np

import tensorflow as tf
from tensorflow.keras import Model


def _convolve(w, s):
    """Circular convolution implementation."""
    assert s.shape[0] == 3
    t = tf.concat([w[-1:], w, w[:1]], axis=0)
    s = tf.cast(s, dtype='float32')
    c = tf.nn.conv1d(tf.reshape(t, (1, -1, 1)), tf.reshape(s, (-1, 1, 1)), stride=1, padding='VALID')
    c = tf.reshape(c, (-1,))
    return c


class NTMMemory(Model):
    """Memory bank for NTM."""
    def __init__(self, n_rows: int, n_cols: int):
        """Initialize the NTM Memory matrix.
        The memory's dimensions are (n_rows x n_cols).
        Each batch has it's own memory matrix.
        :param n_rows: Number of rows in the memory.
        :param n_cols: Number of columns in the memory.
        """
        super(NTMMemory, self).__init__()

        self.n_rows = n_rows
        self.n_cols = n_cols

        # Initialize memory tensor
        self.prev_mem = None
        self.mem: tf.Tensor = tf.zeros((n_rows, n_cols))

        # Initialize memory bias tensor
        stdev = 1 / (np.sqrt(n_rows + n_cols))
        self.mem_bias: tf.Variable = tf.Variable(tf.random.uniform((n_rows, n_cols), -stdev, stdev), name='mem_bias')

    def reset(self):
        """Initialize memory from bias, for start-of-sequence."""
        self.mem = tf.convert_to_tensor(self.mem_bias)

    def size(self):
        return self.N, self.M

    def read(self, weights: tf.Tensor):
        """Read from memory (according to section 3.1)."""
        return tf.linalg.matvec(tf.transpose(self.mem), weights)

    def write(self, w, e, a):
        """write to memory (according to section 3.2)."""
        self.prev_mem = self.mem
        erase = tf.matmul(tf.expand_dims(w, -1), tf.expand_dims(e, 0))
        add = tf.matmul(tf.expand_dims(w, -1), tf.expand_dims(a, 0))
        self.mem = self.prev_mem * (1 - erase) + add

    def address(self, k, beta, g, s, gamma, w_prev):
        """NTM Addressing (according to section 3.3).
        Returns a softmax weighting over the rows of the memory matrix.
        :param k: The key vector.
        :param beta: The key strength (focus).
        :param g: Scalar interpolation gate (with previous weighting).
        :param s: Shift weighting.
        :param gamma: Sharpen weighting scalar.
        :param w_prev: The weighting produced in the previous time step.
        """
        # Content focus
        wc = self._similarity(k, beta)

        # Location focus
        wg = self._interpolate(w_prev, wc, g)
        w_hat = self._shift(wg, s)
        w = self._sharpen(w_hat, gamma)

        return w

    def _similarity(self, k, beta):
        cos_sim = 1 - tf.keras.losses.cosine_similarity(self.mem + 1e-16, k + 1e-16)
        w = tf.nn.softmax(beta * cos_sim, axis=-1)
        return w

    def _interpolate(self, w_prev, wc, g):
        return g * wc + (1 - g) * w_prev

    def _shift(self, wg, s):
        result = tf.zeros(wg.shape)
        result = _convolve(wg, s)
        return result

    def _sharpen(self, w_hat, gamma):
        w = w_hat ** gamma
        w = w / (tf.math.reduce_sum(w) + 1e-16)
        return w