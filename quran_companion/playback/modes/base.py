class Mode:
    """Interface every playback mode implements. `session` gives access to data, settings and views."""

    def __init__(self, session):
        self.session = session

    def start(self, ayah: int) -> None:
        raise NotImplementedError

    def tick(self) -> None:
        """Called regularly while the session is active."""

    def step(self, d: int) -> None:
        """Next (+1) / previous (-1) / current again (0)."""

    def pause(self) -> bool:
        """Pause; return False if there is nothing to pause."""
        return False

    def resume(self) -> None:
        pass

    def stop(self) -> None:
        pass
