"""scheduler.featuresets.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Enumerates available feature sets and defines their
             corresponding model input columns for schedule prediction.
             Used to evaluate multiple training configurations for
             optimal performance.

Author: Will Bickerstaff
Version: 0.1
"""

import logging
from enum import IntEnum
from typing import List


class FeatureSet(IntEnum):
    """Supported feature set configurations for model training."""

    MINIMAL = 0
    DEFAULT = 1
    NO_ROLLING = 2
    COUNT = 3
    FULL_FEATURES = 500
    CUSTOM = 999


class FeatureSetManager:
    """Manages feature column sets for different modeling strategies."""

    @staticmethod
    def get_columns(feature_set: FeatureSet) -> List[str]:
        """Get the feature column names corresponding to a given FeatureSet.

        Returns a list of column names used by the LightGBM model for training
        or prediction, based on the selected feature set configuration.
        This allows experimentation with different input features to compare
        model performance across sets.

        Args
        ----
            feature_set (FeatureSet): The feature set enum specifying which
                                      subset of features to use.

        Returns
        -------
            List[str]: A list of feature column names for the given set.
        """
        match feature_set:
            case FeatureSet.MINIMAL:
                return [
                    'hour_sin', 'hour_cos',
                    'day_sin', 'day_cos',
                    'interval_number'
                ]

            case FeatureSet.NO_ROLLING:
                return [
                    'hour_sin', 'hour_cos',
                    'day_sin', 'day_cos',
                    'interval_number',
                    'historical_accuracy',
                    'historical_false_positives',
                    'historical_false_negatives',
                    'historical_confidence'
                ]

            case FeatureSet.COUNT:
                return [
                    'hour_sin', 'hour_cos',
                    'month_sin', 'month_cos',
                    'day_sin', 'day_cos',
                    'rolling_count_1h', 'rolling_count_1d',
                    'interval_number',
                    'historical_accuracy',
                    'historical_false_positives',
                    'historical_false_negatives',
                    'historical_confidence'
                ]

            case FeatureSet.FULL_FEATURES:
                return [
                    'hour_sin', 'hour_cos',
                    'month_sin', 'month_cos',
                    'day_sin', 'day_cos',
                    'rolling_activity_1h', 'rolling_activity_1d',
                    'rolling_count_1h', 'rolling_count_1d',
                    'interval_number',
                    'historical_accuracy',
                    'historical_false_positives',
                    'historical_false_negatives',
                    'historical_confidence'
                ]

            case FeatureSet.CUSTOM:
                logging.warning("CUSTOM feature set is not yet implemented. "
                                "using BASELINE")
                return FeatureSetManager.get_columns(FeatureSet.MINIMAL)

            case FeatureSet.DEFAULT | _:
                if feature_set != FeatureSet.DEFAULT:
                    logging.warning("Feature set [%d] is not a valid feature "
                                    "set. using BASELINE", feature_set)
                return [
                    'hour_sin', 'hour_cos',
                    'day_sin', 'day_cos',
                    'rolling_activity_1h', 'rolling_activity_1d',
                    'interval_number',
                    'historical_accuracy',
                    'historical_false_positives',
                    'historical_false_negatives',
                    'historical_confidence'
                ]
