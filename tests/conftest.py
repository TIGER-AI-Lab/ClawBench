import pytest
from pathlib import Path
import subprocess
from unittest.mock import Mock

@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path

@pytest.fixture
def set_env(monkeypatch):
    def _set_env(key, value):
        monkeypatch.setenv(key, value)
    return _set_env

@pytest.fixture
def mock_subprocess_run(mocker):
    def _mock_subprocess_run(returncode=0, stdout="", stderr=""):
        mock = mocker.patch('subprocess.run')
        mock_return = Mock(spec=subprocess.CompletedProcess)
        mock_return.returncode = returncode
        mock_return.stdout = stdout
        mock_return.stderr = stderr
        mock.return_value = mock_return
        return mock
    return _mock_subprocess_run

@pytest.fixture
def create_dummy_config(temp_dir):
    def _create_config(filename, content):
        path = temp_dir / filename
        path.write_text(content)
        return path
    return _create_config
