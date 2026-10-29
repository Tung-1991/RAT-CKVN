"""Read account previews off Tk. A superseded result cannot replace a newer request."""
import queue
import threading

from ckps.connections.dnse.discovery import AccountReader


class ConnectionProbe:
    def __init__(self, reader_factory=AccountReader):
        self.reader_factory = reader_factory
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.revision = 0
        self.thread = threading.Thread(target=self._run, name='ckps-account-preview', daemon=True)
        self.thread.start()

    def request(self, credentials, account='', package=''):
        self.revision += 1
        self.commands.put((self.revision, dict(credentials), account, package))
        return self.revision

    def _run(self):
        while not self.stop.is_set():
            try:revision, credentials, account, package = self.commands.get(timeout=.2)
            except queue.Empty:continue
            if revision != self.revision:continue
            reader = None
            try:
                reader = self.reader_factory(credentials['key'], credentials['secret'])
                reader.stopping = self.stop
                result = reader.profile(account, package)
            except Exception as exc:result = {'error': str(exc)}
            finally:
                if reader:reader.close()
            if not self.stop.is_set() and revision == self.revision:self.events.put((revision, result))

    def close(self):
        self.stop.set()
