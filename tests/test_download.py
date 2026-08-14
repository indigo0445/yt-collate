"""Download service writes a flat dump named by video id."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from yt_collate.models.music import Artist, Track
from yt_collate.services.download import (
    DownloadJobQueue,
    DownloadService,
    default_download_dir,
    existing_download,
    safe_video_id,
)


def _song(video_id: str, *, title: str | None = None, is_video: bool = False) -> Track:
    return Track(
        video_id=video_id,
        title=title or video_id,
        artists=[Artist(name="A")],
        is_video=is_video,
    )


def _write_from_template(cmd: list[str], ext: str = "opus") -> subprocess.CompletedProcess[str]:
    out = cmd[cmd.index("-o") + 1]
    path = Path(out.replace("%(ext)s", ext))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio")
    return subprocess.CompletedProcess(cmd, 0, "", "")


def test_safe_video_id_strips_path_junk() -> None:
    assert safe_video_id("dQw4w9wgXcQ") == "dQw4w9wgXcQ"
    assert safe_video_id("../x") is None
    assert safe_video_id("abc/def") is None


def test_existing_download_ignores_partials_and_video(tmp_path: Path) -> None:
    (tmp_path / "vid.part").write_text("x")
    (tmp_path / "vid.mp4").write_bytes(b"video")
    assert existing_download(tmp_path, "vid") is None
    done = tmp_path / "vid.opus"
    done.write_bytes(b"ok")
    assert existing_download(tmp_path, "vid") == done


def test_download_skips_existing_and_names_by_id(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _write_from_template(cmd)

    svc = DownloadService(tmp_path, cookies=lambda: "/tmp/c.txt", run=run)
    first = svc.download_track(_song("aaaaaaaaaaa", title="One"))
    assert first.status == "ok"
    assert first.path == tmp_path / "aaaaaaaaaaa.opus"
    assert "--cookies" in calls[0]
    assert "/tmp/c.txt" in calls[0]
    assert "-x" in calls[0]
    assert "opus" in calls[0]
    assert "player_client=web_music" in " ".join(calls[0])
    second = svc.download_track(_song("aaaaaaaaaaa", title="One"))
    assert second.status == "skipped"
    assert len(calls) == 1


def test_video_download_omits_cookies(tmp_path: Path) -> None:
    cmds: list[list[str]] = []

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        cmds.append(cmd)
        return _write_from_template(cmd)

    svc = DownloadService(tmp_path, cookies=lambda: "/tmp/c.txt", run=run)
    result = svc.download_track(_song("bbbbbbbbbbb", is_video=True))
    assert result.status == "ok"
    assert "--cookies" not in cmds[0]
    assert "extractor-args" not in cmds[0]
    assert result.path == tmp_path / "bbbbbbbbbbb.opus"


def test_download_replaces_leftover_mp4(tmp_path: Path) -> None:
    leftover = tmp_path / "ccccccccccc.mp4"
    leftover.write_bytes(b"video")

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return _write_from_template(cmd)

    svc = DownloadService(tmp_path, run=run)
    result = svc.download_track(_song("ccccccccccc"))
    assert result.status == "ok"
    assert result.path == tmp_path / "ccccccccccc.opus"
    assert not leftover.exists()


def test_playlist_job_one_callback(tmp_path: Path) -> None:
    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return _write_from_template(cmd)

    svc = DownloadService(tmp_path, run=run)
    jobs = DownloadJobQueue(svc)
    done = threading.Event()
    progress: list[tuple[int, int]] = []
    results = []

    try:
        jobs.enqueue(
            [_song("ccccccccccc"), _song("ddddddddddd")],
            collection="Chill Mix",
            on_progress=lambda c, t: progress.append((c, t)),
            on_done=lambda result: (results.append(result), done.set()),
        )
        assert done.wait(timeout=2)
        assert len(results) == 1
        batch = results[0]
        assert batch.collection == "Chill Mix"
        assert batch.ok == 2
        assert len(batch.items) == 2
        assert progress == [(1, 2), (2, 2)]
    finally:
        jobs.shutdown()


def test_song_jobs_callback_per_track(tmp_path: Path) -> None:
    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return _write_from_template(cmd)

    svc = DownloadService(tmp_path, run=run)
    jobs = DownloadJobQueue(svc)
    done = threading.Event()
    results = []

    try:
        jobs.enqueue(
            [_song("eeeeeeeeeee", title="Solo")],
            on_done=lambda result: (results.append(result), done.set()),
        )
        assert done.wait(timeout=2)
        assert len(results) == 1
        assert results[0].collection is None
        assert results[0].items[0].track.title == "Solo"
    finally:
        jobs.shutdown()


def test_migrates_legacy_download_dir(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    legacy = home / "Music" / "ymlite"
    legacy.mkdir(parents=True)
    (legacy / "aaaaaaaaaaa.opus").write_bytes(b"ok")
    monkeypatch.setenv("HOME", str(home))
    dest = default_download_dir()
    assert dest == home / "Music" / "yt-collate"
    assert (dest / "aaaaaaaaaaa.opus").exists()
    assert not legacy.exists()
