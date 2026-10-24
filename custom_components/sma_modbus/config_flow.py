"""Config flow for SMA Sunny Tripower Modbus integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    BLOCK_SLOW_STATUS_COUNT,
    BLOCK_SLOW_STATUS_START,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL_FAST,
    CONF_SCAN_INTERVAL_SLOW,
    CONF_SLAVE_ID,
    CONF_STRINGS_LABEL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL_FAST,
    DEFAULT_SCAN_INTERVAL_SLOW,
    DEFAULT_SLAVE_ID,
    DEFAULT_STRINGS_LABEL,
    DOMAIN,
    STRINGS_LABEL_AB,
    STRINGS_LABEL_CD,
    STRINGS_LABEL_OPTIONS,
)
from .coordinator import async_read_holding_registers

_LOGGER = logging.getLogger(__name__)


async def validate_connection(
    host: str, port: int, slave_id: int
) -> tuple[bool, str | None]:
    """Validate that we can connect to the SMA Inverter and read status register."""
    client = AsyncModbusTcpClient(host=host, port=port, timeout=5.0)
    try:
        connected = await client.connect()
        if not connected:
            return False, "cannot_connect"

        # Attempt to read status register (30201) using universal pymodbus helper
        await async_read_holding_registers(
            client=client,
            address=BLOCK_SLOW_STATUS_START,
            count=BLOCK_SLOW_STATUS_COUNT,
            slave_id=slave_id,
        )
        return True, None

    except (asyncio.TimeoutError, OSError):
        return False, "cannot_connect"
    except ModbusException:
        return False, "invalid_response"
    except Exception as exc:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected error validating connection: %s", exc)
        return False, "unknown"
    finally:
        try:
            client.close()
        except Exception:  # pylint: disable=broad-except
            pass


class SmaModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SMA Sunny Tripower Modbus."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            slave_id = user_input[CONF_SLAVE_ID]
            name = user_input.get(CONF_NAME, DEFAULT_NAME).strip()
            strings_label = user_input.get(CONF_STRINGS_LABEL, DEFAULT_STRINGS_LABEL)

            unique_id = f"{host}_{port}_{slave_id}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            success, error_code = await validate_connection(host, port, slave_id)
            if success:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_SLAVE_ID: slave_id,
                        CONF_NAME: name,
                        CONF_STRINGS_LABEL: strings_label,
                    },
                )

            if error_code:
                errors["base"] = error_code

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID): cv.positive_int,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(
                    CONF_STRINGS_LABEL, default=DEFAULT_STRINGS_LABEL
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=STRINGS_LABEL_OPTIONS,
                        translation_key="strings_label",
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return SmaModbusOptionsFlowHandler(config_entry)


class SmaModbusOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for SMA Sunny Tripower Modbus integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # If strings_label or slave_id changed, also synchronize with entry.data
            updated_data = dict(self.config_entry.data)
            if CONF_STRINGS_LABEL in user_input:
                updated_data[CONF_STRINGS_LABEL] = user_input[CONF_STRINGS_LABEL]
            if CONF_SLAVE_ID in user_input:
                updated_data[CONF_SLAVE_ID] = user_input[CONF_SLAVE_ID]

            self.hass.config_entries.async_update_entry(
                self.config_entry, data=updated_data
            )
            return self.async_create_entry(title="", data=user_input)

        current_label = self.config_entry.data.get(
            CONF_STRINGS_LABEL, DEFAULT_STRINGS_LABEL
        )
        current_slave = self.config_entry.data.get(CONF_SLAVE_ID, DEFAULT_SLAVE_ID)
        current_fast = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_FAST, DEFAULT_SCAN_INTERVAL_FAST
        )
        current_slow = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_SLOW, DEFAULT_SCAN_INTERVAL_SLOW
        )

        schema = vol.Schema(
            {
                vol.Optional(CONF_SLAVE_ID, default=current_slave): cv.positive_int,
                vol.Optional(
                    CONF_STRINGS_LABEL, default=current_label
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=STRINGS_LABEL_OPTIONS,
                        translation_key="strings_label",
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL_FAST, default=current_fast
                ): cv.positive_int,
                vol.Optional(
                    CONF_SCAN_INTERVAL_SLOW, default=current_slow
                ): cv.positive_int,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
