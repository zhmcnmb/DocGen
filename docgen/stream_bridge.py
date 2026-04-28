import queue
import threading
from collections.abc import Generator


class StreamBridge:
    _instances: dict[str, "StreamBridge"] = {}

    @classmethod
    def get(cls, session_id: str) -> "StreamBridge":
        if session_id not in cls._instances:
            cls._instances[session_id] = cls(session_id)
        return cls._instances[session_id]

    @classmethod
    def remove(cls, session_id: str) -> None:
        cls._instances.pop(session_id, None)

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._queue: queue.Queue = queue.Queue()
        self._done = threading.Event()

    def push(self, event: str, data: dict) -> None:
        self._queue.put((event, data))

    def finish(self) -> None:
        self._done.set()
        self._queue.put(None)

    def events(self) -> Generator[tuple[str, dict], None, None]:
        while True:
            item = self._queue.get(timeout=1)
            if item is None:
                return
            yield item

    @property
    def is_done(self) -> bool:
        return self._done.is_set()

    def reset(self) -> None:
        self._queue = queue.Queue()
        self._done = threading.Event()
