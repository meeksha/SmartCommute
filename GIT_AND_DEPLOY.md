# Sharing SmartCommute on GitHub and putting it online

## What goes where
| Part | Size | How it's shared |
|---|---|---|
| Code, tests, docs, small data (`transit-engine/data/external`), ML models | about 20 MB | the Git repository |
| Timetables, walking network, fare database (`transit-engine/data`) | about 1.4 GB, with single files up to 410 MB | one zip attached to a GitHub **Release**. GitHub refuses files over 100 MB in a repository, but a release file can be up to 2 GB. |
| `.env` (TomTom key, Google client ID, admin emails), certificates | tiny | **never on GitHub**. Send privately to teammates who need them. |

The `.gitignore` in this folder already enforces this.

## 1. Push to GitHub (once, from your laptop)
1. On github.com: **New repository**, named e.g. `smartcommute`, set to **Private**, with *no* README, licence or .gitignore (you already have them).
   Then go to **Settings → Collaborators** and add your teammates.
2. In PowerShell, from the folder that contains `docker-compose.yml`:
   ```powershell
   cd $HOME\Desktop\major
   git init
   git add .
   git status
   ```
   Check the list: no `.env`, nothing under `transit-engine/data/` except `external/`, no `.zip`. If something unexpected shows up, add it to `.gitignore` and run `git add .` again.
3. Make sure nothing is over GitHub's limit (this should print nothing):
   ```powershell
   git ls-files | ForEach-Object { Get-Item $_ } | Where-Object Length -gt 50MB | Select-Object FullName, Length
   ```
4. Commit and push (replace YOUR-NAME):
   ```powershell
   git commit -m "SmartCommute: engine, frontend, docs"
   git branch -M main
   git remote add origin https://github.com/YOUR-NAME/smartcommute.git
   git push -u origin main
   ```
   The first push opens a browser window to sign in to GitHub.

## 2. Share the data (once)
```powershell
cd $HOME\Desktop\major\transit-engine
Compress-Archive -Path data -DestinationPath $HOME\Desktop\smartcommute-data.zip
```
On GitHub, go to **Releases → Draft a new release**, use tag `data-2026-11`, drag in `smartcommute-data.zip` and publish. It takes a few minutes to upload.

## 3. What a teammate does
```powershell
git clone https://github.com/YOUR-NAME/smartcommute.git
cd smartcommute
# download smartcommute-data.zip from the repo's Releases page, then:
Expand-Archive $HOME\Downloads\smartcommute-data.zip -DestinationPath transit-engine -Force
copy .env.example .env        # then fill in the values you sent them
docker compose up -d --build  # http://localhost:8080
```
For report writing, `docs/SmartCommute_Technical_Reference.docx` and `transit-engine/docs/API.md` are enough; running the app needs Docker with about 6 GB of RAM.

## 4. Putting it online
The engine keeps about 2 million timetable connections in memory, so it needs **4–6 GB of RAM** and a PostgreSQL database. Free hosting tiers (Render, Railway, Vercel, Netlify) don't have that much memory, and Vercel/Netlify only host static websites. Two options that work:

### A. Demo from your laptop with a public link (free, about 5 minutes)
```powershell
winget install --id Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:8080
```
It prints a `https://<random-words>.trycloudflare.com` address that anyone can open while your laptop and Docker are running.
- **Location:** it's HTTPS, so phones can use "Use my current location". Browsers only allow GPS on HTTPS or on localhost.
- **Google sign-in:** add that address under **Authorized JavaScript origins** in Google Cloud. The address changes every time you start the tunnel, so for a demo email sign-in is simpler.
- **Limits:** the link stops when you close the window or the laptop sleeps.

### B. A real server (always on)
1. Rent a cloud VM with **8 GB RAM**, 2 vCPU, 30 GB disk, Ubuntu (AWS, Azure, Google Cloud, DigitalOcean). Student credits, for example through the GitHub Student Developer Pack, can cover this.
2. On the server:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
   git clone https://github.com/YOUR-NAME/smartcommute.git && cd smartcommute
   # copy smartcommute-data.zip to the server (or download it from the release), then:
   unzip smartcommute-data.zip -d transit-engine
   nano .env        # TOMTOM_API_KEY, GOOGLE_CLIENT_ID, ADMIN_EMAILS, POSTGRES_PASSWORD=<a long random password>
   sudo docker compose up -d --build
   ```
3. **HTTPS:** either run `cloudflared` as a named tunnel to your own domain, or put Caddy in front of port 8080. Only ports 80 and 443 should be open in the cloud firewall. The database (5432) and API (8000) are bound to the server itself and are not reachable from outside.
4. Add the domain to Google's Authorized JavaScript origins.

### Before anything is public
- Set a strong `POSTGRES_PASSWORD` in `.env` before the first start.
- Keep `.env` off GitHub, and rotate the TomTom key if it was ever shared.
- Real colleagues' trips and contact details will be stored. Tell users what's stored and get their consent; the app reveals contact details only after a request is accepted.
- Keep the attribution: map data © OpenStreetMap contributors (ODbL), and the BMTC/BMRCL GTFS feeds' licences (see the technical reference).
