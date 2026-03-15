import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from tg_gemini.config import GeminiConfig
from tg_gemini.events import ErrorEvent, GeminiEvent, parse_event


@dataclass(frozen=True)
class SessionInfo:
    index: int
    title: str
    time: str
    session_id: str


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
        self, prompt: str, session_id: str | None = None, model: str | None = None
    ) -> AsyncIterator[GeminiEvent]:
        args = self._build_args(prompt, session_id, model)
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.config.working_dir,
            )
        except FileNotFoundError:
            yield ErrorEvent(severity="error", message="gemini CLI not found in PATH")
            return

        if proc.stdout:
            async for line in proc.stdout:
                event = self._parse_line(line.decode())
                if event:
                    yield event

        await proc.wait()

        if proc.returncode != 0:
            stderr = (await proc.stderr.read()).decode().strip() if proc.stderr else ""
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
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    async def list_sessions(self) -> list[SessionInfo]:
        """List available sessions for the project."""
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
            return proc.returncode == 0
