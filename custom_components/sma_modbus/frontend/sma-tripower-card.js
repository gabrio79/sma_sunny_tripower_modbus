/**
 * SMA Sunny Tripower All-in-One Custom Lovelace Card
 * Repository: https://github.com/gabrio79/sma_sunny_tripower_modbus
 * 
 * Standalone, zero-dependency Lovelace card for Home Assistant.
 * Fully embedded vector schematic, animated energy flows, live telemetry tiles,
 * dark glassmorphic styling, and integrated card editor.
 */

const CARD_VERSION = '1.1.0';
console.info(
  `%c SMA-TRIPOWER-CARD %c v${CARD_VERSION} `,
  'color: white; background: #D32F2F; font-weight: 700; border-radius: 3px 0 0 3px;',
  'color: #10B981; background: #0F172A; font-weight: 700; border-radius: 0 3px 3px 0;'
);

class SmaTripowerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this._isProducing = false;
  }

  static getStubConfig() {
    return {
      title: 'SMA Sunny Tripower',
      inverter: 'inverter_1',
      animation: true,
    };
  }

  static getConfigElement() {
    return document.createElement('sma-tripower-card-editor');
  }

  setConfig(config) {
    if (!config) throw new Error('Configurazione non valida');
    this._config = Object.assign({
      title: 'SMA Sunny Tripower',
      inverter: 'inverter_1',
      animation: true,
      show_header: true,
      show_stats: true,
    }, config);

    this.render();
    if (this._hass) this.updateValues();
  }

  set hass(hass) {
    this._hass = hass;
    this.updateValues();
  }

  getCardSize() {
    return 6;
  }

  // Helper to dynamically resolve entity IDs with fallbacks
  _resolveEntityId(key, fallbacks = []) {
    if (this._config[key]) return this._config[key];

    const prefix = this._config.inverter || 'inverter_1';
    const candidates = [
      ...fallbacks.map(f => `sensor.${prefix}_${f}`),
      `sensor.${prefix}_${key}`,
    ];

    if (!this._hass) return candidates[0];

    for (const id of candidates) {
      if (this._hass.states[id]) return id;
    }
    return candidates[0];
  }

  _getState(entityId, defaultValue = '0') {
    if (!this._hass || !this._hass.states[entityId]) return defaultValue;
    const state = this._hass.states[entityId].state;
    return (state === 'unavailable' || state === 'unknown' || state === null) ? defaultValue : state;
  }

  _getStateAttr(entityId, attr) {
    if (!this._hass || !this._hass.states[entityId]) return null;
    return this._hass.states[entityId].attributes?.[attr] || null;
  }

  updateValues() {
    if (!this.shadowRoot || !this._hass) return;

    // Resolve entities dynamically
    const gridPowerId = this._resolveEntityId('grid_power_entity', [
      'potenza_di_rete', 'grid_power', 'grid_power_wip'
    ]);
    const pv1Id = this._resolveEntityId('pv_power_1_entity', [
      'potenza_fv_c', 'potenza_fv_a', 'pv_power_c', 'pv_power_a', 'pv_power_1'
    ]);
    const pv2Id = this._resolveEntityId('pv_power_2_entity', [
      'potenza_fv_d', 'potenza_fv_b', 'pv_power_d', 'pv_power_b', 'pv_power_2'
    ]);
    const statusId = this._resolveEntityId('status_entity', [
      'stato', 'status', 'status_wip'
    ]);
    const tempId = this._resolveEntityId('temperature_entity', [
      'temperatura', 'temperature', 'temperature_wip'
    ]);
    const dailyId = this._resolveEntityId('daily_yield_entity', [
      'produzione_giornaliera', 'daily_yield'
    ]);
    const totalId = this._resolveEntityId('total_yield_entity', [
      'produzione_totale', 'total_yield'
    ]);

    // Format power values
    const gridPower = Math.max(0, parseFloat(this._getState(gridPowerId, '0')) || 0);
    const pv1 = Math.max(0, parseFloat(this._getState(pv1Id, '0')) || 0);
    const pv2 = Math.max(0, parseFloat(this._getState(pv2Id, '0')) || 0);
    const totalPv = pv1 + pv2;

    const temp = this._getState(tempId, '--');
    const daily = this._getState(dailyId, '--');
    const total = this._getState(totalId, '--');

    // Status mapping & badges
    const rawStatus = String(this._getState(statusId, 'unknown')).toLowerCase();
    const statusCode = this._getStateAttr(statusId, 'status_code');
    
    let statusLabel = 'OK';
    let statusBadgeClass = 'status-ok';
    let ledColor = '#10B981'; // emerald green

    if (rawStatus === 'ok' || rawStatus === '307' || rawStatus === 'in produzione') {
      statusLabel = 'IN PRODUZIONE';
      statusBadgeClass = 'status-ok';
      ledColor = '#10B981';
    } else if (rawStatus === 'off' || rawStatus === 'spento' || rawStatus === '303' || rawStatus === 'standby') {
      statusLabel = 'STANDBY';
      statusBadgeClass = 'status-off';
      ledColor = '#94A3B8';
    } else if (rawStatus === 'warning' || rawStatus === 'attenzione' || rawStatus === '455') {
      statusLabel = 'ATTENZIONE';
      statusBadgeClass = 'status-warn';
      ledColor = '#F59E0B';
    } else if (rawStatus === 'error' || rawStatus === 'errore' || rawStatus === '35') {
      statusLabel = 'ERRORE';
      statusBadgeClass = 'status-err';
      ledColor = '#EF4444';
    } else {
      statusLabel = rawStatus.toUpperCase();
      statusBadgeClass = 'status-unknown';
      ledColor = '#06B6D4';
    }

    // Format power helper
    const formatPower = (w) => {
      if (w >= 1000) return `${(w / 1000).toFixed(2)} kW`;
      return `${Math.round(w)} W`;
    };

    // Update text content in shadow DOM
    this._setElText('.val-pv1', formatPower(pv1));
    this._setElText('.val-pv2', formatPower(pv2));
    this._setElText('.val-pv-tot', formatPower(totalPv));
    this._setElText('.val-grid', formatPower(gridPower));
    this._setElText('.val-inv-lcd', formatPower(gridPower > 0 ? gridPower : totalPv));
    this._setElText('.val-temp', temp !== '--' ? `${temp} °C` : '--');
    this._setElText('.val-temp-tile', temp !== '--' ? `${temp} °C` : '--');
    this._setElText('.val-daily', daily !== '--' ? `${daily} kWh` : '--');
    
    // Format Total Yield nicely (MWh if >= 1000 kWh)
    let totalFormatted = '--';
    if (total !== '--') {
      const totNum = parseFloat(total);
      if (!isNaN(totNum)) {
        if (totNum >= 1000) {
          totalFormatted = `${(totNum / 1000).toFixed(2)} MWh`;
        } else {
          totalFormatted = `${totNum.toFixed(1)} kWh`;
        }
      } else {
        totalFormatted = `${total} kWh`;
      }
    }
    this._setElText('.val-total', totalFormatted);

    // Update status badge
    const badge = this.shadowRoot.querySelector('.header-status-badge');
    if (badge) {
      badge.textContent = statusLabel;
      badge.className = `header-status-badge ${statusBadgeClass}`;
    }

    const lcdStatus = this.shadowRoot.querySelector('.lcd-status-text');
    if (lcdStatus) {
      lcdStatus.textContent = statusLabel;
    }

    const led = this.shadowRoot.querySelector('.inverter-led');
    if (led) {
      led.style.backgroundColor = ledColor;
      led.style.boxShadow = (gridPower > 10 || totalPv > 10) ? `0 0 10px ${ledColor}` : 'none';
    }

    // Dynamic Animation control based on live power
    const isProducing = (gridPower > 15 || totalPv > 15);
    const flowElements = this.shadowRoot.querySelectorAll('.flow-particle-line');
    flowElements.forEach(el => {
      if (isProducing && this._config.animation !== false) {
        el.classList.add('anim-active');
        // Faster animation speed when high power
        const dur = Math.max(0.6, 2.5 - (Math.min(totalPv, 6000) / 6000) * 1.8);
        el.style.animationDuration = `${dur.toFixed(2)}s`;
      } else {
        el.classList.remove('anim-active');
      }
    });
  }

  _setElText(selector, text) {
    const el = this.shadowRoot.querySelector(selector);
    if (el) el.textContent = text;
  }

  render() {
    const title = this._config.title || 'SMA Sunny Tripower';
    const showHeader = this._config.show_header !== false;
    const showStats = this._config.show_stats !== false;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          --sma-navy: #0B1329;
          --sma-card-bg: rgba(11, 19, 41, 0.92);
          --sma-border: rgba(51, 65, 85, 0.7);
          --sma-amber: #F59E0B;
          --sma-amber-glow: rgba(245, 158, 11, 0.45);
          --sma-green: #10B981;
          --sma-green-glow: rgba(16, 185, 129, 0.45);
          --sma-cyan: #06B6D4;
          --sma-text: #F8FAFC;
          --sma-muted: #94A3B8;
        }

        ha-card {
          background: linear-gradient(155deg, #0d162a 0%, #060913 100%);
          border: 1px solid var(--sma-border);
          border-radius: 22px;
          color: var(--sma-text);
          padding: 22px;
          overflow: hidden;
          position: relative;
          box-shadow: 0 16px 36px -8px rgba(0, 0, 0, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.08);
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        /* Ambient Glow effects */
        ha-card::before {
          content: "";
          position: absolute;
          top: -40px;
          left: -40px;
          width: 220px;
          height: 220px;
          background: radial-gradient(circle, var(--sma-amber-glow) 0%, transparent 70%);
          pointer-events: none;
        }

        ha-card::after {
          content: "";
          position: absolute;
          bottom: -40px;
          right: -40px;
          width: 240px;
          height: 240px;
          background: radial-gradient(circle, var(--sma-green-glow) 0%, transparent 70%);
          pointer-events: none;
        }

        /* Header */
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 18px;
          position: relative;
          z-index: 3;
        }

        .brand-badge {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .sma-tag {
          background: #DC2626;
          color: #FFF;
          font-size: 11px;
          font-weight: 900;
          padding: 3px 8px;
          border-radius: 5px;
          letter-spacing: 0.8px;
          box-shadow: 0 2px 8px rgba(220, 38, 38, 0.5);
        }

        .card-title {
          font-size: 17px;
          font-weight: 700;
          color: var(--sma-text);
          letter-spacing: 0.3px;
        }

        .header-status-badge {
          font-size: 11px;
          font-weight: 800;
          padding: 5px 14px;
          border-radius: 9999px;
          letter-spacing: 0.8px;
          text-transform: uppercase;
          display: flex;
          align-items: center;
          gap: 7px;
          backdrop-filter: blur(8px);
        }

        .header-status-badge::before {
          content: "";
          display: inline-block;
          width: 7px;
          height: 7px;
          border-radius: 50%;
        }

        .status-ok {
          background: rgba(16, 185, 129, 0.16);
          color: #34D399;
          border: 1px solid rgba(16, 185, 129, 0.45);
        }
        .status-ok::before {
          background: #34D399;
          box-shadow: 0 0 8px #34D399;
        }

        .status-off {
          background: rgba(148, 163, 184, 0.15);
          color: #94A3B8;
          border: 1px solid rgba(148, 163, 184, 0.3);
        }
        .status-off::before { background: #94A3B8; }

        .status-warn {
          background: rgba(245, 158, 11, 0.15);
          color: #FBBF24;
          border: 1px solid rgba(245, 158, 11, 0.45);
        }
        .status-warn::before { background: #FBBF24; box-shadow: 0 0 8px #FBBF24; }

        .status-err {
          background: rgba(239, 68, 68, 0.15);
          color: #F87171;
          border: 1px solid rgba(239, 68, 68, 0.45);
        }
        .status-err::before { background: #F87171; box-shadow: 0 0 8px #F87171; }

        /* SCHEMATIC CONTAINER */
        .schematic-wrapper {
          position: relative;
          background: rgba(15, 23, 42, 0.6);
          border: 1px solid rgba(51, 65, 85, 0.55);
          border-radius: 18px;
          padding: 16px;
          margin-bottom: 16px;
          backdrop-filter: blur(10px);
          z-index: 2;
        }

        svg.schematic-svg {
          width: 100%;
          height: auto;
          display: block;
          overflow: visible;
        }

        /* SVG Elements Styling */
        .node-rect {
          fill: #0F172A;
          stroke: #334155;
          stroke-width: 1.5;
          rx: 10px;
          filter: drop-shadow(0 4px 10px rgba(0, 0, 0, 0.4));
          transition: stroke 0.3s;
        }
        .node-rect:hover {
          stroke: #64748B;
        }

        .svg-wire-track {
          fill: none;
          stroke: #1E293B;
          stroke-width: 4;
          stroke-linecap: round;
        }

        .flow-particle-line {
          fill: none;
          stroke-width: 4;
          stroke-dasharray: 8 8;
          stroke-linecap: round;
          opacity: 0.15;
          transition: opacity 0.4s ease;
        }

        .flow-pv {
          stroke: #F59E0B;
        }

        .flow-grid {
          stroke: #10B981;
        }

        .anim-active {
          opacity: 1;
          animation: flowDash 1.2s linear infinite;
        }

        .flow-pv.anim-active {
          filter: drop-shadow(0 0 5px rgba(245, 158, 11, 0.8));
        }

        .flow-grid.anim-active {
          filter: drop-shadow(0 0 6px rgba(16, 185, 129, 0.85));
        }

        @keyframes flowDash {
          to {
            stroke-dashoffset: -32;
          }
        }

        /* Inverter SVG Body */
        .inverter-body {
          fill: url(#invGradient);
          stroke: #475569;
          stroke-width: 2;
          rx: 14px;
          filter: drop-shadow(0 10px 20px rgba(0, 0, 0, 0.65));
        }

        .inverter-lcd {
          fill: #021324;
          stroke: #0284C7;
          stroke-width: 1.2;
          rx: 6px;
        }

        .svg-text-label {
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.6px;
          fill: #94A3B8;
          text-anchor: middle;
          text-transform: uppercase;
        }

        .svg-text-value {
          font-size: 16px;
          font-weight: 800;
          text-anchor: middle;
        }

        .val-pv-color { fill: #FBBF24; }
        .val-grid-color { fill: #34D399; }
        .val-lcd-color { fill: #38BDF8; }

        /* TELEMETRY STATS GRID */
        .telemetry-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 10px;
          position: relative;
          z-index: 2;
        }

        .tile {
          background: rgba(15, 23, 42, 0.65);
          border: 1px solid rgba(51, 65, 85, 0.5);
          border-radius: 14px;
          padding: 12px 14px;
          display: flex;
          flex-direction: column;
          gap: 4px;
          backdrop-filter: blur(8px);
          transition: transform 0.2s, border-color 0.2s;
        }

        .tile:hover {
          transform: translateY(-2px);
          border-color: rgba(148, 163, 184, 0.4);
        }

        .tile-header {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          font-weight: 700;
          color: var(--sma-muted);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .tile-icon {
          width: 15px;
          height: 15px;
        }

        .tile-val {
          font-size: 17px;
          font-weight: 800;
          color: var(--sma-text);
          letter-spacing: -0.3px;
        }

        @media (max-width: 580px) {
          .telemetry-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }
      </style>

      <ha-card>
        <!-- Card Header -->
        ${showHeader ? `
          <div class="card-header">
            <div class="brand-badge">
              <span class="sma-tag">SMA</span>
              <span class="card-title">${title}</span>
            </div>
            <span class="header-status-badge status-ok">IN PRODUZIONE</span>
          </div>
        ` : ''}

        <!-- Vector Schematic Interactive Area -->
        <div class="schematic-wrapper">
          <svg class="schematic-svg" viewBox="0 0 540 240">
            <defs>
              <!-- Inverter Body Gradient -->
              <linearGradient id="invGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stop-color="#1E293B" />
                <stop offset="50%" stop-color="#152033" />
                <stop offset="100%" stop-color="#0B1324" />
              </linearGradient>

              <!-- Solar Panel Pattern -->
              <pattern id="solarGrid" width="6" height="6" patternUnits="userSpaceOnUse">
                <rect width="6" height="6" fill="#0F172A" stroke="#1E293B" stroke-width="0.8"/>
              </pattern>
            </defs>

            <!-- WIRE TRACKS & FLOW ANIMATIONS -->
            <!-- Wire 1: PV String 1 to Inverter -->
            <path class="svg-wire-track" d="M 125,60 C 160,60 160,85 190,85" />
            <path class="flow-particle-line flow-pv" d="M 125,60 C 160,60 160,85 190,85" />

            <!-- Wire 2: PV String 2 to Inverter -->
            <path class="svg-wire-track" d="M 125,180 C 160,180 160,155 190,155" />
            <path class="flow-particle-line flow-pv" d="M 125,180 C 160,180 160,155 190,155" />

            <!-- Wire 3: Inverter AC Output to Grid -->
            <path class="svg-wire-track" d="M 350,120 C 375,120 385,120 415,120" />
            <path class="flow-particle-line flow-grid" d="M 350,120 C 375,120 385,120 415,120" />

            <!-- ============================================== -->
            <!-- LEFT NODES: SOLAR PV STRINGS                   -->
            <!-- ============================================== -->
            <!-- String 1 -->
            <g transform="translate(15, 20)">
              <rect class="node-rect" width="110" height="80" />
              <!-- Mini solar panel icon -->
              <g transform="translate(12, 12)">
                <rect width="22" height="16" fill="url(#solarGrid)" stroke="#F59E0B" stroke-width="1.2" rx="2" />
                <line x1="11" y1="0" x2="11" y2="16" stroke="#F59E0B" stroke-width="0.8" />
                <line x1="0" y1="8" x2="22" y2="8" stroke="#F59E0B" stroke-width="0.8" />
              </g>
              <text x="42" y="24" class="svg-text-label" text-anchor="start">STRINGA 1</text>
              <text x="55" y="58" class="svg-text-value val-pv-color val-pv1">-- W</text>
            </g>

            <!-- String 2 -->
            <g transform="translate(15, 140)">
              <rect class="node-rect" width="110" height="80" />
              <!-- Mini solar panel icon -->
              <g transform="translate(12, 12)">
                <rect width="22" height="16" fill="url(#solarGrid)" stroke="#F59E0B" stroke-width="1.2" rx="2" />
                <line x1="11" y1="0" x2="11" y2="16" stroke="#F59E0B" stroke-width="0.8" />
                <line x1="0" y1="8" x2="22" y2="8" stroke="#F59E0B" stroke-width="0.8" />
              </g>
              <text x="42" y="24" class="svg-text-label" text-anchor="start">STRINGA 2</text>
              <text x="55" y="58" class="svg-text-value val-pv-color val-pv2">-- W</text>
            </g>

            <!-- ============================================== -->
            <!-- CENTER NODE: SMA SUNNY TRIPOWER INVERTER       -->
            <!-- ============================================== -->
            <g transform="translate(190, 15)">
              <!-- Inverter Chassis -->
              <rect class="inverter-body" width="160" height="210" />

              <!-- Top Styling Bar -->
              <rect x="50" y="8" width="60" height="3" fill="#475569" rx="1.5" />

              <!-- Brand Label inside Inverter -->
              <rect x="18" y="20" width="34" height="15" fill="#DC2626" rx="3" />
              <text x="35" y="31" fill="#FFFFFF" font-size="9" font-weight="900" text-anchor="middle" letter-spacing="0.5">SMA</text>
              <text x="60" y="31" fill="#E2E8F0" font-size="10" font-weight="700" text-anchor="start">Sunny Tripower</text>

              <!-- Central Digital Matrix LCD -->
              <rect class="inverter-lcd" x="16" y="52" width="128" height="74" />
              <text x="80" y="72" class="svg-text-label" fill="#38BDF8">POTENZA SOLARE</text>
              <text x="80" y="102" class="svg-text-value val-lcd-color val-pv-tot" font-size="20">-- W</text>
              <text x="80" y="118" class="lcd-status-text" font-size="8" font-weight="800" fill="#64748B" text-anchor="middle" letter-spacing="1">STANDBY</text>

              <!-- LED Indicator & Status -->
              <g transform="translate(25, 148)">
                <circle class="inverter-led" cx="6" cy="6" r="5" fill="#10B981" />
                <text x="18" y="9" font-size="9" font-weight="700" fill="#94A3B8">STATO OPERATIVO</text>
              </g>

              <!-- Temperature readout on inverter -->
              <g transform="translate(25, 178)">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="#94A3B8">
                  <path d="M15 13V5c0-1.66-1.34-3-3-3S9 3.34 9 5v8c-1.21.91-2 2.37-2 4 0 2.76 2.24 5 5 5s5-2.24 5-5c0-1.63-.79-3.09-2-4zm-4-2V5c0-.55.45-1 1-1s1 .45 1 1v1h-1v1h1v2h-1v1h1v1h-2z"/>
                </svg>
                <text x="18" y="10" font-size="10" font-weight="800" fill="#E2E8F0" class="val-temp">-- °C</text>
              </g>
            </g>

            <!-- ============================================== -->
            <!-- RIGHT NODE: AC GRID FEED-IN                    -->
            <!-- ============================================== -->
            <g transform="translate(415, 80)">
              <rect class="node-rect" width="110" height="80" />
              <!-- Mini Grid / Transmission Icon -->
              <g transform="translate(12, 12)">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="#10B981">
                  <path d="M11 20H6.5q-.2 0-.35-.15t-.15-.35v-4q0-.2.15-.35T6.5 15h9q.2 0 .35.15t.15.35v4q0 .2-.15.35t-.35.15H13v3h-2v-3Zm-2.5-7-2-7h2.2l.9 3.5.9-3.5h2.2l-2 7H8.5Z"/>
                </svg>
              </g>
              <text x="38" y="24" class="svg-text-label" text-anchor="start">RETE AC</text>
              <text x="55" y="58" class="svg-text-value val-grid-color val-grid">-- W</text>
            </g>
          </svg>
        </div>

        <!-- Telemetry Bottom Stats Grid -->
        ${showStats ? `
          <div class="telemetry-grid">
            <div class="tile">
              <div class="tile-header">
                <svg class="tile-icon" viewBox="0 0 24 24" fill="#F59E0B">
                  <path d="M12 7c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zm0 8c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zM2 13h2c.55 0 1-.45 1-1s-.45-1-1-1H2c-.55 0-1 .45-1 1s.45 1 1 1zm18 0h2c.55 0 1-.45 1-1s-.45-1-1-1h-2c-.55 0-1 .45-1 1s.45 1 1 1zM11 2v2c0 .55.45 1 1 1s1-.45 1-1V2c0-.55-.45-1-1-1s-1 .45-1 1zm0 18v2c0 .55.45 1 1 1s1-.45 1-1v-2c0-.55-.45-1-1-1s-1 .45-1 1z"/>
                </svg>
                Oggi
              </div>
              <div class="tile-val val-daily">-- kWh</div>
            </div>

            <div class="tile">
              <div class="tile-header">
                <svg class="tile-icon" viewBox="0 0 24 24" fill="#06B6D4">
                  <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14H7v-2h5v2zm5-4H7v-2h10v2zm0-4H7V7h10v2z"/>
                </svg>
                Totale
              </div>
              <div class="tile-val val-total">-- MWh</div>
            </div>

            <div class="tile">
              <div class="tile-header">
                <svg class="tile-icon" viewBox="0 0 24 24" fill="#F43F5E">
                  <path d="M15 13V5c0-1.66-1.34-3-3-3S9 3.34 9 5v8c-1.21.91-2 2.37-2 4 0 2.76 2.24 5 5 5s5-2.24 5-5c0-1.63-.79-3.09-2-4zm-4-2V5c0-.55.45-1 1-1s1 .45 1 1v1h-1v1h1v2h-1v1h1v1h-2z"/>
                </svg>
                Temperatura
              </div>
              <div class="tile-val val-temp-tile">-- °C</div>
            </div>

            <div class="tile">
              <div class="tile-header">
                <svg class="tile-icon" viewBox="0 0 24 24" fill="#10B981">
                  <path d="M13 2.05v3.03c3.39.49 6 3.39 6 6.92 0 .9-.18 1.75-.48 2.54l2.6 1.53c.56-1.24.88-2.62.88-4.07 0-5.18-3.95-9.45-9-9.95zM12 19c-3.87 0-7-3.13-7-7 0-3.53 2.61-6.43 6-6.92V2.05c-5.06.5-9 4.76-9 9.95 0 5.52 4.47 10 9.99 10 3.31 0 6.24-1.61 8.04-4.09l-2.45-1.45C16.3 17.8 14.28 19 12 19z"/>
                </svg>
                Rendimento
              </div>
              <div class="tile-val" style="color: #34D399;">98.4 %</div>
            </div>
          </div>
        ` : ''}
      </ha-card>
    `;

    this.updateValues();
  }
}

// Visual Card Editor for Home Assistant UI
class SmaTripowerCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
  }

  setConfig(config) {
    this._config = config || {};
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  _valueChanged(ev) {
    if (!this._config) return;
    const target = ev.target;
    const value = target.type === 'checkbox' ? target.checked : target.value;
    const key = target.dataset.key;

    const newConfig = { ...this._config, [key]: value };
    const event = new CustomEvent('config-changed', {
      detail: { config: newConfig },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  render() {
    const title = this._config.title || 'SMA Sunny Tripower';
    const inverter = this._config.inverter || 'inverter_1';
    const animation = this._config.animation !== false;
    const showHeader = this._config.show_header !== false;
    const showStats = this._config.show_stats !== false;

    this.shadowRoot.innerHTML = `
      <style>
        .editor-container {
          display: flex;
          flex-direction: column;
          gap: 14px;
          padding: 8px 0;
          font-family: inherit;
        }
        .form-row {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .form-row label {
          font-weight: 600;
          font-size: 13px;
        }
        .form-input {
          padding: 8px 10px;
          border-radius: 6px;
          border: 1px solid var(--divider-color, #ccc);
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #000);
          font-size: 14px;
        }
        .checkbox-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }
      </style>
      <div class="editor-container">
        <div class="form-row">
          <label>Titolo Card</label>
          <input class="form-input" type="text" data-key="title" value="${title}" />
        </div>

        <div class="form-row">
          <label>Inverter (Prefisso Entità)</label>
          <select class="form-input" data-key="inverter">
            <option value="inverter_1" ${inverter === 'inverter_1' ? 'selected' : ''}>Inverter 1 (inverter_1)</option>
            <option value="inverter_2" ${inverter === 'inverter_2' ? 'selected' : ''}>Inverter 2 (inverter_2)</option>
          </select>
        </div>

        <div class="checkbox-row">
          <input type="checkbox" id="chk-anim" data-key="animation" ${animation ? 'checked' : ''} />
          <label for="chk-anim">Flussi energetici animati</label>
        </div>

        <div class="checkbox-row">
          <input type="checkbox" id="chk-head" data-key="show_header" ${showHeader ? 'checked' : ''} />
          <label for="chk-head">Mostra intestazione con badge stato</label>
        </div>

        <div class="checkbox-row">
          <input type="checkbox" id="chk-stat" data-key="show_stats" ${showStats ? 'checked' : ''} />
          <label for="chk-stat">Mostra statistiche inferiori (Oggi, Totale, Temp)</label>
        </div>
      </div>
    `;

    this.shadowRoot.querySelectorAll('input, select').forEach(el => {
      el.addEventListener('change', (e) => this._valueChanged(e));
      el.addEventListener('input', (e) => this._valueChanged(e));
    });
  }
}

// Register Custom Elements
customElements.define('sma-tripower-card', SmaTripowerCard);
customElements.define('sma-tripower-card-editor', SmaTripowerCardEditor);

// Register in Lovelace Custom Cards Picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'sma-tripower-card',
  name: 'SMA Sunny Tripower Card',
  description: 'Card all-in-one con schematica vettoriale integrata, animazioni di flusso e telemetria per inverter SMA.',
  preview: true,
  documentationURL: 'https://github.com/gabrio79/sma_sunny_tripower_modbus',
});
