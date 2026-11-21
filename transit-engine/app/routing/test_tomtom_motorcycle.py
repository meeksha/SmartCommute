from app.routing.tomtom_traffic import calculate_road_route

origin = (12.9585, 77.5635)
destination = (13.0105, 77.5540)

try:
    result = calculate_road_route(
        origin,
        destination,
        travel_mode="motorcycle"
    )

    print("\nTOMTOM MOTORCYCLE ROUTE")
    print("=======================")

    for key, value in result.items():
        print(f"{key}: {value}")

except Exception as exc:
    print("MOTORCYCLE ROUTING TEST FAILED")
    print(exc)
