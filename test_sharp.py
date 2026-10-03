import asyncio
import getpass
from dataclasses import asdict, is_dataclass

from aiosharp_cocoro_air import (
    SharpCOCOROAir,
    SharpAuthError,
    SharpApiError,
    SharpConnectionError,
)


async def main():
    email = input("Sharp Life AIR e-mail: ").strip()
    password = getpass.getpass("Sharp Life AIR password: ")

    try:
        async with SharpCOCOROAir(email, password) as client:
            print("\nLogowanie...")
            await client.authenticate()
            print("Logowanie OK.")

            print("\nPobieranie urządzeń...")
            devices = await client.get_devices()

            print(f"Znaleziono urządzeń: {len(devices)}")

            for number, device in enumerate(devices, 1):
                print("\n" + "=" * 70)
                print(f"URZĄDZENIE {number}")
                print("=" * 70)

                if is_dataclass(device):
                    for key, value in asdict(device).items():
                        print(f"{key}: {value}")
                else:
                    print(device)

                print("\nProperties:")
                properties = getattr(device, "properties", None)

                if properties is None:
                    print("brak")
                elif is_dataclass(properties):
                    for key, value in asdict(properties).items():
                        print(f"{key}: {value}")
                else:
                    print(properties)

    except SharpAuthError as err:
        print(f"\nBŁĄD LOGOWANIA: {err}")

    except SharpConnectionError as err:
        print(f"\nBŁĄD POŁĄCZENIA: {err}")

    except SharpApiError as err:
        print(f"\nBŁĄD API: {err}")

    except Exception as err:
        print(f"\nNIEOCZEKIWANY BŁĄD: {type(err).__name__}: {err}")
        raise


asyncio.run(main())
