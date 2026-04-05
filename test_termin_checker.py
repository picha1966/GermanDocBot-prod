import asyncio
from utils.termin_checker import check_termin_availability


async def main():

    tests = [

        ("berlin", "anmeldung"),

        ("frankfurt", "anmeldung"),
        ("frankfurt", "personalausweis"),

        ("duesseldorf", "anmeldung"),
        ("duesseldorf", "personalausweis"),

        ("koeln", "anmeldung"),
        ("koeln", "personalausweis"),

    ]

    for city, service in tests:

        print(f"\nTesting {city} / {service}")

        try:

            status, data = await check_termin_availability(
                city,
                service
            )

            print("Status:", status)
            print("Data:", data)

        except Exception as e:

            print("ERROR:", e)


if __name__ == "__main__":
    asyncio.run(main())
