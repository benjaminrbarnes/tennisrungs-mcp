from pathlib import Path
from types import SimpleNamespace
import pytest
from tennisrungs_mcp import paths


@pytest.mark.parametrize('platform,expected', [
    ('darwin', 'Library/Application Support/tennisrungs-mcp'),
    ('linux', '.local/share/tennisrungs-mcp'),
])
def test_state_path_is_os_specific_and_ignores_home_override(monkeypatch, platform, expected):
    monkeypatch.setattr(paths.sys, 'platform', platform)
    monkeypatch.setenv('HOME', '/untrusted-home-override')
    monkeypatch.setattr(paths.pwd, 'getpwuid', lambda uid: SimpleNamespace(pw_dir='/synthetic-os-home'))
    assert paths.data_directory() == Path('/synthetic-os-home') / expected
