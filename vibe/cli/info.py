from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time
from typing import Any

from vibe import __version__
from vibe.core.types import LLMUsage


def _safe_getattr(obj: Any, attr: str) -> Any:
    """Safely get attribute from Pydantic model, returning None if not set or doesn't exist."""
    try:
        value = getattr(obj, attr, None)
        # Handle Pydantic's Unset object
        if hasattr(value, '__class__') and value.__class__.__name__ == 'Unset':
            return None
        return value
    except Exception:
        return None


class InfoData:
    """Data class to hold execution metrics for JSON output."""

    def __init__(self) -> None:
        self.provider: str | None = None
        self.model: str | None = None
        self.wall_time_ms: float | None = None
        self.ttft_ms: float | None = None
        self.input_tokens: int | None = None
        self.cache_creation_input_tokens: int | None = None
        self.cache_read_input_tokens: int | None = None
        self.effective_input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.total_cost_usd: float | None = None
        self.stdout_bytes: int = 0
        self.exit_code: int = 0
        self.timestamp: str | None = None
        self.version: str = __version__

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "provider": self.provider,
            "model": self.model,
            "wall_time_ms": self.wall_time_ms,
            "ttft_ms": self.ttft_ms,
            "input_tokens": self.input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "effective_input_tokens": self.effective_input_tokens,
            "output_tokens": self.output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "stdout_bytes": self.stdout_bytes,
            "exit_code": self.exit_code,
            "timestamp": self.timestamp,
            "version": self.version,
        }

    def compute_effective_input_tokens(self) -> None:
        """Compute effective_input_tokens if required values are available."""
        if self.input_tokens is not None:
            # Use cache tokens if available, treat None as 0 for computation
            cache_creation = self.cache_creation_input_tokens or 0
            cache_read = self.cache_read_input_tokens or 0
            
            if cache_creation > 0 or cache_read > 0:
                # Only compute effective_input_tokens if we have some cache information
                self.effective_input_tokens = self.input_tokens + cache_creation + cache_read
            else:
                # No cache tokens available, return None
                self.effective_input_tokens = None
        else:
            self.effective_input_tokens = None



class StdoutCaptureStream:
    """A file-like object that captures stdout and counts bytes."""

    def __init__(self, original_stdout: Any) -> None:
        self.original_stdout = original_stdout
        self.captured_bytes: int = 0

    def write(self, text: str) -> int:
        """Write text and capture byte count."""
        if text:
            byte_count = len(text.encode("utf-8"))
            self.captured_bytes += byte_count
        return self.original_stdout.write(text)

    def flush(self) -> None:
        """Flush the underlying stream."""
        self.original_stdout.flush()

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attributes to the original stdout."""
        return getattr(self.original_stdout, name)


class InfoCollector:
    """Collects execution metrics for the --info feature."""

    def __init__(self) -> None:
        self.data = InfoData()
        self._start_time: float | None = None
        self._first_token_time: float | None = None
        self._request_sent_time: float | None = None
        self._stdout_stream: StdoutCaptureStream | None = None
        self._original_stdout: Any = None
        self._total_llm_usage = LLMUsage(prompt_tokens=0, completion_tokens=0)
        self._provider: str | None = None
        self._model: str | None = None

    def start(self) -> None:
        """Start collecting metrics."""
        self._start_time = time.perf_counter()
        self.data.timestamp = datetime.now(UTC).isoformat()
        # Start capturing stdout
        self._original_stdout = sys.stdout
        self._stdout_stream = StdoutCaptureStream(self._original_stdout)
        sys.stdout = self._stdout_stream

    def stop_capturing_stdout(self) -> None:
        """Stop capturing stdout and restore original."""
        if self._stdout_stream is not None:
            self.data.stdout_bytes = self._stdout_stream.captured_bytes
            sys.stdout = self._original_stdout
            self._stdout_stream = None
            self._original_stdout = None

    def set_provider_info(self, provider: str, model: str) -> None:
        """Set provider and model information."""
        self._provider = provider
        self._model = model
        self.data.provider = provider
        self.data.model = model

    def record_request_sent(self) -> None:
        """Record when the LLM request was sent."""
        self._request_sent_time = time.perf_counter()

    def record_first_token(self) -> None:
        """Record when the first token was received."""
        if self._request_sent_time is not None:
            self._first_token_time = time.perf_counter()

    def record_llm_usage(self, usage: LLMUsage | None) -> None:
        """Record LLM usage metrics."""
        if usage is not None:
            self._total_llm_usage += usage

    def record_cost(self, cost_usd: float | None) -> None:
        """Record the total cost in USD."""
        if cost_usd is not None:
            self.data.total_cost_usd = cost_usd



    def set_exit_code(self, code: int) -> None:
        """Set the exit code."""
        self.data.exit_code = code

    def finalize(self) -> None:
        """Finalize metrics collection and compute derived values."""
        # Stop capturing stdout first
        self.stop_capturing_stdout()

        if self._start_time is not None:
            end_time = time.perf_counter()
            self.data.wall_time_ms = (end_time - self._start_time) * 1000

        # Compute TTFT if available
        if (
            self._request_sent_time is not None
            and self._first_token_time is not None
        ):
            self.data.ttft_ms = (
                (self._first_token_time - self._request_sent_time) * 1000
            )
        else:
            self.data.ttft_ms = None

        # Set provider and model if not already set
        if self._provider and self._model:
            self.data.provider = self._provider
            self.data.model = self._model

        # Set token counts from total usage
        self.data.input_tokens = self._total_llm_usage.prompt_tokens
        self.data.output_tokens = self._total_llm_usage.completion_tokens

        # Set cache token counts from usage if available
        self.data.cache_creation_input_tokens = self._total_llm_usage.cache_creation_input_tokens
        self.data.cache_read_input_tokens = self._total_llm_usage.cache_read_input_tokens
        
        # For providers like Mistral that only provide num_cached_tokens (total cached tokens)
        # but not separate creation/read breakdown, we'll use num_cached_tokens as cache_read_input_tokens
        # This is a reasonable approximation since most cached tokens are typically from cache reads
        if (
            self.data.cache_creation_input_tokens is None
            and self.data.cache_read_input_tokens is None
            and self._total_llm_usage.num_cached_tokens is not None
        ):
            # Use num_cached_tokens as cache_read_input_tokens when no separate breakdown is available
            self.data.cache_read_input_tokens = self._total_llm_usage.num_cached_tokens
        
        # Also try to extract cached tokens from prompt_token_details if available
        if (
            self.data.cache_creation_input_tokens is None
            and self.data.cache_read_input_tokens is None
            and self._total_llm_usage.prompt_token_details is not None
        ):
            # Try to extract cached tokens from prompt_token_details
            cached_tokens = _safe_getattr(self._total_llm_usage.prompt_token_details, 'cached_tokens')
            if cached_tokens is not None:
                self.data.cache_read_input_tokens = cached_tokens

        # Compute effective input tokens
        self.data.compute_effective_input_tokens()
        
        # Set additional metrics if available from usage
        if self._total_llm_usage.total_tokens is not None:
            # total_tokens might be the sum of all tokens, but we'll keep our computed values
            pass

    def write_json(self, path: str | Path | None = None) -> None:
        """Write the collected metrics to a JSON file or print to stderr."""
        json_data = self.data.to_dict()
        json_str = json.dumps(json_data, indent=2)
        
        if path is None:
            # Print to stderr to avoid mixing with normal stdout
            print(json_str, file=sys.stderr)
        else:
            path = Path(path)
            with path.open("w", encoding="utf-8") as f:
                f.write(json_str)


class InfoCollectorContext:
    """Context manager for info collection."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.collector: InfoCollector | None = None

    def __enter__(self) -> InfoCollectorContext:
        if self.enabled:
            self.collector = InfoCollector()
            self.collector.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.collector is not None:
            # Set exit code based on exception
            if exc_type is not None:
                self.collector.set_exit_code(1)
            else:
                self.collector.set_exit_code(0)
            self.collector.finalize()
            self.collector.write_json()