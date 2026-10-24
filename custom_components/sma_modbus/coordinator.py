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


async def _async_try_read(
    client: AsyncModbusTcpClient,
    method,
    address: int,
    count: int,
    slave_id: int,
) -> list[int] | None:
    """Attempt reading with a given method across all pymodbus keyword arguments."""
    for kwarg in ("device_id", "slave", "unit"):
        try:
            resp = await method(address=address, count=count, **{kwarg: slave_id})
            if resp is not None:
                if resp.isError():
                    _LOGGER.warning(
                        "SMA Inverter %s returned Modbus exception on address %s (%s=%s): %s",
                        client.host,
                        address,
                        kwarg,
                        slave_id,
                        resp,
                    )
                    return None
                if hasattr(resp, "registers") and len(resp.registers) >= count:
                    return resp.registers
        except TypeError as err:
            if "unexpected keyword argument" in str(err):
                continue
            _LOGGER.warning(
                "TypeError reading address %s on %s (%s=%s): %s",
                address,
                client.host,
                kwarg,
                slave_id,
                err,
            )
        except (asyncio.TimeoutError, OSError):
            raise
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Communication error reading address %s on %s (%s=%s): %s",
                address,
                client.host,
                kwarg,
                slave_id,
                err,
            )
            raise
    return None


async def async_read_holding_registers(
    client: AsyncModbusTcpClient, address: int, count: int, slave_id: int
) -> list[int]:
    """Read registers using holding (FC03), with fallback to input (FC04)."""
    # 1. Try FC03 (read_holding_registers) at address
    regs = await _async_try_read(
        client, client.read_holding_registers, address, count, slave_id
    )
    if regs is not None:
        return regs

    # 2. Try FC04 (read_input_registers) at address
    regs = await _async_try_read(
        client, client.read_input_registers, address, count, slave_id
    )
    if regs is not None:
        return regs

    raise ModbusException(
        f"Unable to read {count} registers from address {address} (slave {slave_id}) with FC03 or FC04"
    )


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
        self._first_data_logged: bool = False

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
                self._client = None
                raise ModbusException(
                    f"TCP handshake failed with {self.host}:{self.port}"
                )

        return self._client

    async def _async_read_channel(
        self, client: AsyncModbusTcpClient, address: int, count: int
    ) -> list[int] | None:
        """Read an individual Modbus data object safely."""
        try:
            regs = await async_read_holding_registers(
                client=client, address=address, count=count, slave_id=self.slave_id
            )
            _LOGGER.debug(
                "SMA Inverter %s:%s - Read %s regs from %s: %s",
                self.host,
                self.slave_id,
                count,
                address,
                regs,
            )
            return regs
        except (asyncio.TimeoutError, OSError):
            raise
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning(
                "SMA Inverter %s:%s - Failed reading %s registers from address %s: %s",
                self.host,
                self.slave_id,
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
                success_count = 0

                # 1. SLOW CYCLE (every 60s or on startup)
                need_slow_read = (
                    self._last_slow_update == 0.0
                    or (now - self._last_slow_update) >= self.scan_interval_slow
                )

                if need_slow_read:
                    # Status (30201, count 2, S32)
                    status_regs = await self._async_read_channel(
                        client, REG_STATUS, COUNT_STATUS
                    )
                    if status_regs is not None:
                        success_count += 1
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
                        success_count += 1
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
                        success_count += 1
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
                        success_count += 1
                        raw_temp = decode_int32(temp_regs)
                        if raw_temp in (SMA_S32_NAN, SMA_S32_MAX):
                            self._cached_slow_data[KEY_TEMPERATURE] = None
                        else:
                            scaled_temp = round(raw_temp * 0.1, 1)
                            self._cached_slow_data[KEY_TEMPERATURE] = (
                                scaled_temp if scaled_temp > -100.0 else None
                            )

                    if success_count > 0:
                        self._last_slow_update = now

                # 2. FAST CYCLE (every 5s)
                # PV Power 1 (30773, count 2, S32)
                pv1_regs = await self._async_read_channel(
                    client, REG_PV_POWER_1, COUNT_PV_POWER_1
                )
                if pv1_regs is not None:
                    success_count += 1
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
                    success_count += 1
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
                    success_count += 1
                    raw_pv2 = decode_int32(pv2_regs)
                    data[KEY_PV_POWER_2] = (
                        0 if raw_pv2 in (SMA_S32_NAN, SMA_S32_MAX) or raw_pv2 < 0 else raw_pv2
                    )
                else:
                    data[KEY_PV_POWER_2] = 0

                # If no registers could be read at all, force socket cleanup
                if success_count == 0 and not need_slow_read and not self._cached_slow_data:
                    if self._client is not None:
                        try:
                            self._client.close()
                        except Exception:
                            pass
                        self._client = None
                    raise UpdateFailed(
                        f"Nessun dato ricevuto dall'inverter SMA ({self.host}:{self.port}, slave {self.slave_id})"
                    )

                # Merge cached slow data into payload
                data.update(self._cached_slow_data)

                # Log first successful read as visible notice in logs
                if not self._first_data_logged and success_count > 0:
                    _LOGGER.warning(
                        "SMA Inverter %s connesso! Telemetria: Rete=%s W, FV1=%s W, FV2=%s W, Stato=%s, Resa Oggi=%s kWh, Totale=%s kWh, Temp=%s °C",
                        self.host,
                        data.get(KEY_GRID_POWER),
                        data.get(KEY_PV_POWER_1),
                        data.get(KEY_PV_POWER_2),
                        data.get(KEY_STATUS),
                        data.get(KEY_DAILY_YIELD),
                        data.get(KEY_TOTAL_YIELD),
                        data.get(KEY_TEMPERATURE),
                    )
                    self._first_data_logged = True

                # Reset communication lost warning flag upon success
                if self._connection_lost_logged:
                    _LOGGER.warning(
                        "Comunicazione ripristinata con l'inverter SMA %s:%s (slave %s)",
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
                    self._client = None

                if not self._connection_lost_logged:
                    _LOGGER.warning(
                        "Inverter irraggiungibile all'indirizzo %s:%s (slave %s): %s",
                        self.host,
                        self.port,
                        self.slave_id,
                        err,
                    )
                    self._connection_lost_logged = True

                raise UpdateFailed(f"Errore comunicazione inverter SMA: {err}") from err

    async def async_close(self) -> None:
        """Close modbus client connection gracefully."""
        async with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.debug("Error closing Modbus client: %s", err)
                self._client = None
