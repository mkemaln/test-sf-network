from typing import Iterable


class FailureInjector:
    def __init__(self, network) -> None:
        self.network = network
        self.active: tuple[str, str] | None = None

    def inject(self, link: tuple[str, str]) -> None:
        self.network.configLinkStatus(link[0], link[1], "down")
        self.active = link

    def restore(self) -> None:
        if self.active is not None:
            self.network.configLinkStatus(self.active[0], self.active[1], "up")
            self.active = None

    @staticmethod
    def choose_link(links: Iterable[tuple[str, str]], rng) -> tuple[str, str]:
        values = list(links)
        if not values:
            raise ValueError("cannot choose a failure from an empty link set")
        return values[int(rng.integers(0, len(values)))]
