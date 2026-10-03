"""Read-only sensor diagnostics for the pinned Sharp EU API library."""
import asyncio
import getpass

from aiosharp_cocoro_air import (
    SharpCOCOROAir, SharpAuthError, SharpApiError, SharpConnectionError,
    decode_echonet_property,
)

SENSOR_CODES = {0x80, 0x84, 0x85, 0x88, 0x8B, 0xA0, 0xC0, 0xF1, 0xF3}


def inspect_properties(value):
    if not value:
        print("echonetProperty: empty")
        return
    try:
        data = bytes.fromhex(value)
    except (TypeError, ValueError):
        print("echonetProperty: invalid hex")
        return
    print(f"echonetProperty bytes: {len(data)}")
    if len(data) < 8:
        print("Header incomplete")
        return
    clean = bytearray(data[:8])
    offset = 8
    while offset + 1 < len(data):
        code, length = data[offset:offset + 2]
        end = offset + 2 + length
        if end > len(data):
            print(f"0x{code:02X}: truncated, expected {length} bytes")
            break
        payload = data[offset + 2:end]
        # Never print unknown fields, account IDs or the raw response.
        detail = payload.hex() if code in SENSOR_CODES else "[omitted]"
        print(f"0x{code:02X}: length={length}, value={detail or '[empty]'}")
        if length:
            clean.extend(data[offset:end])
        offset = end
    print("Decoded non-empty sensor properties:")
    try:
        properties = decode_echonet_property(clean.hex())
    except (IndexError, ValueError):
        print("Decoder rejected the remaining sensor data")
        return
    if not properties:
        print("[none]")
    for key, value in properties.items():
        print(f"{key}: {value}")


async def main():
    email = input("Sharp Life AIR e-mail: ").strip()
    password = getpass.getpass("Sharp Life AIR password: ")
    try:
        async with SharpCOCOROAir(email, password) as client:
            async with asyncio.timeout(90):
                print("\nLogowanie...")
                await client.authenticate()
                print("Logowanie OK.")
            for attempt in range(1, 4):
                print(f"\nODCZYT {attempt}/3")
                async with asyncio.timeout(45):
                    boxes = await client._get_boxes()
                count = 0
                for box in boxes.get("box", []):
                    for device in box.get("echonetData", []):
                        count += 1
                        print(f"\nURZĄDZENIE {count}")
                        print(f"Model: {device.get('model')}")
                        inspect_properties(device.get("echonetProperty"))
                print(f"Znaleziono urządzeń: {count}")
                if attempt < 3:
                    await asyncio.sleep(5)
    except SharpAuthError:
        print("BŁĄD LOGOWANIA")
    except (SharpApiError, SharpConnectionError, TimeoutError) as err:
        print(f"BŁĄD POŁĄCZENIA/API: {type(err).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
