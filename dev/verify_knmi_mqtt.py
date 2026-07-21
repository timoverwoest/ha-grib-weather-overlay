#!/usr/bin/env python3
"""Standalone check of the KNMI MQTT Notification Service connection.

No Home Assistant needed -- only paho-mqtt. Unlike dev/verify_knmi_source.py,
this needs a *real, registered* API key: KNMI's public anonymous demo key is
rejected for MQTT (verified: CONNACK reason code "Not authorized"), even
though the same key works fine for the REST Open Data API.

Run:
    python3 dev/verify_knmi_mqtt.py <api_key> [dataset_key] [dataset_version]

Listens for up to 90s and prints any "new file" notifications received. A
successful CONNACK proves broker/port/websocket/TLS/auth are wired up
correctly even if no notification arrives in that window (harmonie_arome_cy43_p1
publishes a new run about once an hour).
"""

from __future__ import annotations

import json
import sys
import time
import uuid

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

MQTT_HOST = "mqtt.dataplatform.knmi.nl"
MQTT_PORT = 443
MQTT_WS_PATH = "/mqtt"
LISTEN_SECONDS = 90


def main(api_key: str, dataset_key: str, dataset_version: str) -> None:
    topic = f"dataplatform/file/v1/{dataset_key}/{dataset_version}/created"
    connected = {"ok": False}

    def on_connect(client, _userdata, _flags, reason_code, _properties):
        connected["ok"] = reason_code == 0
        print(f"CONNACK: {reason_code} ({'OK' if connected['ok'] else 'REJECTED'})")
        if connected["ok"]:
            print(f"Subscribing to {topic}")
            client.subscribe(topic, qos=1)

    def on_message(_client, _userdata, msg):
        try:
            payload = json.loads(msg.payload)
            print(f"NEW FILE: {payload['data']['filename']}")
        except Exception:  # noqa: BLE001 - just show the raw payload if parsing fails
            print(f"MESSAGE on {msg.topic}: {msg.payload[:300]!r}")

    def on_disconnect(_client, _userdata, _flags, reason_code, _properties):
        print(f"DISCONNECT: {reason_code}")

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"ha-grib-overlay-{uuid.uuid4()}",
        transport="websockets",
        protocol=mqtt.MQTTProtocolVersion.MQTTv5,
    )
    client.username_pw_set(username="token", password=api_key)
    client.tls_set()
    client.ws_set_options(path=MQTT_WS_PATH)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    connect_properties = Properties(PacketTypes.CONNECT)
    connect_properties.SessionExpiryInterval = 3600
    client.connect(
        MQTT_HOST, MQTT_PORT, keepalive=60, clean_start=False, properties=connect_properties
    )
    client.loop_start()
    print(f"Listening for {LISTEN_SECONDS}s ...")
    time.sleep(LISTEN_SECONDS)
    client.loop_stop()
    client.disconnect()

    if not connected["ok"]:
        print("Connection was never accepted -- check the API key.")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    key = sys.argv[1]
    dset = sys.argv[2] if len(sys.argv) > 2 else "harmonie_arome_cy43_p1"
    version = sys.argv[3] if len(sys.argv) > 3 else "1.0"
    main(key, dset, version)
