import os

import pytest

from fitbit_report.private_storage import ensure_private_directory, write_private_text


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits only")
def test_private_storage_uses_owner_only_permissions(tmp_path):
    directory = ensure_private_directory(tmp_path / "private")
    path = write_private_text(directory / "secret.txt", "secret")

    assert directory.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits only")
def test_private_storage_tightens_existing_file_permissions(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    path = directory / "secret.txt"
    path.write_text("old", encoding="utf-8")
    path.chmod(0o666)

    write_private_text(path, "new")

    assert directory.stat().st_mode & 0o777 == 0o755
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.read_text(encoding="utf-8") == "new"


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits only")
def test_private_file_does_not_change_existing_parent_policy(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)

    path = write_private_text(shared / "token.json", "secret")

    assert shared.stat().st_mode & 0o777 == 0o755
    assert path.stat().st_mode & 0o777 == 0o600
