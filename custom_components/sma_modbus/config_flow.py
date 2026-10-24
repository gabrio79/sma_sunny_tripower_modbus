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
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL_FAST,
    CONF_SCAN_INTERVAL_SLOW,
    CONF_SLAVE_ID,
    CONF_STRINGS_LABEL,
    CONF_STRING_1_NAME,
    CONF_STRING_2_NAME,
    COUNT_STATUS,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL_FAST,
    DEFAULT_SCAN_INTERVAL_SLOW,
    DEFAULT_SLAVE_ID,
    DEFAULT_STRINGS_LABEL,
    DOMAIN,
    REG_STATUS,
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
            address=REG_STATUS,
            count=COUNT_STATUS,
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
                entry_data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_SLAVE_ID: slave_id,
                    CONF_NAME: name,
                    CONF_STRINGS_LABEL: strings_label,
                }
                if user_input.get(CONF_STRING_1_NAME):
                    entry_data[CONF_STRING_1_NAME] = user_input[CONF_STRING_1_NAME].strip()
                if user_input.get(CONF_STRING_2_NAME):
                    entry_data[CONF_STRING_2_NAME] = user_input[CONF_STRING_2_NAME].strip()
                return self.async_create_entry(
                    title=name,
                    data=entry_data,
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
                vol.Optional(CONF_STRING_1_NAME): cv.string,
                vol.Optional(CONF_STRING_2_NAME): cv.string,
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

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        """Initialize options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        entry = getattr(self, "config_entry", None) or self._entry
        if entry is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            # If strings_label, slave_id, or custom string names changed, also synchronize with entry.data
            updated_data = dict(entry.data)
            for k in (CONF_STRINGS_LABEL, CONF_SLAVE_ID, CONF_STRING_1_NAME, CONF_STRING_2_NAME):
                if k in user_input:
                    updated_data[k] = user_input[k]

            self.hass.config_entries.async_update_entry(
                entry, data=updated_data
            )
            return self.async_create_entry(title="", data=user_input)

        current_label = entry.data.get(
            CONF_STRINGS_LABEL, DEFAULT_STRINGS_LABEL
        )
        current_slave = entry.data.get(CONF_SLAVE_ID, DEFAULT_SLAVE_ID)
        current_str1 = entry.options.get(
            CONF_STRING_1_NAME, entry.data.get(CONF_STRING_1_NAME, "")
        )
        current_str2 = entry.options.get(
            CONF_STRING_2_NAME, entry.data.get(CONF_STRING_2_NAME, "")
        )
        current_fast = entry.options.get(
            CONF_SCAN_INTERVAL_FAST, DEFAULT_SCAN_INTERVAL_FAST
        )
        current_slow = entry.options.get(
            CONF_SCAN_INTERVAL_SLOW, DEFAULT_SCAN_INTERVAL_SLOW
        )

        schema_dict = {
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
        }

        if current_str1:
            schema_dict[vol.Optional(CONF_STRING_1_NAME, default=current_str1)] = cv.string
        else:
            schema_dict[vol.Optional(CONF_STRING_1_NAME)] = cv.string

        if current_str2:
            schema_dict[vol.Optional(CONF_STRING_2_NAME, default=current_str2)] = cv.string
        else:
            schema_dict[vol.Optional(CONF_STRING_2_NAME)] = cv.string

        schema_dict[vol.Optional(CONF_SCAN_INTERVAL_FAST, default=current_fast)] = cv.positive_int
        schema_dict[vol.Optional(CONF_SCAN_INTERVAL_SLOW, default=current_slow)] = cv.positive_int

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema_dict))
