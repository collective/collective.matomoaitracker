"""What the tracking view did, shown in the control panel.

Kept in memory of the Zope process, not in the database: recording a batch
must not write to the database.  With several Zope instances, every instance
counts the batches it handled since it started.
"""

from datetime import datetime
from datetime import UTC
from threading import Lock


class TrackingStatus:
    def __init__(self):
        self.lock = Lock()
        self.reset()

    def reset(self):
        self.started = datetime.now(UTC)
        self.last_batch = None
        self.batches = 0
        self.tracked = 0
        self.rejected = 0
        self.skipped = 0
        self.last_error = None
        self.last_error_time = None

    def record_batch(self, tracked, rejected, skipped):
        with self.lock:
            self.last_batch = datetime.now(UTC)
            self.batches += 1
            self.tracked += tracked
            self.rejected += rejected
            self.skipped += skipped

    def record_error(self, message):
        with self.lock:
            self.last_error = message
            self.last_error_time = datetime.now(UTC)


STATUS = TrackingStatus()
