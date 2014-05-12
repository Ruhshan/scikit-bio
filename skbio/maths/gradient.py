#!/usr/bin/env python
r"""
Gradient analyses (:mod:`skbio.maths.gradient`)
===============================================

.. currentmodule:: skbio.maths.gradient

This module provides functionality for performing gradient analyses.

Classes
-------

.. autosummary::
   :toctree: generated/

   AverageVectors
   TrajectoryVectors
   DifferenceVectors
   WindowDifferenceVectors
   GroupResults
   CategoryResults
   VectorsResults

"""

# -----------------------------------------------------------------------------
# Copyright (c) 2013--, scikit-bio development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
# -----------------------------------------------------------------------------

from __future__ import division

from copy import deepcopy
from collections import namedtuple, defaultdict

import numpy as np

from skbio.util.sort import signed_natsort
from skbio.maths.stats.test import ANOVA_one_way


class GroupResults(namedtuple('GroupResults', ('name', 'vector', 'mean',
                                               'info', 'message'))):
    r"""Store the vector results of a group of a metadata category

    Attributes
    ----------
    name : str
        The name of the group within the metadata category
    vector : 1-D numpy array
        The result vector
    mean : float
        The mean of the vector
    info : dict
        Any extra information computed by the vector algorithm. Depends on the
        algorithm
    message : str
        A message with information of the execution of the algorithm
    """
    __slots__ = ()  # To avoid creating a dict, as a namedtuple doesn't have it

    def __new__(cls, name, vector, mean, info, message):
        return super(GroupResults, cls).__new__(cls, name, vector, mean,
                                                info, message)

    def to_files(self, out_f, raw_f):
        r"""Save the vector analysis results for a category group to files in
        text format.

        Parameters
        ----------
        out_f : file-like object
            File-like object to write vectors analysis data to. Must have a
            ``write`` method. It is the caller's responsibility to close
            `out_f` when done (if necessary)
        raw_f : file-like object
            File-like object to write vectors raw values. Must have a ``write``
            method. It is the caller's responsibility to close `out_f` when
            done (if necessary)
        """
        out_f.write('For group "%s", the group means is: %f\n'
                    % (self.name, self.mean))
        raw_f.write('For group "%s":\n'
                    % (self.name, self.vector))

        if self.message:
            out_f.write('%s\n' % self.message)
            raw_f.write('%s\n' % self.message)

        out_f.write('The info is:%s\n' % self.info)
        raw_f.write('The vector is:\n%s\n' % self.vector)


class CategoryResults(namedtuple('CategoryResults', ('category', 'probability',
                                                     'groups', 'message'))):
    r"""Store the vector results of a metadata category

    Attributes
    ----------
    category : str
        The name of the category
    probability : float
        The ANOVA probability that the category groups are independent
    groups : list of GroupResults
        The vector results for each group in the category
    message : str
        A message with information of the execution of the algorithm
    """
    __slots__ = ()  # To avoid creating a dict, as a namedtuple doesn't have it

    def __new__(cls, category, probability, groups, message):
        return super(CategoryResults, cls).__new__(cls, category, probability,
                                                   groups, message)

    def to_files(self, out_f, raw_f):
        r"""Save the vector analysis results for a category to files in
        text format.

        Parameters
        ----------
        out_f : file-like object
            File-like object to write vectors analysis data to. Must have a
            ``write`` method. It is the caller's responsibility to close
            `out_f` when done (if necessary)
        raw_f : file-like object
            File-like object to write vectors raw values. Must have a ``write``
            method. It is the caller's responsibility to close `out_f` when
            done (if necessary)
        """
        if self.probability is None:
            out_f.write('Grouped by "%s" %s\n' % (self.category, self.message))
        else:
            out_f.write('Grouped by "%s", probability: %f\n'
                        % (self.category, self.probability))
            raw_f.write('Grouped by "%s"\n' % self.category)
            for group in self.groups:
                group.to_files(out_f, raw_f)


class VectorsResults(namedtuple('VectorsResults', ('algorithm', 'weighted',
                                                   'categories'))):
    r"""Store the vector results

    Attributes
    ----------
    algorithm : str
        The algorithm used to compute vectors
    weighted : bool
        If true, a weighting vector was used
    categories : list of CategoryResults
        The vector results for each metadata category
    """
    __slots__ = ()  # To avoid creating a dict, as a namedtuple doesn't have it

    def __new__(cls, algorithm, weighted, categories):
        return super(VectorsResults, cls).__new__(cls, algorithm, weighted,
                                                  categories)

    def to_files(self, out_f, raw_f):
        r"""Save the vector analysis results to files in text format.

        Parameters
        ----------
        out_f : file-like object
            File-like object to write vectors analysis data to. Must have a
            ``write`` method. It is the caller's responsibility to close
            `out_f` when done (if necessary)
        raw_f : file-like object
            File-like object to write vectors raw values. Must have a ``write``
            method. It is the caller's responsibility to close `out_f` when
            done (if necessary)
        """
        out_f.write('Vectors algorithm: %s\n' % self.algorithm)
        raw_f.write('Vectors algorithm: %s\n' % self.algorithm)

        if self.weighted:
            out_f.write('** This output is weighted **\n')
            raw_f.write('** This output is weighted **\n')

        for cat_results in self.categories:
            cat_results.to_files(out_f, raw_f)


class BaseVectors(object):
    r"""Base class for the Vector algorithms

    Parameters
    ----------
    coords : pandas.DataFrame
        The coordinates for each sample id
    prop_expl : numpy 1-D array
        The proportion explained by each axis in coords
    metamap : pandas.DataFrame
        The metadata map, indexed by sample ids and columns are metadata
        categories
    vector_categories : list of str, optional
        A list of metadata categories to use to create the vectors. If None is
        passed, the vectors for all metadata categories are computed. Default:
        None, compute all of them
    sort_category : str, optional
        The metadata category to use to sort the vectors. Default: None
    axes : int, optional
        The number of axes to account while doing the vector specific
        calculations. Pass 0 to compute all of them. Default: 3
    weighted : bool, optional
        If true, the output is weighted by the space between samples in the
        `sort_category` column

    Raises
    ------
    ValueError
        If any category of `vector_categories` is not present in `metamap`
        If `sort_category` is not present in `metamap`
        If `axes` is not between 0 and the maximum number of axes available
        If `weighted` is True and no `sort_category` is provided
        If `weighted` is True and the values under `sort_category` are not
            numerical
        If `coords` and `metamap` does not have samples in common
    """
    # Should be defined by the derived classes
    _alg_name = None

    def __init__(self, coords, prop_expl, metamap, vector_categories=None,
                 sort_category=None, axes=3, weighted=False):
        if not vector_categories:
            # If vector_categories is not provided, use all the categories
            # present in the metadata map
            vector_categories = metamap.keys()
        else:
            # Check that vector_categories are in metamap
            for category in vector_categories:
                if category not in metamap:
                    raise ValueError("Category %s not present in metadata."
                                     % category)

        # Check that sort_categories is in metamap
        if sort_category and sort_category not in metamap:
            raise ValueError("Sort category %s not present in metadata."
                             % sort_category)

        if axes == 0:
            # If axes == 0, we should compute the vectors for all axes
            axes = len(prop_expl)
        elif axes > len(prop_expl) or axes < 0:
            # Axes should be 0 <= axes <= len(prop_expl)
            raise ValueError("axes should be between 0 and the max number of "
                             "axes available (%d), found: %d "
                             % (len(prop_expl), axes))

        # Restrict coordinates to those axes that we actually need to compute
        self._coords = coords.ix[:, :axes-1]
        self._prop_expl = prop_expl[:axes]
        self._metamap = metamap
        self._weighted = weighted

        # Remove any samples from coords not present in mapping file
        # and remove any samples from metamap not present in coords
        self._normalize_samples()

        # Create groups
        self._make_groups(vector_categories, sort_category)

        # Compute the weighting_vector
        self._weighting_vector = None
        if weighted:
            if not sort_category:
                raise ValueError("You should provide a sort category if you "
                                 "want to weight the vectors")
            try:
                self._weighting_vector = self._metamap[sort_category].astype(
                    np.float64)
            except ValueError:
                    raise ValueError("The sorting category must be numeric")

        # Initialize the message buffer
        self._message_buffer = []

    def _normalize_samples(self):
        """Ensures that `self._coords` and `self._metamap` have the same
        sample ids

        Raises
        ------
        ValueError
            If `coords` and `metamap` does not have samples in common
        """
        # Figure out the sample ids in common
        coords_sample_ids = set(self._coords.index)
        mm_sample_ids = set(self._metamap.index)
        sample_ids = coords_sample_ids.intersection(mm_sample_ids)

        # Check if they actually have sample ids in common
        if not sample_ids:
            raise ValueError("Coordinates and metadata map had no samples "
                             "in common")

        # Need to take a subset of coords
        if coords_sample_ids != sample_ids:
            self._coords = self._coords.ix[sample_ids]
        # Need to take a subset of metamap
        if mm_sample_ids != sample_ids:
            self._metamap = self._metamap.ix[sample_ids]

    def _make_groups(self, vector_categories, sort_category):
        """Groups the sample ids in `self._metamap` by the values in
        `vector_categories`

        Creates `self._groups`, a dictionary keyed by category and values are
        dictionaries in which the keys represent the group name within the
        category and values are ordered lists of sample ids

        If `sort_category` is not None, the sample ids are sorted based on the
        values under this category in the metadata map. Otherwise, they are
        sorted using the sample id.

        Parameters
        ----------
        vector_categories : list of str
            A list of metadata categories to use to create the groups.
            Default: None, compute all of them
        sort_category : str or None
            The category from self._metamap to use to sort groups
        """
        # If sort_category is provided, we used the value of such category to
        # sort. Otherwise, we use the sample id.
        if sort_category:
            sort_val = lambda sid: self._metamap[sort_category][sid]
        else:
            sort_val = lambda sid: sid

        self._groups = defaultdict(dict)
        for cat in vector_categories:
            # Group samples by category
            gb = self._metamap.groupby(cat)
            for g, df in gb:
                sorted_list = signed_natsort([(sort_val(sid), sid)
                                              for sid in df.index])
                self._groups[cat][g] = [val[1] for val in sorted_list]

    def get_vectors(self):
        """Compute the vectors for each group in each category and run ANOVA
        over the results to test group independence.

        Returns
        -------
        VectorsResults
            An instance of VectorsResults holding the results of the vector
            analysis.
        """
        result = VectorsResults(self._alg_name, self._weighted, [])
        # Loop through all the categories that we should compute the vectors
        for cat, cat_groups in self._groups.iteritems():
            # Loop through all the category values present in the current
            # category and compute the vector for each of the category value
            # present in
            res_by_group = [self._get_group_vectors(group, sample_ids)
                            for group, sample_ids in cat_groups.iteritems()]

            result.categories.append(self._test_vectors(cat, res_by_group))

        return result

    def _get_group_vectors(self, group_name, sids):
        """"""
        # We multiply the coord values with the prop_expl
        vectors = self._coords.ix[sids] * self._prop_expl

        if vectors.empty:
            # Raising a RuntimeError since in a usual execution this should
            # never happens. The only way this can happen is if the user
            # directly calls this function, which shouldn't be done
            # (that's why the function is private)
            raise RuntimeError("No samples to process, an empty list cannot "
                               "be processed")

        # The weighting can only be done over vectors with a length greater
        # than 1
        if self._weighted and len(sids) > 1:
            vectors_copy = deepcopy(vectors)
            try:
                vectors = self._weight_by_vector(vectors_copy,
                                                 self._weighting_vector[sids])
            except (FloatingPointError, ValueError):
                self._message_buffer.append("Could not weight group, no "
                                            "gradient in the the "
                                            "weighting vector.\n")
                vectors = vectors_copy

        return self._compute_vector_results(group_name, vectors.ix[sids])

    def _compute_vector_results(self, group_name, vectors):
        raise NotImplementedError("No algorithm is implemented on the base "
                                  "class.")

    def _weight_by_vector(self, vector, w_vector):
        """weights the values of 'vector' given a weighting vector 'w_vector'.

        Each value in 'vector' will be weighted by the 'rate of change'
        to 'optimal rate of change' ratio, meaning that when calling this
        function over evenly spaced 'w_vector' values, no change will be
        reflected on the output.

        Parameters
        ----------
        vector: pandas.DataFrame
            Values to weight
        w_vector: pandas.Series
            Values used to weight 'vector'

        Returns
        -------
        pandas.DataFrame
            A weighted version of 'vector'.

        Raises
        ------
        ValueError
            If vector and w_vector don't have equal lengths
            If w_vector is not a gradient
        TypeError
            If vector and w_vector are not iterables
        """
        try:
            if len(vector) != len(w_vector):
                raise ValueError("vector (%d) & w_vector (%d) must be equal "
                                 "lengths" % (len(vector), len(w_vector)))
        except TypeError:
            raise TypeError("vector and w_vector must be iterables")

        # check no repeated values are passed in the weighting vector
        if len(set(w_vector)) != len(w_vector):
            raise ValueError("The weighting vector must be a gradient")

        # no need to weight in case of a one element vector
        if len(w_vector) == 1:
            return vector

        # Cast to float so divisions have a floating point resolution
        total_length = float(max(w_vector) - min(w_vector))

        # reflects the expected gradient between subsequent values in w_vector
        # the first value isn't weighted so subtract one from the number of
        # elements
        optimal_gradient = total_length/(len(w_vector)-1)

        # for all elements apply the weighting function
        for i, idx in enumerate(vector.index):
            # if it's the first element, no weighting to do
            if i != 0:
                vector.ix[idx] = (vector.ix[idx] * optimal_gradient /
                                  (np.abs((w_vector[i] - w_vector[i-1]))))

        return vector

    def _test_vectors(self, category, res_by_group):
        """Run ANOVA over `res_by_group`

        If ANOVA cannot be run in the current category (because either there is
        only one group in category or there is a group with only one member)
        the result CategoryResults instance has `probability` and `groups` set
        to None and message is set to a string explaining why ANOVA was not run

        Returns
        -------
        CategoryResults
            An instance of CategoryResults holding the results of the vector
            analysis applied on `category`
        """
        # If there is only one group under category we cannot run ANOVA
        if len(res_by_group) == 1:
            return CategoryResults(category, None, None,
                                   'Only one value in the group.')
        # Check if groups can be tested using ANOVA. ANOVA testing requires
        # all elements to have at least size greater to one.
        values = [res.vector for res in res_by_group]
        if any([len(value) == 1 for value in values]):
            return CategoryResults(category, None, None,
                                   'This group can not be used. All groups '
                                   'should have more than 1 element.')
        # We are ok to run ANOVA
        F, p_val = ANOVA_one_way(values)
        return CategoryResults(category, p_val, res_by_group, None)


class AverageVectors(BaseVectors):
    """docstring for AverageVectors"""

    _alg_name = 'avg'

    def _compute_vector_results(self, group_name, vectors):
        """"""
        center = np.average(vectors, axis=0)
        if len(vectors) == 1:
            vector = np.array([np.linalg.norm(center)])
            calc = {'avg': vector[0]}
        else:
            vector = np.array([np.linalg.norm(row[1].get_values() - center)
                               for row in vectors.iterrows()])
            calc = {'avg': np.average(vector)}

        msg = ''.join(self._message_buffer) if self._message_buffer else None
        # Reset the message buffer
        self._message_buffer = []
        return GroupResults(group_name, vector, np.mean(vector), calc, msg)


class TrajectoryVectors(BaseVectors):
    """"""

    _alg_name = 'trajectory'

    def _compute_vector_results(self, group_name, vectors):
        """"""
        if len(vectors) == 1:
            vector = [np.linalg.norm(vectors)]
            calc = {'trajectory': vector[0]}
        else:
            vector = np.array([np.linalg.norm(vectors.ix[i+1].get_values() -
                                              vectors.ix[i].get_values())
                               for i in range(len(vectors) - 1)])
            calc = {'trajectory': np.linalg.norm(vector)}

        msg = ''.join(self._message_buffer) if self._message_buffer else None
        # Reset the message buffer
        self._message_buffer = []
        return GroupResults(group_name, vector, np.mean(vector), calc, msg)


class DifferenceVectors(BaseVectors):
    """"""

    _alg_name = 'diff'

    def _compute_vector_results(self, group_name, vectors):
        """"""
        if len(vectors) == 1:
            vector = [np.linalg.norm(vectors)]
            calc = {'mean': vector[0], 'std': 0}
        elif len(vectors) == 2:
            vector = [np.linalg.norm(vectors[1] - vectors[0])]
            calc = {'mean': vector[0], 'std': 0}
        else:
            vec_norm = np.array([np.linalg.norm(vectors.ix[i+1].get_values() -
                                                vectors.ix[i].get_values())
                                 for i in range(len(vectors) - 1)])
            vector = np.diff(vec_norm)
            calc = {'mean': np.mean(vector), 'std': np.std(vector)}

        msg = ''.join(self._message_buffer) if self._message_buffer else None
        # Reset the message buffer
        self._message_buffer = []
        return GroupResults(group_name, vector, np.mean(vector), calc, msg)


class WindowDifferenceVectors(BaseVectors):
    """docstring for WindowDifferenceVectors"""

    _alg_name = 'wdiff'

    def __init__(self, coords, prop_expl, metamap, window_size, **kwargs):
        super(WindowDifferenceVectors, self).__init__(coords, prop_expl,
                                                      metamap, **kwargs)

        if window_size < 1 or not isinstance(window_size, (long, int)):
            raise ValueError("The window_size must be a positive integer")

        self._window_size = window_size

    def _compute_vector_results(self, group_name, vectors):
        """Perform the first difference algorithm between windows of values in a
        vector and each value.

        Parameters
        ----------
        vector: numpy array
            Values to calculate the windowed_diff
        window_size: int or long
            Size of the window

        Returns
        -------
        numpy array
            Array where the Nth value is the difference between the mean of
            vector[N+1:N+1+window_size] and vector[N]. By definition this array
            will have 'window_size' less elements than 'vector'.

        Raises
        ------
        ValueError
            If the window_size is not a positive integer
            If the window_size is greater than the vector length
        """
        if len(vectors) == 1:
            vector = [np.linalg.norm(vectors)]
            calc = {'mean': vector, 'std': 0}
        elif len(vectors) == 2:
            vector = [np.linalg.norm(vectors[1] - vectors[0])]
            calc = {'mean': vector, 'std': 0}
        else:
            vec_norm = np.array([np.linalg.norm(vectors.ix[i+1].get_values() -
                                                vectors.ix[i].get_values())
                                 for i in range(len(vectors) - 1)])
            # windowed first differences won't be able on every group,
            # specially given the variation of size that a vector tends to have
            if len(vec_norm) <= self._window_size:
                vector = vec_norm
                self._message_buffer.append("Cannot calculate the first "
                                            "difference with a window of size "
                                            "(%d)." % self._window_size)
            else:
                # Replicate the last element as many times as required
                for idx in range(0, self._window_size):
                    vec_norm = np.append(vec_norm, vec_norm[-1:], axis=0)
                vector = []
                for idx in range(0, len(vec_norm) - self._window_size):
                    # Meas has to be over axis 0 so it handles arrays of arrays
                    element = np.mean(vec_norm[(idx + 1):
                                               (idx + 1 + self._window_size)],
                                      axis=0)
                    vector.append(element - vec_norm[idx])
                vector = np.array(vector)

            calc = {'mean': np.mean(vector), 'std': np.std(vector)}

        msg = ''.join(self._message_buffer) if self._message_buffer else None
        # Reset the message buffer
        self._message_buffer = []
        return GroupResults(group_name, vector, np.mean(vector), calc, msg)
