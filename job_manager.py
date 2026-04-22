"""Job manager — async queue for nesting jobs with progress broadcasting."""
import asyncio
from typing import Dict, Optional
from models.schemas import NestConfig, NestResult


class JobManager:
    """Manages nesting job lifecycle: enqueue, run, cancel, broadcast progress."""

    def __init__(self):
        self._jobs: Dict[str, dict] = {}
        self._queue: asyncio.Queue = asyncio.Queue()

    async def start_job(self, job_id: str, config: NestConfig) -> None:
        """Enqueue a new nesting job."""
        self._jobs[job_id] = {"status": "queued", "config": config, "result": None}
        await self._queue.put(job_id)

    async def cancel_job(self, job_id: str) -> None:
        """Cancel a running job."""
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = "cancelled"

    def get_status(self, job_id: str) -> Optional[dict]:
        """Get current job status."""
        return self._jobs.get(job_id)


job_manager = JobManager()
