"""scheduler.base.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Base class for shared configuration in scheduling components.
Author: Will Bickerstaff
Version: 0.1
"""
import logging


class SchedulerComponent:
    """Base class to inject shared configuration into scheduling components.

    Provides a unified method to distribute configuration values such as
    database connections, interval settings, confidence thresholds, and
    in-memory schedule caches to all scheduler subcomponents (e.g., features,
    model, evaluation, and store).

    This class is inherited by all core components that require shared access
    to runtime settings and resources.
    """

    def set_config(self, db=None, interval_minutes=10,
                   min_confidence=0.6, schedule_cache=None, features=None):
        """Inject shared configuration into the component.

        Args
        ----
            db: Database connection object (e.g., lightlib.db.DB).
            interval_minutes (int): Schedule granularity in minutes.
            min_confidence (float): Minimum confidence for predictions.
            schedule_cache (dict): Reference to the global schedule cache.
            features: Optional reference to FeatureEngineer instance (for
                      components like model or evaluator).
        """
        self.db = db
        self.interval_minutes = interval_minutes
        self.min_confidence = min_confidence
        self.schedule_cache = schedule_cache
        self.features = features  # Optional dependency
        logging.debug("[%s] Config applied: interval minutes = %s",
                     self.__class__.__name__, interval_minutes)
