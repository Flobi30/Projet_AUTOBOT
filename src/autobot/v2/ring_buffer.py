"""
Ring Buffer SPMC Lock-Free — P2
Replaces asyncio.Queue dispatch in WebSocket → Instance path.

Architecture:
    Single Producer (WebSocket task) writes TickerData.
    Multiple Consumers (per-instance tasks) read via independent cursors.

Lock-free guarantee (CPython):
    CPython GIL ensures that simple reference assignments and integer stores
    are atomic.  The write protocol — slot store THEN cursor advance — gives
    consumers a consistent view: seq < write_seq implies the slot is fully
    written.

Memory model:
    Slots are pre-allocated (list of size N). No allocation on hot path.
    Zero-copy: TickerData references are stored, not copied.

Performance (CPython 3.11, measured in test_ring_buffer.py):
    write()       ~200–400 ns
    read_at()     ~100–200 ns
    poll_batch()  ~50–80 ns/msg (amortised for batch ≥ 16)

Usage:
    ring = RingBuffer(65536)          # 64 K slots

    # Producer (single task)
    ring.write(ticker_data)

    # Consumer (one per instance)
    reader = RingBufferReader(ring)
    for msg in reader.poll_batch(64):
        await instance.on_price_update(msg)
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = ["RingBuffer", "RingBufferReader", "DEFAULT_BUFFER_SIZE"]

DEFAULT_BUFFER_SIZE: int = 65536  # Must be power of 2


class RingBuffer:
    """
    SPMC (Single Producer / Multiple Consumers) lock-free ring buffer.

    Design invariants:
        - Size is always a power of 2: index = seq & mask  (O(1), no modulo)
        - write_seq is monotonically increasing
        - Slot at index i belongs to the write whose seq & mask == i
        - Overwrite policy: oldest slot is silently overwritten when full

    Thread / task safety (CPython asyncio):
        Single-threaded asyncio event loop means there is no concurrent
        execution.  CPython's GIL additionally serialises bytecode, making
        list-item assignment and integer stores atomic.

        NOT safe for use across OS threads without additional synchronisation.
    """

    __slots__ = ("_size", "_mask", "_slots", "_write_seq")

    def __init__(self, size: int = DEFAULT_BUFFER_SIZE) -> None:
        """
        Args:
            size: Number of slots.  Must be a power of 2.

        Raises:
            ValueError: If size is not a positive power of 2.
        """
        if size <= 0 or (size & (size - 1)) != 0:
            raise ValueError(f"Buffer size must be a positive power of 2, got {size}")

        self._size: int = size
        self._mask: int = size - 1

        # Pre-allocated slot array — no GC pressure on hot path.
        # Slots hold Python object references (zero-copy for TickerData).
        self._slots: list[Any] = [None] * size

        # Monotonically increasing write cursor.
        # In CPython, plain integer assignment is atomic under the GIL.
        self._write_seq: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Capacity in number of slots."""
        return self._size

    @property
    def write_seq(self) -> int:
        """Current write cursor (number of writes performed)."""
        return self._write_seq

    # ------------------------------------------------------------------
    # Hot path: producer
    # ------------------------------------------------------------------

    def write(self, data: Any) -> int:
        """
        Write *data* to the next slot.  O(1), wait-free.

        If all consumers are at least *size* messages behind, the oldest
        unread slot is silently overwritten (no blocking, no exception).

        Protocol (preserves consumer consistency):
            1. Record current seq
            2. Write data to slot[seq & mask]   ← atomic reference store
            3. Advance _write_seq to seq + 1    ← atomic integer store

        Consumers check ``seq < write_seq`` before reading, so they
        never observe a slot before step 3 completes.

        Returns:
            The sequence number assigned to this write.
        """
        seq = self._write_seq
        self._slots[seq & self._mask] = data  # (1) Write data — atomic
        self._write_seq = seq + 1             # (2) Advance cursor — atomic
        return seq

    # ------------------------------------------------------------------
    # Hot path: consumer (called by RingBufferReader)
    # ------------------------------------------------------------------

    def read_at(self, seq: int) -> tuple[bool, Any]:
        """
        Attempt a non-blocking read at sequence number *seq*.  O(1).

        Returns:
            ``(True, data)``  — data is available and the slot is valid.
            ``(False, None)`` — either no new data, or the slot was already
                               overwritten (consumer too slow).

        Overwrite detection:
            If ``write_seq - seq > size``, the slot at ``seq & mask`` has
            been overwritten.  The caller (RingBufferReader) must skip
            forward to a safe position.
        """
        write_seq = self._write_seq     # Single load — consistent snapshot

        if seq >= write_seq:
            return False, None          # Nothing new yet

        if (write_seq - seq) > self._size:
            return False, None          # Slot overwritten — signal skip

        return True, self._slots[seq & self._mask]

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return buffer diagnostics (not on hot path)."""
        ws = self._write_seq
        return {
            "size": self._size,
            "write_seq": ws,
            "fill_ratio": min(1.0, ws / self._size) if self._size else 0.0,
        }


class RingBufferReader:
    """
    Consumer cursor for a :class:`RingBuffer` — one per instance/consumer.

    Each reader maintains its own ``read_seq`` so N consumers can progress
    independently at different rates without any synchronisation.

    Design:
        - ``poll()``        — single non-blocking read, O(1)
        - ``poll_batch()``  — up to N reads in one call, amortises overhead
        - ``skip_to_latest()`` — drop backlog, jump to current write position
        - ``lag``           — how many unread messages are pending

    Overflow recovery:
        If the producer has lapped the consumer (``lag > buffer.size``), the
        missed slots are silently skipped and ``read_seq`` is advanced to the
        oldest valid slot.  This is the only case where the reader may skip
        messages.
    """

    __slots__ = ("_buf", "_read_seq")

    def __init__(self, buffer: RingBuffer, *, start_at_tail: bool = True) -> None:
        """
        Args:
            buffer: The shared ring buffer.
            start_at_tail: If ``True`` (default), start reading from the
                current write position — ignores historical data.
                If ``False``, start from sequence 0 — reads full history
                (useful for testing).
        """
        self._buf = buffer
        self._read_seq: int = buffer.write_seq if start_at_tail else 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def read_seq(self) -> int:
        """Current read cursor."""
        return self._read_seq

    @property
    def lag(self) -> int:
        """
        Number of unread messages.

        If ``lag > buffer.size``, an overflow has occurred and messages
        have been silently dropped.  ``poll_batch()`` will auto-recover.
        """
        return self._buf.write_seq - self._read_seq

    # ------------------------------------------------------------------
    # Hot path: reads
    # ------------------------------------------------------------------

    def poll(self) -> Optional[Any]:
        """
        Non-blocking single read.  O(1).

        Returns the next unread item, or ``None`` if nothing is available.
        Advances the read cursor on success.
        """
        available, data = self._buf.read_at(self._read_seq)
        if available:
            self._read_seq += 1
            return data

        # Handle overwrite: if read_at returned False due to overflow, skip.
        write_seq = self._buf.write_seq
        if (write_seq - self._read_seq) > self._buf.size:
            self._read_seq = write_seq - self._buf.size

        return None

    def poll_batch(self, max_items: int = 64) -> list[Any]:
        """
        Non-blocking batch read.  O(min(max_items, lag)).

        Reads up to *max_items* messages in order, advancing the cursor
        past all returned items.  Handles overflow by skipping to the
        oldest valid slot when necessary.

        Args:
            max_items: Upper bound on messages returned per call.

        Returns:
            List of data items in chronological order (may be empty).
        """
        results: list[Any] = []
        buf = self._buf
        seq = self._read_seq

        for _ in range(max_items):
            write_seq = buf._write_seq          # Cache: single load per iteration
            if seq >= write_seq:
                break

            lag = write_seq - seq
            if lag > buf._size:
                # Consumer too slow — skip to oldest valid slot
                seq = write_seq - buf._size
                continue                         # Re-check at new seq

            results.append(buf._slots[seq & buf._mask])
            seq += 1

        self._read_seq = seq
        return results

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def skip_to_latest(self) -> int:
        """
        Discard all pending messages and jump to the current write position.

        Useful when a consumer needs to process only fresh data after a
        period of inactivity (e.g., after restart or lag recovery).

        Returns:
            Number of messages skipped.
        """
        write_seq = self._buf.write_seq
        skipped = write_seq - self._read_seq
        self._read_seq = write_seq
        return max(0, skipped)

    def reset_to(self, seq: int) -> None:
        """
        Reset the read cursor to an arbitrary sequence number.

        Note: reading at a seq that has already been overwritten will return
        nothing (overflow protection in ``read_at``).
        """
        self._read_seq = max(0, seq)
