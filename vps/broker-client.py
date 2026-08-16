#!/usr/bin/env python3
"""Unprivileged narrow client: signed Work Order + device token only."""
import json, os, socket, sys

request = {"action": "start", "work_order": json.load(sys.stdin),
           "device_token": os.environ["AGENTICDEV_DEVICE_TOKEN"]}
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
    s.connect("/run/agenticdev/broker.sock")
    s.sendall(json.dumps(request).encode()); s.shutdown(socket.SHUT_WR)
    response = json.loads(s.recv(65536))
print(json.dumps(response))
raise SystemExit(0 if response.get("ok") else 1)
