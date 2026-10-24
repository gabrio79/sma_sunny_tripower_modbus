"""Sensor platform for SMA Sunny Tripower Modbus integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    CONF_STRINGS_LABEL,
    CONF_STRING_1_NAME,
    CONF_STRING_2_NAME,
    DEFAULT_STRINGS_LABEL,
    DOMAIN,
    KEY_DAILY_YIELD,
    KEY_GRID_POWER,
    KEY_PV_POWER_1,
    KEY_PV_POWER_2,
    KEY_STATUS,
    KEY_STATUS_CODE,
    KEY_TEMPERATURE,
    KEY_TOTAL_YIELD,
    STATUS_ERROR,
    STATUS_OFF,
    STATUS_OK,
    STATUS_UNKNOWN,
    STATUS_WARNING,
    STRINGS_LABEL_CD,
)
from .coordinator import SmaModbusCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SMA Sunny Tripower sensors based on a config entry."""
    coordinator: SmaModbusCoordinator = getattr(entry, "runtime_data", None)
    if coordinator is None:
        coordinator = hass.data[DOMAIN][entry.entry_id]

    strings_label = entry.data.get(CONF_STRINGS_LABEL, DEFAULT_STRINGS_LABEL)

    # Determine dynamic keys for MPPT strings (e.g. pv_power_c / pv_power_d or pv_power_a / pv_power_b)
    if strings_label == STRINGS_LABEL_CD:
        pv_1_key = "pv_power_c"
        pv_2_key = "pv_power_d"
    else:
        pv_1_key = "pv_power_a"
        pv_2_key = "pv_power_b"

    descriptions: tuple[SensorEntityDescription, ...] = (
        SensorEntityDescription(
            key=KEY_STATUS,
            translation_key="status",
            icon="mdi:information-outline",
            device_class=SensorDeviceClass.ENUM,
            options=[
                STATUS_OK,
                STATUS_OFF,
                STATUS_WARNING,
                STATUS_ERROR,
                STATUS_UNKNOWN,
            ],
        ),
        SensorEntityDescription(
            key=KEY_STATUS_CODE,
            translation_key="status_wip",
            icon="mdi:numeric",
            entity_registry_enabled_default=True,
        ),
        SensorEntityDescription(
            key=KEY_GRID_POWER,
            translation_key="grid_power",
            icon="mdi:solar-power",
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfPower.WATT,
        ),
        SensorEntityDescription(
            key=KEY_PV_POWER_1,
            translation_key=pv_1_key,
            icon="mdi:solar-power",
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfPower.WATT,
        ),
        SensorEntityDescription(
            key=KEY_PV_POWER_2,
            translation_key=pv_2_key,
            icon="mdi:solar-power",
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfPower.WATT,
        ),
        SensorEntityDescription(
            key=KEY_DAILY_YIELD,
            translation_key="daily_yield",
            icon="mdi:solar-power-variant",
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            suggested_display_precision=1,
        ),
        SensorEntityDescription(
            key=KEY_TOTAL_YIELD,
            translation_key="total_yield",
            icon="mdi:solar-power-variant-outline",
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            suggested_display_precision=0,
        ),
        SensorEntityDescription(
            key=KEY_TEMPERATURE,
            translation_key="temperature",
            icon="mdi:thermometer",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            suggested_display_precision=1,
        ),
    )

    # Compute device slug (e.g. "Inverter 1" -> "inverter_1", "SMA Inverter 1" -> "inverter_1")
    device_slug = slugify(entry.title)
    if device_slug.startswith("sma_inverter_"):
        device_slug = device_slug.replace("sma_", "")
    elif device_slug.startswith("sma_"):
        device_slug = device_slug.replace("sma_", "")

    key_to_suffix = {
        KEY_STATUS: "status",
        KEY_STATUS_CODE: "status_wip",
        KEY_GRID_POWER: "grid_power",
        KEY_PV_POWER_1: pv_1_key,
        KEY_PV_POWER_2: pv_2_key,
        KEY_DAILY_YIELD: "daily_yield",
        KEY_TOTAL_YIELD: "total_yield",
        KEY_TEMPERATURE: "temperature",
    }

    # Entity registry migration for backwards compatibility and yaml file consistency
    ent_reg = er.async_get(hass)
    for desc in descriptions:
        target_entity_id = f"sensor.{device_slug}_{key_to_suffix[desc.key]}"
        unique_id = f"{entry.entry_id}_{desc.key}"
        current_entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
        if current_entity_id and current_entity_id != target_entity_id:
            if ent_reg.async_get(target_entity_id) is None:
                _LOGGER.info(
                    "Migrating entity_id from %s to %s (unique_id: %s)",
                    current_entity_id,
                    target_entity_id,
                    unique_id,
                )
                ent_reg.async_update_entity(current_entity_id, new_entity_id=target_entity_id)

    async_add_entities(
        SmaModbusSensor(
            coordinator=coordinator,
            description=description,
            entry=entry,
            entity_id=f"sensor.{device_slug}_{key_to_suffix[description.key]}",
        )
        for description in descriptions
    )


class SmaModbusSensor(CoordinatorEntity[SmaModbusCoordinator], SensorEntity):
    """Representation of an SMA Sunny Tripower Modbus sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmaModbusCoordinator,
        description: SensorEntityDescription,
        entry: ConfigEntry,
        entity_id: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self.entry = entry
        if entity_id:
            self.entity_id = entity_id

        # Stable unique identifier per sensor entity
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        # Group all sensors under one device entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="SMA",
            model="Sunny Tripower",
        )

        # Custom name override for MPPT strings if configured
        custom_name = None
        if description.key == KEY_PV_POWER_1:
            custom_name = entry.options.get(CONF_STRING_1_NAME) or entry.data.get(CONF_STRING_1_NAME)
        elif description.key == KEY_PV_POWER_2:
            custom_name = entry.options.get(CONF_STRING_2_NAME) or entry.data.get(CONF_STRING_2_NAME)

        if custom_name:
            self._attr_name = custom_name

    @property
    def native_value(self) -> Any:
        """Return the native value from coordinator data."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes if applicable."""
        if self.entity_description.key == KEY_STATUS and self.coordinator.data:
            status_code = self.coordinator.data.get(KEY_STATUS_CODE)
            if status_code is not None:
                return {KEY_STATUS_CODE: status_code}
        return None
