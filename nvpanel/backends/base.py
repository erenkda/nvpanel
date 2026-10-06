from dataclasses import dataclass

from ..model import Settings


@dataclass(frozen=True)
class Monitor:
    name: str  # connector name, e.g. DP-3


class BackendError(RuntimeError):
    pass


class Backend:
    id = "base"
    title = "Base"
    # Settings keys this backend can apply.
    capabilities = frozenset()
    # Human readable reasons for keys that are NOT available.
    unsupported_notes = {}

    @classmethod
    def available(cls) -> bool:
        raise NotImplementedError

    def monitors(self) -> list:
        raise NotImplementedError

    def apply(self, monitor: Monitor, settings: Settings) -> None:
        raise NotImplementedError

    def reset(self, monitor: Monitor) -> None:
        self.apply(monitor, Settings())

    def watch(self, callback) -> None:
        """Call callback() when the display layout changes (optional)."""
