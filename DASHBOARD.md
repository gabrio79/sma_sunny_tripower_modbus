# 📊 Custom Card All-in-One per SMA Sunny Tripower (`sma-tripower-card`)

Una scheda personalizzata Lovelace completa, moderna e reattiva con **tutto integrato**: grafica vettoriale nativa SVG dell'inverter SMA, flussi di energia animati in tempo reale, display LCD digitale, LED di stato e pannello telemetria completo.

Nessun file esterno da posizionare a mano o coordinate da configurare: basta aggiungere la card!

---

## ✨ Caratteristiche Principali

- 📐 **Schematica Vettoriale SVG Incorporata**: Disegno ad altissima risoluzione dell'inverter SMA Sunny Tripower, delle stringhe fotovoltaiche e della rete elettrica.
- ⚡ **Flussi Energetici Dinamici Animati**: Linee di flusso a particelle pulsanti che collegano le stringhe solari all'inverter e l'inverter alla rete. L'animazione accelera all'aumentare della potenza solare e si arresta in standby.
- 📟 **Display Digitale LCD & LED di Stato**: Display blu elettrico stile SMA con lettura istantanea e LED di stato circolare (Verde = Produzione, Arancione = Attesa/Standby, Rosso = Errore).
- 📈 **Griglia Telemetrica Completa**:
  - **Oggi**: Produzione giornaliera in kWh.
  - **Totale**: Produzione storica cumulativa (in kWh o MWh).
  - **Temperatura**: Temperatura interna del dissipatore (°C).
  - **Rendimento**: Rendimento inverter stimato.
- 🎛️ **Editor Visuale Integrato**: Configurazione guidata tramite l'interfaccia di Home Assistant (titolo, inverter 1 o 2, attivazione animazioni, visibilità header/statistiche).
- 🔄 **Risoluzione Automatica Entità**: Supporta istantaneamente sia `inverter_1` che `inverter_2` senza dover mappare ogni sensore a mano.

---

## 🚀 Come Aggiungere la Card in Lovelace

### Metodo 1: Risorsa Registrata Automaticamente dall'Integrazione
L'integrazione SMA Modbus registra automaticamente l'endpoint `/sma_modbus/sma-tripower-card.js`.

1. Apri la tua Dashboard in Home Assistant.
2. Clicca sui **3 puntini in alto a destra** ➔ **Modifica Dashboard**.
3. Clicca su **Aggiungi scheda** ➔ cerca **SMA Sunny Tripower Card** oppure scegli **Manuale** (YAML).
4. Inserisci il seguente codice:

```yaml
type: custom:sma-tripower-card
title: "Inverter 1 - SMA Sunny Tripower"
inverter: "inverter_1"
animation: true
```

Per il secondo inverter:
```yaml
type: custom:sma-tripower-card
title: "Inverter 2 - SMA Sunny Tripower"
inverter: "inverter_2"
animation: true
```

---

### Metodo 2: Aggiunta Manuale Risorsa Lovelace (se necessario)
Se Home Assistant non carica automaticamente le risorse:
1. Vai su **Impostazioni** ➔ **Dashboard** ➔ **Risorse** (in alto a destra).
2. Clicca **Aggiungi Risorsa**:
   - **URL**: `/sma_modbus/sma-tripower-card.js` (oppure copia il file in `/config/www/sma-tripower-card.js` e usa `/local/sma-tripower-card.js`)
   - **Tipo di risorsa**: `Modulo JavaScript`
3. Salva e ricarica la pagina del browser (F5 / Ctrl+F5).

---

## ⚙️ Opzioni di Configurazione Complete

| Parametro | Tipo | Predefinito | Descrizione |
|---|---|---|---|
| `type` | string | **Obbligatorio** | `custom:sma-tripower-card` |
| `title` | string | `SMA Sunny Tripower` | Titolo mostrato nell'intestazione |
| `inverter` | string | `inverter_1` | Prefisso delle entità (`inverter_1` o `inverter_2`) |
| `theme` | string | `dark` | Tema grafico: `dark` (scuro moderno) o `light` (sfondo bianco/chiaro) |
| `white_background` | boolean | `false` | Imposta rapidamente lo sfondo bianco se `true` (alias per `theme: light`) |
| `animation` | boolean | `true` | Abilita/disabilita le animazioni di flusso |
| `show_header` | boolean | `true` | Mostra/nasconde l'intestazione con badge di stato |
| `show_stats` | boolean | `true` | Mostra/nasconde i riquadri inferiori (Oggi, Totale, Temp) |
| `grid_power_entity` | string | *auto* | Override manuale sensore potenza di rete |
| `pv_power_1_entity` | string | *auto* | Override manuale sensore potenza Stringa 1 |
| `pv_power_2_entity` | string | *auto* | Override manuale sensore potenza Stringa 2 |
| `daily_yield_entity` | string | *auto* | Override manuale sensore resa giornaliera |
| `total_yield_entity` | string | *auto* | Override manuale sensore resa totale |
| `temperature_entity` | string | *auto* | Override manuale sensore temperatura |
| `status_entity` | string | *auto* | Override manuale sensore stato |
