# file_log.py - LogSink writing lines to a laptop file (simulation only). [SIMULATED]
from cansat.hal.interfaces import LogSink


class FileLogSink(LogSink):
    def __init__(self, path):
        try:
            self._f = open(path, "w", newline="\n")
        except OSError:
            self._f = None

    def ok(self):
        return self._f is not None

    def append(self, line):
        if self._f is None:
            return False
        self._f.write(line + "\n")
        return True

    def flush(self):
        if self._f is None:
            return False
        self._f.flush()
        return True

    def close(self):
        if self._f is not None:
            self._f.close()
            self._f = None
