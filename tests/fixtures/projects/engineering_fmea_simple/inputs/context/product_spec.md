# Product spec: battery-powered IoT environmental sensor

## Summary

A small battery-powered IoT sensor that periodically samples ambient
temperature + humidity, transmits the reading over LoRaWAN to a
gateway, and sleeps between samples to extend battery life.

## Target use

Deployed in unheated outdoor enclosures (warehouses, agricultural
sheds) where mains power is unavailable. Expected service life: 18
months on a single primary lithium cell.

## Functions

1. **sense** — sample temperature (-40 to +85 C) + relative humidity
   (0 to 100%) every 10 minutes; tolerance +/- 0.5 C, +/- 3% RH.
2. **transmit** — package the reading as a LoRaWAN uplink (SF7-SF12,
   adaptive); retry once on NAK; drop after second failure.
3. **sleep** — enter deep-sleep between samples; wake on RTC
   interrupt; average current draw under 50 uA at 25 C.

## Components

- MCU: STM32L0 ultra-low-power Cortex-M0+
- Sensor: Sensirion SHT40
- Radio: Semtech SX1262 LoRa transceiver
- Battery: Saft LS17500 primary lithium (3.6 V, 3.6 Ah)
- Housing: IP67 polycarbonate enclosure with gasketed lid

## Environmental envelope

Operating: -20 C to +60 C. Non-operating (storage): -40 C to +85 C.
Vibration per IEC 60721-3-4 class 4M3.
