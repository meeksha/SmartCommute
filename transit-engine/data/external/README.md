# External data

`namma_yatri_ward_summary.csv`: one row per Bengaluru ward (searches, bookings, completed trips,
cancellation rate, average distance and fare per trip). From
https://github.com/scariadon5/Namma-Yatri-Pricing-MLOPS- (MIT License, (c) 2026 Don Scaria),
originally from Namma Yatri's open data. Used only to validate SmartCommute's distance-based fare model
(`python -m app.ml.validate_fares`).
