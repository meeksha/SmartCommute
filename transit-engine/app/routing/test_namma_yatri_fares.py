from app.routing.namma_yatri_fares import (
    estimate_auto_fare,
    estimate_cab_fare
)

distances = [2, 5, 10, 15]

print(f"{'Distance':<12}{'Auto':<15}{'Cab (<=10L)':<18}")

for distance in distances:
    auto = estimate_auto_fare(distance)
    cab = estimate_cab_fare(distance, "up_to_10_lakh")

    print(
        f"{distance:<12}"
        f"Rs.{auto['estimated_total_inr']:<12.2f}"
        f"Rs.{cab['estimated_total_inr']:<15.2f}"
    )
