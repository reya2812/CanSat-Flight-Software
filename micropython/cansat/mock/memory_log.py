# memory_log.py - LogSink that keeps lines in memory (tests). [SIMULATED]
from cansat.hal.interfaces import LogSink


class MemoryLogSink(LogSink):
    def __init__(self):
        self.lines = []
        self.fail_writes = False  # inject storage failure

    def append(self, line):
        if self.fail_writes:
            return False
        self.lines.append(line)
        return True

    def flush(self):
        return not self.fail_writes
