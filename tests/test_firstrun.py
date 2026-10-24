import sys
from app import firstrun, paths


def _frozen(monkeypatch, exe_dir, local):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "RemotePCControl.exe"))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(firstrun, "_new_token", None)


def test_source_run_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    firstrun.prepare()
    assert not (tmp_path / ".env").exists()
    assert paths.data_dir() == tmp_path
    assert firstrun.already_running(8888) is False


def test_first_start_of_exe_creates_env_with_token(tmp_path, monkeypatch):
    exe, local = tmp_path / "exe", tmp_path / "local"
    exe.mkdir()
    _frozen(monkeypatch, exe, local)
    firstrun.prepare()
    env = local / "RemotePCControl" / ".env"
    text = env.read_text()
    token = firstrun._new_token
    assert len(token) >= 40 and f"REMOTE_PC_TOKEN={token}" in text and "REMOTE_PC_HOST=0.0.0.0" in text
    firstrun.prepare()   # second start keeps the same token
    assert env.read_text() == text


def test_existing_env_next_to_exe_is_kept(tmp_path, monkeypatch):
    exe, local = tmp_path / "exe", tmp_path / "local"
    exe.mkdir()
    (exe / ".env").write_text("REMOTE_PC_TOKEN=old-install-token\n")
    _frozen(monkeypatch, exe, local)
    firstrun.prepare()
    assert paths.data_dir() == exe.resolve()
    assert firstrun._new_token is None and not local.exists()
