"""DataUpdateCoordinator for SMA Sunny Tripower Modbus integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import struct
import time
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BLOCK_FAST_POWER_COUNT,
    BLOCK_FAST_POWER_START,
    BLOCK_FAST_PV2_COUNT,
    BLOCK_FAST_PV2_START,
    BLOCK_SLOW_STATUS_COUNT,
    BLOCK_SLOW_STATUS_START,
    BLOCK_SLOW_TEMP_COUNT,
    BLOCK_SLOW_TEMP_START,
    BLOCK_SLOW_YIELD_COUNT,
    BLOCK_SLOW_YIELD_START,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL_FAST,
    CONF_SCAN_INTERVAL_SLOW,
    CONF_SLAVE_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL_FAST,
    DEFAULT_SCAN_INTERVAL_SLOW,
    DEFAULT_SLAVE_ID,
    DOMAIN,
    KEY_DAILY_YIELD,
    KEY_GRID_POWER,
    KEY_PV_POWER_1,
    KEY_PV_POWER_2,
    KEY_STATUS,
    KEY_STATUS_CODE,
    KEY_TEMPERATURE,
    KEY_TOTAL_YIELD,
    SMA_S32_MAX,
    SMA_S32_NAN,
    SMA_S64_MAX,
    SMA_S64_NAN,
    STATUS_CODE_MAP,
    STATUS_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)


def decode_int32(registers: list[int]) -> int:
    """Decode two 16-bit registers as signed 32-bit big-endian integer."""
    raw = struct.pack(">2H", registers[0], registers[1])
    return struct.unpack(">i", raw)[0]


def decode_int64(registers: list[int]) -> int:
    """Decode four 16-bit registers as signed 64-bit big-endian integer."""
    raw = struct.pack(">4H", registers[0], registers[1], registers[2], registers[3])
    return struct.unpack(">q", raw)[0]


async def async_read_holding_registers(
    client: AsyncModbusTcpClient, address: int, count: int, slave_id: int
) -> list[int]:
    """Read holding registers handling pymodbus version compatibility (device_id, slave, unit)."""
    response = None
    for kwarg in ("device_id", "slave", "unit"):
        try:
            response = await client.read_holding_registers(
                address=address, count=count, **{kwarg: slave_id}
            )
            break
        except TypeError as err:
            if "unexpected keyword argument" in str(err):
                continue
            raise

    if response is None:
        try:
            response = await client.read_holding_registers(address=address, count=count)
        except Exception as err:
            raise ModbusException(
                f"Modbus call failed for address {address}: {err}"
            ) from err

    if response is None or response.isError():
        raise ModbusException(
            f"Modbus error reading {count} registers from address {address}: {response}"
        )

    if len(response.registers) < count:
        raise ModbusException(
            f"Incomplete read from address {address}: expected {count}, got {len(response.registers)}"
        )

    return response.registers


class SmaModbusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage polling SMA Sunny Tripower inverter via Modbus TCP."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.host: str = entry.data[CONF_HOST]
        self.port: int = entry.data.get(CONF_PORT, DEFAULT_PORT)
        self.slave_id: int = entry.data.get(CONF_SLAVE_ID, DEFAULT_SLAVE_ID)

        # Allow overriding intervals via options
        self.scan_interval_fast: int = entry.options.get(
            CONF_SCAN_INTERVAL_FAST, DEFAULT_SCAN_INTERVAL_FAST
        )
        self.scan_interval_slow: int = entry.options.get(
            CONF_SCAN_INTERVAL_SLOW, DEFAULT_SCAN_INTERVAL_SLOW
        )

        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{self.host}_{self.slave_id}",
            update_interval=timedelta(seconds=self.scan_interval_fast),
        )

        self._client: AsyncModbusTcpClient | None = None
        self._lock = asyncio.Lock()
        self._last_slow_update: float = 0.0
        self._cached_slow_data: dict[str, Any] = {}
        self._connection_lost_logged: bool = False

    async def _async_ensure_connected(self) -> AsyncModbusTcpClient:
        """Ensure client exists and is connected."""
        if self._client is None:
            self._client = AsyncModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=5.0,
            )

        if not self._client.connected:
            connected = await self._client.connect()
            if not connected:
                raise ModbusException(
                    f"TCP handshake failed with {self.host}:{self.port}"
                )

        return self._client

    async def _async_read_chunk(
        self, client: AsyncModbusTcpClient, address: int, count: int
    ) -> list[int]:
        """Read holding registers delegating to universal helper."""
        return await async_read_holding_registers(
            client=client, address=address, count=count, slave_id=self.slave_id
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all required registers using optimized chunking."""
        async with self._lock:
            try:
                client = await self._async_ensure_connected()
                data: dict[str, Any] = {}
                now = time.monotonic()

                # 1. READ SLOW REGISTERS (every 60s or on startup)
                need_slow_read = (
                    self._last_slow_update == 0.0
                    or (now - self._last_slow_update) >= self.scan_interval_slow
                )

                if need_slow_read:
                    # Status chunk (30201, count 2)
                    status_regs = await self._async_read_chunk(
                        client, BLOCK_SLOW_STATUS_START, BLOCK_SLOW_STATUS_COUNT
                    )
                    raw_status = decode_int32(status_regs)
                    self._cached_slow_data[KEY_STATUS_CODE] = raw_status
                    self._cached_slow_data[KEY_STATUS] = STATUS_CODE_MAP.get(
                        raw_status, STATUS_UNKNOWN
                    )

                    # Yield chunk (30513..30520, count 8)
                    yield_regs = await self._async_read_chunk(
                        client, BLOCK_SLOW_YIELD_START, BLOCK_SLOW_YIELD_COUNT
                    )
                    # Total Yield (regs 0..3)
                    raw_total_yield = decode_int64(yield_regs[0:4])
                    if (
                        raw_total_yield == SMA_S64_NAN
                        or raw_total_yield == SMA_S64_MAX
                        or raw_total_yield < 0
                    ):
                        self._cached_slow_data[KEY_TOTAL_YIELD] = None
                    else:
                        self._cached_slow_data[KEY_TOTAL_YIELD] = round(
                            raw_total_yield * 0.001
                        )

                    # Daily Yield (regs 4..7)
                    raw_daily_yield = decode_int64(yield_regs[4:8])
                    if (
                        raw_daily_yield == SMA_S64_NAN
                        or raw_daily_yield == SMA_S64_MAX
                        or raw_daily_yield < 0
                    ):
                        self._cached_slow_data[KEY_DAILY_YIELD] = None
                    else:
                        self._cached_slow_data[KEY_DAILY_YIELD] = round(
                            raw_daily_yield * 0.001, 1
                        )

                    # Temperature chunk (30953, count 2)
                    temp_regs = await self._async_read_chunk(
                        client, BLOCK_SLOW_TEMP_START, BLOCK_SLOW_TEMP_COUNT
                    )
                    raw_temp = decode_int32(temp_regs)
                    if (
                        raw_temp == SMA_S32_NAN
                        or raw_temp == SMA_S32_MAX
                    ):
                        self._cached_slow_data[KEY_TEMPERATURE] = None
                    else:
                        scaled_temp = round(raw_temp * 0.1, 1)
                        # Filter spurious readings < -100 °C as per spec
                        self._cached_slow_data[KEY_TEMPERATURE] = (
                            scaled_temp if scaled_temp > -100.0 else None
                        )

                    self._last_slow_update = now

                # 2. READ FAST REGISTERS (every 5s)
                # Block 1: 30773..30776 (count 4) covers PV Power 1 & Grid Power
                fast_power_regs = await self._async_read_chunk(
                    client, BLOCK_FAST_POWER_START, BLOCK_FAST_POWER_COUNT
                )

                # PV Power 1 (regs 0..1, addr 30773)
                raw_pv1 = decode_int32(fast_power_regs[0:2])
                data[KEY_PV_POWER_1] = (
                    0 if raw_pv1 == SMA_S32_NAN or raw_pv1 < 0 else raw_pv1
                )

                # Grid Power (regs 2..3, addr 30775)
                raw_grid = decode_int32(fast_power_regs[2:4])
                data[KEY_GRID_POWER] = (
                    0 if raw_grid == SMA_S32_NAN or raw_grid < 0 else raw_grid
                )

                # Block 2: 30961..30962 (count 2) covers PV Power 2
                fast_pv2_regs = await self._async_read_chunk(
                    client, BLOCK_FAST_PV2_START, BLOCK_FAST_PV2_COUNT
                )
                raw_pv2 = decode_int32(fast_pv2_regs[0:2])
                data[KEY_PV_POWER_2] = (
                    0 if raw_pv2 == SMA_S32_NAN or raw_pv2 < 0 else raw_pv2
                )

                # Merge cached slow data into current payload
                data.update(self._cached_slow_data)

                # Connection is healthy: log recovery if it was previously reported as down
                if self._connection_lost_logged:
                    _LOGGER.info(
                        "Communication re-established with SMA Inverter at %s:%s (slave %s)",
                        self.host,
                        self.port,
                        self.slave_id,
                    )
                    self._connection_lost_logged = False

                return data

            except (ModbusException, asyncio.TimeoutError, OSError) as err:
                # Force client reset so subsequent attempt performs a clean TCP handshake
                if self._client is not None:
                    try:
                        self._client.close()
                    except Exception:  # pylint: disable=broad-except
                        pass

                # Quiet log management during night standby
                if not self._connection_lost_logged:
                    _LOGGER.warning(
                        "Inverter unreachable at %s:%s (slave %s). "
                        "The device may be in night standby mode: %s",
                        self.host,
                        self.port,
                        self.slave_id,
                        err,
                    )
                    self._connection_lost_logged = True
                else:
                    _LOGGER.debug(
                        "Still unable to reach SMA Inverter at %s:%s: %s",
                        self.host,
                        self.port,
                        err,
                    )

                raise UpdateFailed(f"Inverter communication error: {err}") from err

    async def async_close(self) -> None:
        """Close modbus client connection gracefully."""
        async with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.debug("Error closing Modbus client: %s", err)
                self._client = None
