from __future__ import annotations

import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .protocol import (
    ActionSpace,
    Handshake,
    Message,
    ProtocolError,
    StepResult,
    decode_reset_result,
    decode_step_result,
    encode_reset,
    encode_step,
)
from .transport import expect_message, receive_frame, send_error, send_frame


@dataclass(frozen=True)
class WorkerPaths:
    log: Path
    csv: Path


class UnityWorker:
    def __init__(
        self,
        worker_id: int,
        executable: Path,
        paths: WorkerPaths,
        *,
        time_scale: float = 20,
        action_space: ActionSpace = ActionSpace.DISCRETE,
        max_duration: float = 300,
        startup_timeout: float = 180,
        nographics: bool = True,
        expected_handshake_worker_id: int | None = None,
        expected_handshake_action_space: ActionSpace | None = None,
    ):
        self.worker_id = worker_id
        self.executable = executable.resolve()
        self.paths = paths
        self.time_scale = float(time_scale)
        self.action_space = action_space
        self.max_duration = float(max_duration)
        self.startup_timeout = startup_timeout
        self.nographics = nographics
        self.expected_handshake_worker_id = expected_handshake_worker_id
        self.expected_handshake_action_space = expected_handshake_action_space
        self.listener: socket.socket | None = None
        self.socket: socket.socket | None = None
        self.process: subprocess.Popen | None = None
        self.handshake: Handshake | None = None
        self.pending_step = False
        self.last_exit_code: int | None = None

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.process else None

    def start(self) -> None:
        if not self.executable.is_file():
            raise FileNotFoundError(f"Research Worker build is missing: {self.executable}")
        self.paths.log.parent.mkdir(parents=True, exist_ok=True)
        self.paths.csv.parent.mkdir(parents=True, exist_ok=True)
        if self.paths.log.exists() or self.paths.csv.exists():
            raise FileExistsError(f"Worker {self.worker_id} requires unused log and CSV paths")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(self.startup_timeout)
        self.listener = listener
        port = listener.getsockname()[1]
        command = [
            str(self.executable),
            "-batchmode",
            "-logFile", str(self.paths.log.resolve()),
        ]
        if self.nographics:
            command.append("-nographics")
        command.extend([
            "--research-worker",
            "--worker-id", str(self.worker_id),
            "--bridge-host", "127.0.0.1",
            "--bridge-port", str(port),
            "--time-scale", format(self.time_scale, "g"),
            "--action-space", self.action_space.name.title(),
            "--max-duration", format(self.max_duration, "g"),
            "--unity-csv", str(self.paths.csv.resolve()),
        ])
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=creationflags)
        try:
            connection, _ = listener.accept()
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            connection.settimeout(120)
            self.socket = connection
            payload = receive_frame(connection)
            handshake = Handshake.decode(payload)
            try:
                expected_id = self.worker_id if self.expected_handshake_worker_id is None else self.expected_handshake_worker_id
                expected_action_space = self.action_space if self.expected_handshake_action_space is None else self.expected_handshake_action_space
                handshake.validate(expected_id, expected_action_space)
            except Exception as exc:
                send_error(connection, str(exc))
                raise
            self.handshake = handshake
            send_frame(connection, bytes((Message.HELLO_ACCEPTED,)))
        except Exception:
            self.terminate()
            raise
        finally:
            listener.close()
            self.listener = None

    def reset(self, seed: int):
        self._ensure_alive()
        if self.pending_step:
            raise RuntimeError("Cannot RESET while a STEP result is pending")
        send_frame(self.socket, encode_reset(seed))
        return decode_reset_result(receive_frame(self.socket))

    def send_step(self, action: int | float) -> None:
        self._ensure_alive()
        if self.pending_step:
            raise RuntimeError("A STEP is already pending")
        send_frame(self.socket, encode_step(action, self.action_space))
        self.pending_step = True

    def receive_step(self) -> StepResult:
        self._ensure_alive()
        if not self.pending_step:
            raise RuntimeError("No STEP is pending")
        try:
            result = decode_step_result(receive_frame(self.socket))
        finally:
            self.pending_step = False
        return result

    def _ensure_alive(self) -> None:
        if self.socket is None or self.process is None:
            raise RuntimeError(f"Worker {self.worker_id} has not started")
        code = self.process.poll()
        if code is not None:
            raise ChildProcessError(f"Unity worker {self.worker_id} exited with code {code}; log: {self.paths.log}")

    def close(self, timeout: float = 15) -> None:
        if self.process is None:
            return
        acknowledged = False
        try:
            if self.socket is not None and self.process.poll() is None and not self.pending_step:
                send_frame(self.socket, bytes((Message.CLOSE,)))
                expect_message(receive_frame(self.socket), Message.CLOSE_ACCEPTED)
                acknowledged = True
        except (OSError, ConnectionError, ProtocolError, TimeoutError):
            pass
        finally:
            if self.socket is not None:
                try:
                    self.socket.close()
                except OSError:
                    pass
                self.socket = None
            try:
                code = self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
                code = self.process.wait(timeout=5)
            self.last_exit_code = code
            self.process = None
            if code != 0 or not acknowledged:
                raise ChildProcessError(
                    f"Unity worker {self.worker_id} close failed (ack={acknowledged}, exit={code}); log: {self.paths.log}"
                )

    def disconnect(self) -> None:
        if self.socket is not None:
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()
            self.socket = None

    def terminate(self) -> None:
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass
            self.listener = None
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            try:
                self.last_exit_code = self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            self.process = None


def start_workers(
    count: int,
    executable: Path,
    run_dir: Path,
    *,
    time_scale: float,
    max_duration: float = 300,
    nographics: bool = True,
    action_space: ActionSpace = ActionSpace.DISCRETE,
) -> list[UnityWorker]:
    workers: list[UnityWorker] = []
    try:
        for worker_id in range(count):
            worker = UnityWorker(
                worker_id,
                executable,
                WorkerPaths(
                    run_dir / "worker_logs" / f"worker-{worker_id}.log",
                    run_dir / "unity_episode_csv" / f"worker-{worker_id}.csv",
                ),
                time_scale=time_scale,
                action_space=action_space,
                max_duration=max_duration,
                nographics=nographics,
            )
            worker.start()
            workers.append(worker)
        return workers
    except Exception:
        for worker in workers:
            worker.terminate()
        raise


def close_workers(workers: list[UnityWorker]) -> None:
    errors: list[Exception] = []
    for worker in workers:
        try:
            worker.close()
        except Exception as exc:
            errors.append(exc)
            worker.terminate()
    if errors:
        raise RuntimeError("One or more workers did not close cleanly") from errors[0]
