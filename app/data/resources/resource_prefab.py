from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

class WithResources(ABC):
    # The attributes holding where this resource's files are. save() leaves them
    # out, since loading derives them from the resource's folder and nid, so the
    # editor's undo history keeps them beside the saved form
    path_fields: Tuple[str, ...] = ('full_path',)

    @abstractmethod
    def set_full_path(self, path: str) -> None:
        ...

    @abstractmethod
    def used_resources(self) -> List[Optional[Path]]:
        ...

    def file_paths(self) -> Dict[str, Any]:
        return {name: getattr(self, name) for name in self.path_fields}

    def set_file_paths(self, paths: Dict[str, Any]) -> None:
        for name, path in paths.items():
            setattr(self, name, path)
