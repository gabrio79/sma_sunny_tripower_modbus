"""Constants for the SMA Sunny Tripower Modbus integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "sma_modbus"

# Configuration and options keys
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_SLAVE_ID: Final = "slave_id"
CONF_NAME: Final = "name"
CONF_STRINGS_LABEL: Final = "strings_label"
CONF_SCAN_INTERVAL_FAST: Final = "scan_interval_fast"
CONF_SCAN_INTERVAL_SLOW: Final = "scan_interval_slow"

# Default values
DEFAULT_PORT: Final = 502
DEFAULT_SLAVE_ID: Final = 3
DEFAULT_NAME: Final = "SMA Sunny Tripower"
DEFAULT_STRINGS_LABEL: Final = "ab"
DEFAULT_SCAN_INTERVAL_FAST: Final = 5
DEFAULT_SCAN_INTERVAL_SLOW: Final = 60

# String selection options
STRINGS_LABEL_AB: Final = "ab"
STRINGS_LABEL_CD: Final = "cd"
STRINGS_LABEL_OPTIONS: Final = [STRINGS_LABEL_AB, STRINGS_LABEL_CD]

# Data keys for coordinator storage
KEY_STATUS: Final = "status"
KEY_STATUS_CODE: Final = "status_code"
KEY_GRID_POWER: Final = "grid_power"
KEY_PV_POWER_1: Final = "pv_power_1"
KEY_PV_POWER_2: Final = "pv_power_2"
KEY_DAILY_YIELD: Final = "daily_yield"
KEY_TOTAL_YIELD: Final = "total_yield"
KEY_TEMPERATURE: Final = "temperature"

# Inverter operating status
STATUS_OK: Final = "ok"
STATUS_OFF: Final = "off"
STATUS_WARNING: Final = "warning"
STATUS_ERROR: Final = "error"
STATUS_UNKNOWN: Final = "unknown"

STATUS_CODE_MAP: Final[dict[int, str]] = {
    307: STATUS_OK,
    303: STATUS_OFF,
    455: STATUS_WARNING,
    35: STATUS_ERROR,
}

# Modbus register addresses
# Slow cycle (default: 60s)
REG_STATUS: Final = 30201  # int32 (2 registers)
REG_TOTAL_YIELD: Final = 30513  # int64 (4 registers)
REG_DAILY_YIELD: Final = 30517  # int64 (4 registers)
REG_TEMPERATURE: Final = 30953  # int32 (2 registers)

# Fast cycle (default: 5s)
REG_PV_POWER_1: Final = 30773  # int32 (2 registers)
REG_GRID_POWER: Final = 30775  # int32 (2 registers)
REG_PV_POWER_2: Final = 30961  # int32 (2 registers)

# Contiguous block definitions for optimized chunked reads
# Fast block 1: 30773..30776 (count 4) covers PV Power 1 and Grid Power
BLOCK_FAST_POWER_START: Final = REG_PV_POWER_1
BLOCK_FAST_POWER_COUNT: Final = 4

# Fast block 2: 30961..30962 (count 2) covers PV Power 2
BLOCK_FAST_PV2_START: Final = REG_PV_POWER_2
BLOCK_FAST_PV2_COUNT: Final = 2

# Slow block Status: 30201..30202 (count 2)
BLOCK_SLOW_STATUS_START: Final = REG_STATUS
BLOCK_SLOW_STATUS_COUNT: Final = 2

# Slow block Yield: 30513..30520 (count 8) covers Total Yield and Daily Yield
BLOCK_SLOW_YIELD_START: Final = REG_TOTAL_YIELD
BLOCK_SLOW_YIELD_COUNT: Final = 8

# Slow block Temperature: 30953..30954 (count 2)
BLOCK_SLOW_TEMP_START: Final = REG_TEMPERATURE
BLOCK_SLOW_TEMP_COUNT: Final = 2

# SMA sentinel and NaN values
SMA_S32_NAN: Final = -2147483648  # 0x80000000
SMA_S32_MAX: Final = 2147483647  # 0x7FFFFFFF
SMA_S64_NAN: Final = -9223372036854775808  # 0x8000000000000000
SMA_S64_MAX: Final = 9223372036854775807  # 0x7FFFFFFFFFFFFFFF
