#!/usr/bin/env python3
"""HAP Token Sync Broker — 从 152 拉取 token 写入本地。

不自行刷新，只从 152 同步。152 是唯一 token 来源。
启动时立即同步一次，之后每 check_interval_hours 小时同步一次。

用法:
  python3 sync_broker.py
  python3 sync_broker.py --oneshot    # 同步一次即退出
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import config as cfg_mod  # noqa: E402
import storage  # noqa: E402

log = logging.getLogger("hap-token-sync-broker")

# 152 连接信息
SSH_HOST = "152.136.138.32"
SSH_USER = "ubuntu"
SSH_TOKEN_DIR = "/root/.local/share/hap-token-broker/tokens"


def _setup_logging() -> None:
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt, datefmt="%Y-%m-%dT%H:%M:%S")


def ssh_read_token(profile: str) -> dict | None:
    """通过 SSH 从 152 读取指定 profile 的 token JSON。"""
    remote_path = f"{SSH_TOKEN_DIR}/{profile}.json"
    cmd = [
        "ssh", "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        f"{SSH_USER}@{SSH_HOST}",
        "sudo", "cat", remote_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError) as e:
        log.error(f"[{profile}] SSH 失败: {e}")
        return None
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        log.error(f"[{profile}] SSH exit={proc.returncode}: {err[:200]}")
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        log.error(f"[{profile}] token JSON 解析失败: {e}")
        return None


def sync_one(profile: str, mirror_legacy: Path | None = None) -> bool:
    """从 152 同步一个 profile 的 token 到本地。"""
    data = ssh_read_token(profile)
    if data is None:
        return False
    try:
        record = storage.TokenRecord.from_json(data)
    except (KeyError, ValueError) as e:
        log.error(f"[{profile}] token 数据不完整: {e}")
        return False

    storage.write_atomic(record)
    if mirror_legacy is not None:
        try:
            storage.mirror_to_legacy(record, mirror_legacy)
        except Exception as e:
            log.warning(f"[{profile}] legacy mirror failed ({mirror_legacy}): {e}")

    log.info(
        f"[{profile}] synced ok, expires_at={record.expires_at.isoformat()}, "
        f"url={storage.redact_url(record.url)}"
        + (f", mirror={mirror_legacy}" if mirror_legacy else "")
    )
    return True


def sync_all(cfg: cfg_mod.Config) -> int:
    """同步所有 profile，返回成功数。"""
    ok = 0
    for name in cfg.profiles:
        legacy = cfg.mirror_to_legacy.get(name)
        if sync_one(name, legacy):
            ok += 1
    return ok


class SyncBroker:
    def __init__(self, cfg: cfg_mod.Config):
        self.cfg = cfg
        self._stop = threading.Event()

    def request_stop(self, *_):
        log.info("received stop signal")
        self._stop.set()

    def run_forever(self) -> int:
        interval_sec = self.cfg.check_interval_hours * 3600
        total = len(self.cfg.profiles)
        log.info(
            f"sync-broker started, source={SSH_USER}@{SSH_HOST}, "
            f"profiles={list(self.cfg.profiles.keys())}, "
            f"interval={self.cfg.check_interval_hours}h"
        )

        # 首次同步
        ok = sync_all(self.cfg)
        log.info(f"initial sync: {ok}/{total} succeeded")

        while not self._stop.is_set():
            self._stop.wait(timeout=interval_sec)
            if self._stop.is_set():
                break
            ok = sync_all(self.cfg)
            log.info(f"periodic sync: {ok}/{total} succeeded")

        log.info("sync-broker stopped")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="HAP Token Sync Broker")
    parser.add_argument("--config", type=str, default=None, help="配置文件路径")
    parser.add_argument("--oneshot", action="store_true", help="同步一次即退出")
    args = parser.parse_args()

    _setup_logging()

    try:
        cfg = cfg_mod.load_config(Path(args.config)) if args.config else cfg_mod.load_config()
    except cfg_mod.ConfigError as e:
        log.error(f"config error: {e}")
        return 2

    if args.oneshot:
        log.info("--oneshot mode: sync once")
        ok = sync_all(cfg)
        log.info(f"sync done: {ok}/{len(cfg.profiles)} succeeded")
        return 0 if ok > 0 else 3

    broker = SyncBroker(cfg)
    import signal
    signal.signal(signal.SIGTERM, broker.request_stop)
    signal.signal(signal.SIGINT, broker.request_stop)

    pid_file = Path.home() / ".local" / "share" / "hap-token-broker" / "broker.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    try:
        return broker.run_forever()
    finally:
        try:
            pid_file.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
