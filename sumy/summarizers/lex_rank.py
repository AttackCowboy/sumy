# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division, print_function, unicode_literals
import sys
import math

try:
    import numpy
except ImportError:
    numpy = None

from ._summarizer import AbstractSummarizer
from .._compat import Counter


class LexRankSummarizer(AbstractSummarizer):
    """
    LexRank: Graph-based Centrality as Salience in Text Summarization
    Source: http://tangra.si.umich.edu/~radev/lexrank/lexrank.pdf
    """
    threshold = 0.1
    epsilon = 0.1
    _stop_words = frozenset()

    @property
    def stop_words(self):
        return self._stop_words

    @stop_words.setter
    def stop_words(self, words):
        self._stop_words = frozenset(map(self.normalize_word, words))

    def __call__(self, document, sentences_count, query): # query is a Sentence object
        self._ensure_dependencies_installed()

        sentences_words = [self._to_words_set(s) for s in document.sentences]
        if not sentences_words:
            return tuple()

        tf_metrics = self._compute_tf(sentences_words)
        idf_metrics = self._compute_idf(sentences_words)

        ##############################################################################################

        # tf_w_s = count of how many times a word from the query appears in the given sentence
        #          Matrix dimensions: rows = sentences in doc, cols = words in query
        # tf_w_q = count of how many times a word from the query appearss in the query (constant for the query, expanded to have same dims as above):
        #          Matrix dimensions: rows = sentences in doc, cols = words in query
        #
        # rel_matrix = sum-over-words-in-query(log(tf_s_w + 1)*log(tf_w_q)*idf_metrics)
        
        # Lastly, divide rel matrix by sum of all sentences' relevances
        # rel_matrix = rel_matrix/sum-over-rows(rel_matrix)

        query_words = self._to_words_set(query.sentences[0])
        print(query_words)
        print(sentences_words[:2])
        tf_w_s_metrics = self._compute_tf_w_s(sentences_words, query_words)
        tf_w_q_metrics = self._compute_tf_w_q(query_words)
        print("tf_metrics\n",tf_metrics)
        print("idf_metrics\n", idf_metrics)
        print("tf_w_s_metrics\n", tf_w_s_metrics)
        print("tf_w_q_metrics\n", tf_w_q_metrics)


        # Create tf_w_s matrix (currently all zeros)
        tf_w_s = numpy.zeros([len(sentences_words),len(query_words)])
        # Create tf_w_q matrix (currently all zeros)
        tf_w_q = numpy.zeros([len(sentences_words),len(query_words)])
        idf_rel_matrix = self._create_idf_rel_matrix(query_words, idf_metrics)

        rel_matrix = numpy.sum((numpy.log(tf_w_s + 1) * numpy.log(tf_w_q + 1) * idf_rel_matrix),axis=1)
        rel_matrix = rel_matrix/numpy.sum(rel_matrix,axis=0)

        ##############################################################################################

        matrix = self._create_matrix(sentences_words, self.threshold, tf_metrics, idf_metrics)
        matrix = matrix + rel_matrix
        scores = self.power_method(matrix, self.epsilon)
        ratings = dict(zip(document.sentences, scores))

        return self._get_best_sentences(document.sentences, sentences_count, ratings)

    @staticmethod
    def _ensure_dependencies_installed():
        if numpy is None:
            raise ValueError("LexRank summarizer requires NumPy. Please, install it by command 'pip install numpy'.")

    def _to_words_set(self, sentence):
        words = map(self.normalize_word, sentence.words)
        return [self.stem_word(w) for w in words if w not in self._stop_words]

    def _compute_tf(self, sentences):
        tf_values = map(Counter, sentences)

        tf_metrics = []
        for sentence in tf_values:
            metrics = {}
            max_tf = self._find_tf_max(sentence)

            for term, tf in sentence.items():
                metrics[term] = tf / max_tf

            tf_metrics.append(metrics)

        return tf_metrics

    def _compute_tf_w_s(self, sentences, query):
        query_set = set(query)
        return self._compute_tf([[w for w in s if w in query_set] for s in sentences])


    def _compute_tf_w_q(self, query):

        tf_values = map(Counter, [query])

        tf_w_q_metrics = []
        for sentence in tf_values:

            print("============")
            print(sentence)
            print("============")

            metrics = {}
            max_tf = self._find_tf_max(sentence)

            for term, tf in sentence.items():
                metrics[term] = tf / max_tf

            tf_w_q_metrics.append(metrics)

        return tf_w_q_metrics



    @staticmethod
    def _find_tf_max(terms):
        return max(terms.values()) if terms else 1

    @staticmethod
    def _compute_idf(sentences):
        idf_metrics = {}
        sentences_count = len(sentences)

        for sentence in sentences:
            for term in sentence:
                if term not in idf_metrics:
                    n_j = sum(1 for s in sentences if term in s)
                    idf_metrics[term] = math.log(sentences_count / (1 + n_j))

        return idf_metrics
    
    def _create_matrix(self, sentences, threshold, tf_metrics, idf_metrics):
        """
        Creates matrix of shape |sentences|×|sentences|.
        """
        # create matrix |sentences|×|sentences| filled with zeroes
        sentences_count = len(sentences)
        matrix = numpy.zeros((sentences_count, sentences_count))
        degrees = numpy.zeros((sentences_count, ))

        for row, (sentence1, tf1) in enumerate(zip(sentences, tf_metrics)):
            for col, (sentence2, tf2) in enumerate(zip(sentences, tf_metrics)):
                matrix[row, col] = self.cosine_similarity(sentence1, sentence2, tf1, tf2, idf_metrics)

                if matrix[row, col] > threshold:
                    matrix[row, col] = 1.0
                    degrees[row] += 1
                else:
                    matrix[row, col] = 0

        for row in range(sentences_count):
            for col in range(sentences_count):
                if degrees[row] == 0:
                    degrees[row] = 1

                matrix[row][col] = matrix[row][col] / degrees[row]

        return matrix

    def _create_tf_w_s_matrix(self, tf_w_s_metrics, query_words):
        tf_w_s_matrix = np.zeros((len(tf_w_s_metrics),len(query_words)))
        for row_ind in range(len(tf_w_s_metrics)):
            for col_ind in range(len(query_words)):
                cur_metrics = tf_w_s_metrics[row_ind]
                try:
                    tf_w_s_matrix[row_ind, col_ind] = cur_metrics[query_words[col_ind]]
                except:
                    pass
        return tf_w_s_matrix

    def _create_idf_rel_matrix(self, query_words, idf_metrics):
        idf_matrix = numpy.zeros([len(query_words),])
        idx = 0
        for word in query_words:
            idf_matrix[idx] = idf_metrics[word]
            idx += 1
        return idf_matrix

    @staticmethod
    def cosine_similarity(sentence1, sentence2, tf1, tf2, idf_metrics):
        """
        We compute idf-modified-cosine(sentence1, sentence2) here.
        It's cosine similarity of these two sentences (vectors) A, B computed as cos(x, y) = A . B / (|A| . |B|)
        Sentences are represented as vector TF*IDF metrics.

        :param sentence1:
            Iterable object where every item represents word of 1st sentence.
        :param sentence2:
            Iterable object where every item represents word of 2nd sentence.
        :type tf1: dict
        :param tf1:
            Term frequencies of words from 1st sentence.
        :type tf2: dict
        :param tf2:
            Term frequencies of words from 2nd sentence
        :type idf_metrics: dict
        :param idf_metrics:
            Inverted document metrics of the sentences. Every sentence is treated as document for this algorithm.
        :rtype: float
        :return:
            Returns -1.0 for opposite similarity, 1.0 for the same sentence and zero for no similarity between sentences.
        """
        unique_words1 = frozenset(sentence1)
        unique_words2 = frozenset(sentence2)
        common_words = unique_words1 & unique_words2

        numerator = 0.0
        for term in common_words:
            numerator += tf1[term]*tf2[term] * idf_metrics[term]**2

        denominator1 = sum((tf1[t]*idf_metrics[t])**2 for t in unique_words1)
        denominator2 = sum((tf2[t]*idf_metrics[t])**2 for t in unique_words2)

        if denominator1 > 0 and denominator2 > 0:
            return numerator / (math.sqrt(denominator1) * math.sqrt(denominator2))
        else:
            return 0.0

    @staticmethod
    def power_method(matrix, epsilon):
        transposed_matrix = matrix.T
        sentences_count = len(matrix)
        p_vector = numpy.array([1.0 / sentences_count] * sentences_count)
        lambda_val = 1.0

        while lambda_val > epsilon:
            next_p = numpy.dot(transposed_matrix, p_vector)
            lambda_val = numpy.linalg.norm(numpy.subtract(next_p, p_vector))
            p_vector = next_p

        return p_vector
