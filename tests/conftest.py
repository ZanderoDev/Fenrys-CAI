from pathlib import Path

import pytest


@pytest.fixture
def temp_config(tmp_path: Path):
    from fenrys.config import ConfigManager
    return ConfigManager(project_root=tmp_path, home=tmp_path)
