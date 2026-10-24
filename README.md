# SMA Sunny Tripower Modbus - Custom Component per Home Assistant

Integrazione personalizzata (HACS compliant) per **Home Assistant** per monitorare inverter fotovoltaici **SMA Sunny Tripower** tramite **Modbus TCP** asincrono (`pymodbus`).

Questa integrazione sostituisce completamente la vecchia configurazione YAML frammentata (basata su letture registro per registro e molteplici template sensor `_wip`), garantendo:
- **Interfaccia grafica (UI / Config Flow)** per aggiungere e gestire facilmente più inverter.
- **Raggruppamento per Dispositivo (Device Registry)**: ogni inverter possiede la propria scheda dispositivo con produttore "SMA" e modello "Sunny Tripower".
- **DataUpdateCoordinator asincrono con Chunking**: letture aggregate di registri contigui (riduzione drastica del carico sulla scheda di rete dell'inverter).
- **Polling differenziato**: ciclo rapido (default 5s) per la potenza istantanea e ciclo lento (default 60s) per energia, stato e temperatura.
- **Normalizzazione in-memory e Standby Notturno Silenzioso**: gestione nativa dei valori sentinella SMA (valori negativi / `0x80000000` mappati a 0 W) e soppressione del log spam quando l'inverter va in standby notturno.
- **Supporto multilingua nativo (IT / EN)**: conformità con `_attr_has_entity_name = True`, `translation_key` e sensore stato con `SensorDeviceClass.ENUM`.

---

## 📁 Struttura dell'integrazione

```
custom_components/sma_modbus/
├── __init__.py               # Inizializzazione del componente e gestione del ciclo di vita
├── config_flow.py          # Flusso di configurazione e opzioni tramite UI (con validazione TCP)
├── const.py                # Costanti, indirizzi registri, costanti di blocco e mapping
├── coordinator.py          # DataUpdateCoordinator, chunking modbus e decodifica dati
├── manifest.json           # Metadati dell'integrazione HACS e dipendenze
├── sensor.py               # Definizione dichiarativa entità sensore
├── strings.json            # Stringhe di base (inglese)
├── translations/
│   ├── en.json             # Traduzione in lingua inglese
│   └── it.json             # Traduzione completa in lingua italiana
└── hacs.json               # Compatibilità HACS
```

---

## ⚡ Registri Modbus Mappati

| Registro | Tipo | Precisione / Scala | Unità | Polling | Descrizione |
|---|---|---|---|---|---|
| **30201** | int32 | — | — | 60s | Stato operativo inverter (`ok`, `off`, `warning`, `error`, `unknown`) |
| **30513** | int64 | x0.001 (prec. 0) | kWh | 60s | Total Yield (Energia totale prodotta) |
| **30517** | int64 | x0.001 (prec. 1) | kWh | 60s | Daily Yield (Energia giornaliera prodotta) |
| **30953** | int32 | x0.1 (prec. 1) | °C | 60s | Temperatura interna inverter (filtro < -100 °C) |
| **30773** | int32 | min 0 | W | 5s | Potenza MPPT 1 (Stringa A o Stringa C) |
| **30775** | int32 | min 0 | W | 5s | Potenza di rete erogata (Grid Power) |
| **30961** | int32 | min 0 | W | 5s | Potenza MPPT 2 (Stringa B o Stringa D) |

---

## 🚀 Installazione

### Metodo 1: Tramite HACS (Consigliato)
1. Apri **HACS** in Home Assistant.
2. Clicca sui 3 puntini in alto a destra -> **Repository personalizzati**.
3. Incolla l'URL del repository GitHub e seleziona la categoria **Integrazione**.
4. Clicca su **Scarica** e riavvia Home Assistant.

### Metodo 2: Installazione Manuale
1. Copia la cartella `custom_components/sma_modbus/` all'interno della directory `config/custom_components/` della tua installazione di Home Assistant.
2. Riavvia Home Assistant.

---

## ⚙️ Configurazione da Interfaccia Utente

1. Vai su **Impostazioni** -> **Dispositivi e servizi** -> **Aggiungi integrazione**.
2. Cerca **SMA Sunny Tripower Modbus**.
3. Compila i campi:
   - **Indirizzo IP / Host**: es. `192.168.50.11`
   - **Porta TCP**: `502`
   - **ID Slave Modbus**: `3` (default per SMA)
   - **Nome Inverter**: es. `Inverter 1` (o `Inverter 2`)
   - **Etichette Stringhe MPPT**:
     - Seleziona **Stringhe C / D** per l'inverter 1
     - Seleziona **Stringhe A / B** per l'inverter 2
4. Clicca su **Invia**. L'integrazione effettuerà un test di connessione immediato e creerà il dispositivo con tutte le entità.

---

## 🔄 Migrazione del file `sma_inverter_common.yaml`

Dopo aver rimosso i vecchi `sma_inverter_1.yaml` e `sma_inverter_2.yaml`, aggiorna `sma_inverter_common.yaml` come segue (non servono più i sensori `_wip`):

```yaml
template:
  - sensor:
      # Potenza Fotovoltaico Complessiva
      - name: "Fotovoltaico Potenza"
        unique_id: fotovoltaico_potenza
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
        icon: mdi:solar-power
        state: >
          {{
            (
              (states('sensor.inverter_1_grid_power') | float(0)) +
              (states('sensor.inverter_2_grid_power') | float(0))
            ) | round(2)
          }}

      # Energia Fotovoltaico Giornaliera Complessiva
      - name: "Produzione Fotovoltaico Giornaliera"
        unique_id: produzione_fotovoltaico_giornaliera
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total_increasing
        icon: mdi:solar-power-variant
        state: >
          {{
            (
              (states('sensor.inverter_1_daily_yield') | float(0)) +
              (states('sensor.inverter_2_daily_yield') | float(0))
            ) | round(2)
          }}

      # Energia Fotovoltaico Totale Complessiva
      - name: "Fotovoltaico Total Energy"
        unique_id: fotovoltaico_energia_totale
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total_increasing
        icon: mdi:solar-power-variant-outline
        state: >
          {{
            (
              (states('sensor.inverter_1_total_yield') | float(0)) +
              (states('sensor.inverter_2_total_yield') | float(0))
            ) | round(2)
          }}

automation:
  - alias: "ALLARME - Inverter in stato anomalo"
    id: "inverter_stato_anomalo"
    mode: single
    triggers:
      - trigger: template
        value_template: >
          {{ states('sensor.inverter_1_status') not in ['ok', 'unknown', 'unavailable'] }}
        for: "00:00:30"
        id: inverter_1_anomalo
      - trigger: template
        value_template: >
          {{ states('sensor.inverter_2_status') not in ['ok', 'unknown', 'unavailable'] }}
        for: "00:00:30"
        id: inverter_2_anomalo
    actions:
      - action: notify.send_message
        target:
          entity_id:
            - notify.telegram_user_1
            - notify.telegram_user_2
        data:
          title: "⚠️ Allarme Inverter"
          message: >
            {% if trigger.id == 'inverter_1_anomalo' %}
              Inverter 1 in stato anomalo: {{ states('sensor.inverter_1_status') }}
              Status code: {{ state_attr('sensor.inverter_1_status', 'status_code') }}
            {% else %}
              Inverter 2 in stato anomalo: {{ states('sensor.inverter_2_status') }}
              Status code: {{ state_attr('sensor.inverter_2_status', 'status_code') }}
            {% endif %}
            
            Controlla il sistema fotovoltaico!

  - alias: "ALLARME - Inverter non disponibile"
    id: "inverter_non_disponibile"
    description: "Avvisa se un inverter non è disponibile per più di 2 minuti durante il giorno"
    mode: single
    triggers:
      - trigger: state
        entity_id: sensor.inverter_1_status
        to: "unavailable"
        for:
          minutes: 2
        id: inverter_1_unavailable
      - trigger: state
        entity_id: sensor.inverter_2_status
        to: "unavailable"
        for:
          minutes: 2
        id: inverter_2_unavailable
    actions:
      - action: notify.send_message
        target:
          entity_id:
            - notify.telegram_user_1
        data:
          title: "⚠️ Allarme Inverter"
          message: >
            {% if trigger.id == 'inverter_1_unavailable' %}
              L'inverter 1 non è disponibile da oltre 2 minuti!
            {% else %}
              L'inverter 2 non è disponibile da oltre 2 minuti!
            {% endif %}
            
            Verifica la connessione Modbus TCP con l'inverter.
```
