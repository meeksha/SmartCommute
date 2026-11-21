Put your network's / antivirus's root certificate here (Base-64 .crt, .cer or .pem) if Google sign-in,
live traffic or weather fail with "CERTIFICATE_VERIFY_FAILED ... self-signed certificate".
Then run: docker compose up -d --build
The backend log shows "[certs] trusting 1 extra root certificate(s)" when it is picked up.
