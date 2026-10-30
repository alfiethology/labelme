"""Small generated FLIR containers for offline format and GUI regression tests."""

from __future__ import annotations

import io
import struct

import numpy as np
from PIL import Image


def fff(raw: np.ndarray | None = None, *, order: str = "<", png: bool = False) -> bytes:
    if raw is None:
        raw = np.array([[18109, 18500], [19000, 19500]], dtype=np.uint16)
    camera = bytearray(0x400)
    struct.pack_into(order + "H", camera, 0, 2)
    for offset, value in {
        0x20: 1,
        0x24: 0,
        0x28: 293.15,
        0x2C: 293.15,
        0x30: 293.15,
        0x34: 1,
        0x3C: 0.5,
        0x58: 21106.77,
        0x5C: 1501,
        0x60: 1,
        0x70: 0.006569,
        0x74: 0.01262,
        0x78: -0.002276,
        0x7C: -0.00667,
        0x80: 1.9,
        0x30C: 0.012545258,
    }.items():
        struct.pack_into(order + "f", camera, offset, value)
    struct.pack_into(order + "i", camera, 0x308, -7340)
    camera[0xD4:0xD8] = b"Test"
    sensor = bytearray(32)
    struct.pack_into(order + "HHH", sensor, 0, 2, raw.shape[1], raw.shape[0])
    if png:
        stream = io.BytesIO()
        Image.fromarray(raw.astype(np.uint16).byteswap()).save(stream, format="PNG")
        payload = stream.getvalue()
    else:
        payload = raw.astype(order + "u2").tobytes()
    sensor += payload
    header = bytearray(64)
    header[:4] = b"FFF\0"
    struct.pack_into(order + "III", header, 20, 100, 64, 3)
    directory = bytearray(3 * 32)
    start = len(header) + len(directory)
    for number, (kind, offset, length) in enumerate(
        (
            (32, start, len(camera)),
            (1, start + len(camera), len(sensor)),
            (44, start + len(camera), 0),  # Optional empty records are legal.
        )
    ):
        struct.pack_into(order + "H", directory, number * 32, kind)
        struct.pack_into(order + "II", directory, number * 32 + 12, offset, length)
    return bytes(header + directory + camera + sensor)


def radiometric_jpeg(data: bytes, *, zero_counters: bool = False) -> bytes:
    preview = io.BytesIO()
    Image.new("RGB", (8, 6)).save(preview, format="JPEG")
    segments = []
    chunks = [data[:600], data[600:]]
    for index, chunk in enumerate(chunks):
        prefix = b"FLIR\0\x01" + (b"\0\0" if zero_counters else bytes([index, 1]))
        payload = prefix + chunk
        segments.append(b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload)
    return preview.getvalue()[:2] + b"".join(segments) + preview.getvalue()[2:]
