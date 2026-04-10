class ProjectArchitecture:
    def __init__(self):
        self._cached_architecture = None

    def get_architecture(self):
        if self._cached_architecture is None:
            self._cached_architecture = self._get_structure_map()
        return self._cached_architecture

    def _get_structure_map(self):
        return {}