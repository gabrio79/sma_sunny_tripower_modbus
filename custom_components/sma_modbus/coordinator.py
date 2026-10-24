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
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL_FAST,
    CONF_SCAN_INTERVAL_SLOW,
    CONF_SLAVE_ID,
    COUNT_DAILY_YIELD,
    COUNT_GRID_POWER,
    COUNT_PV_POWER_1,
    COUNT_PV_POWER_2,
    COUNT_STATUS,
    COUNT_TEMPERATURE,
    COUNT_TOTAL_YIELD,
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
    REG_DAILY_YIELD,
    REG_GRID_POWER,
    REG_PV_POWER_1,
    REG_PV_POWER_2,
    REG_STATUS,
    REG_TEMPERATURE,
    REG_TOTAL_YIELD,
    SMA_S32_MAX,
    SMA_S32_NAN,
    STATUS_CODE_MAP,
    STATUS_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)


def decode_int32(registers: list[int]) -> int:
    """Decode two 16-bit registers as signed 32-bit big-endian integer."""
    raw = struct.pack(">2H", registers[0], registers[1])
    return struct.unpack(">i", raw)[0]


def decode_uint64(registers: list[int]) -> int:
    """Decode four 16-bit registers as unsigned 64-bit big-endian integer."""
    raw = struct.pack(">4H", registers[0], registers[1], registers[2], registers[3])
    return struct.unpack(">Q", raw)[0]


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

    async def _async_read_channel(
        self, client: AsyncModbusTcpClient, address: int, count: int
    ) -> list[int] | None:
        """Read an individual Modbus data object safely."""
        try:
            return await async_read_holding_registers(
                client=client, address=address, count=count, slave_id=self.slave_id
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug(
                "Error reading %s registers from address %s: %s",
                count,
                address,
                err,
            )
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all required registers from SMA Inverter."""
        async with self._lock:
            try:
                client = await self._async_ensure_connected()
                data: dict[str, Any] = {}
                now = time.monotonic()

                # Verify inverter basic responsiveness first (reading Status register)
                status_regs = await async_read_holding_registers(
                    client=client,
                    address=REG_STATUS,
                    count=COUNT_STATUS,
                    slave_id=self.slave_id,
                )

                # 1. SLOW CYCLE (every 60s or on startup)
                need_slow_read = (
                    self._last_slow_update == 0.0
                    or (now - self._last_slow_update) >= self.scan_interval_slow
                )

                if need_slow_read:
                    # Status (30201, count 2)
                    raw_status = decode_int32(status_regs)
                    self._cached_slow_data[KEY_STATUS_CODE] = raw_status
                    self._cached_slow_data[KEY_STATUS] = STATUS_CODE_MAP.get(
                        raw_status, STATUS_UNKNOWN
                    )

                    # Total Yield (30513, count 4, U64)
                    total_yield_regs = await self._async_read_channel(
                        client, REG_TOTAL_YIELD, COUNT_TOTAL_YIELD
                    )
                    if total_yield_regs is not None:
                        raw_total = decode_uint64(total_yield_regs)
                        if raw_total in (0xFFFFFFFFFFFFFFFF, 0x8000000000000000):
                            self._cached_slow_data[KEY_TOTAL_YIELD] = None
                        else:
                            self._cached_slow_data[KEY_TOTAL_YIELD] = round(
                                raw_total * 0.001
                            )

                    # Daily Yield (30517, count 4, U64)
                    daily_yield_regs = await self._async_read_channel(
                        client, REG_DAILY_YIELD, COUNT_DAILY_YIELD
                    )
                    if daily_yield_regs is not None:
                        raw_daily = decode_uint64(daily_yield_regs)
                        if raw_daily in (0xFFFFFFFFFFFFFFFF, 0x8000000000000000):
                            self._cached_slow_data[KEY_DAILY_YIELD] = None
                        else:
                            self._cached_slow_data[KEY_DAILY_YIELD] = round(
                                raw_daily * 0.001, 1
                            )

                    # Temperature (30953, count 2, S32)
                    temp_regs = await self._async_read_channel(
                        client, REG_TEMPERATURE, COUNT_TEMPERATURE
                    )
                    if temp_regs is not None:
                        raw_temp = decode_int32(temp_regs)
                        if raw_temp in (SMA_S32_NAN, SMA_S32_MAX):
                            self._cached_slow_data[KEY_TEMPERATURE] = None
                        else:
                            scaled_temp = round(raw_temp * 0.1, 1)
                            self._cached_slow_data[KEY_TEMPERATURE] = (
                                scaled_temp if scaled_temp > -100.0 else None
                            )

                    self._last_slow_update = now

                # 2. FAST CYCLE (every 5s)
                # PV Power 1 (30773, count 2, S32)
                pv1_regs = await self._async_read_channel(
                    client, REG_PV_POWER_1, COUNT_PV_POWER_1
                )
                if pv1_regs is not None:
                    raw_pv1 = decode_int32(pv1_regs)
                    data[KEY_PV_POWER_1] = (
                        0 if raw_pv1 in (SMA_S32_NAN, SMA_S32_MAX) or raw_pv1 < 0 else raw_pv1
                    )
                else:
                    data[KEY_PV_POWER_1] = 0

                # Grid Power (30775, count 2, S32)
                grid_regs = await self._async_read_channel(
                    client, REG_GRID_POWER, COUNT_GRID_POWER
                )
                if grid_regs is not None:
                    raw_grid = decode_int32(grid_regs)
                    data[KEY_GRID_POWER] = (
                        0 if raw_grid in (SMA_S32_NAN, SMA_S32_MAX) or raw_grid < 0 else raw_grid
                    )
                else:
                    data[KEY_GRID_POWER] = 0

                # PV Power 2 (30961, count 2, S32)
                pv2_regs = await self._async_read_channel(
                    client, REG_PV_POWER_2, COUNT_PV_POWER_2
                )
                if pv2_regs is not None:
                    raw_pv2 = decode_int32(pv2_regs)
                    data[KEY_PV_POWER_2] = (
                        0 if raw_pv2 in (SMA_S32_NAN, SMA_S32_MAX) or raw_pv2 < 0 else raw_pv2
                    )
                else:
                    data[KEY_PV_POWER_2] = 0

                # Merge cached slow data into payload
                data.update(self._cached_slow_data)

                # Reset communication lost warning flag upon success
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
                if self._client is not None:
                    try:
                        self._client.close()
                    except Exception:  # pylint: disable=broad-except
                        pass

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
