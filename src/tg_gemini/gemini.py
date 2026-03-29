import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

import structlog

from tg_gemini.config import GeminiConfig
from tg_gemini.events import ErrorEvent, GeminiEvent, parse_event

logger = structlog.get_logger()


@dataclass(frozen=True)
class SessionInfo:
    index: int
    title: str
    time: str
    session_id: str


STREAM_BUFFER_LIMIT = 10 * 1024 * 1024  # 10MB for large tool outputs


class GeminiAgent:
    def __init__(self, config: GeminiConfig) -> None:
        self.config = config

    def _build_args(
        self, prompt: str, session_id: str | None = None, model: str | None = None
    ) -> list[str]:
        args = [
            "gemini",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "-m",
            model or self.config.model,
            "--approval-mode",
            self.config.approval_mode,
        ]
        if session_id:
            args.extend(["-r", session_id])
        return args

    async def run_stream(
        self,
        prompt: str,
        session_id: str | None = None,
        model: str | None = None,
        stop_event: asyncio.Event | None = None,
    ) -> AsyncIterator[GeminiEvent]:
        args = self._build_args(prompt, session_id, model)
        logger.debug("gemini_cli_exec", command=" ".join(args))
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=STREAM_BUFFER_LIMIT,
                cwd=self.config.working_dir,
            )
        except FileNotFoundError:
            logger.exception("gemini_cli_not_found")
            yield ErrorEvent(severity="error", message="gemini CLI not found in PATH")
            return

        if proc.stdout:
            while True:
                if stop_event is not None and stop_event.is_set():
                    logger.info("gemini_stream_stopped_by_user")
                    proc.terminate()
                    yield ErrorEvent(severity="info", message="⏹ Stopped by user.")
                    break

                # readline with timeout so we can check stop_event periodically
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=0.5)
                except TimeoutError:
                    continue

                if not line:
                    break
                event = self._parse_line(line.decode())
                if event:
                    yield event

        await proc.wait()

        if proc.returncode != 0:
            stderr = (await proc.stderr.read()).decode().strip() if proc.stderr else ""
            logger.error("gemini_cli_exit", returncode=proc.returncode, stderr=stderr)
            yield ErrorEvent(
                severity="error", message=f"gemini exited with code {proc.returncode}. {stderr}"
            )

    def _parse_line(self, line: str) -> GeminiEvent | None:
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
            return parse_event(data)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug("gemini_parse_error", line=line, error=str(e))
            return None

    async def list_sessions(self) -> list[SessionInfo]:
        """List available sessions for the project."""
        logger.debug("list_sessions_start")
        try:
            proc = await asyncio.create_subprocess_exec(
                "gemini",
                "--list-sessions",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.config.working_dir,
            )
            stdout, _ = await proc.communicate()
        except FileNotFoundError:
            return []
        else:
            if proc.returncode != 0:
                return []

            output = stdout.decode()
            sessions = []
            # Pattern: 1. Title (Time) [UUID]
            pattern = re.compile(r"^\s*(\d+)\.\s+(.*?)\s+\(([^)]+)\)\s+\[([^\]]+)\]$")
            for line in output.splitlines():
                match = pattern.match(line)
                if match:
                    sessions.append(
                        SessionInfo(
                            index=int(match.group(1)),
                            title=match.group(2),
                            time=match.group(3),
                            session_id=match.group(4),
                        )
                    )
            return sessions

    async def delete_session(self, session_id_or_index: str) -> bool:
        """Delete a session by ID or index."""
        logger.info("delete_session", session_id=session_id_or_index)
        try:
            proc = await asyncio.create_subprocess_exec(
                "gemini",
                "--delete-session",
                session_id_or_index,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.config.working_dir,
            )
            await proc.wait()
        except FileNotFoundError:
            return False
        else:
            logger.debug(
                "delete_session_done", success=proc.returncode == 0, returncode=proc.returncode
            )
            return proc.returncode == 0
