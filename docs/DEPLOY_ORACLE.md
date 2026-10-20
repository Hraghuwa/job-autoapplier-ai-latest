# Deploy on Oracle Cloud Always Free (free forever)

Runs the whole backend stack — FastAPI + Celery browser worker + Postgres +
Redis — on one Oracle ARM VM. Frontend stays on Vercel. Nothing here costs money.

You do the account/VM steps (I can't create accounts or enter credentials). Each
step is copy-paste once you're SSH'd in.

---

## 1. Create the VM (Oracle Cloud Console)

1. Sign up at https://cloud.oracle.com → **Always Free** eligible.
2. **Compute → Instances → Create Instance**:
   - **Shape**: change to **Ampere (ARM)** → `VM.Standard.A1.Flex`, set **2 OCPU / 12 GB RAM** (well within the always-free 4 OCPU / 24 GB).
   - **Image**: Ubuntu 22.04 (or 24.04).
   - **SSH keys**: upload your public key (or let it generate one — save the private key).
3. After it boots, note the **public IP**.
4. **Open ports 80 + 443**:
   - *Networking → VCN → Security List → Add Ingress Rules*: source `0.0.0.0/0`, TCP ports `80` and `443`.
   - Also on the VM itself: `sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT && sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT && sudo netfilter-persistent save`

## 2. Point a hostname at the VM

Caddy needs a public hostname to issue HTTPS. Free option: **DuckDNS**.
1. https://www.duckdns.org → sign in → create a subdomain, e.g. `jobagent`.
2. Set its IP to your VM's public IP. You now have `jobagent.duckdns.org`.

## 3. Install Docker on the VM

```bash
ssh ubuntu@YOUR_VM_IP
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
```

## 4. Get the code + configure

```bash
git clone -b e2e-hardening https://github.com/Hraghuwa/job-autoapplier-ai-latest.git
cd job-autoapplier-ai-latest
cp .env.prod.example .env.prod
nano .env.prod          # fill DOMAIN, POSTGRES_PASSWORD, SECRET_KEY, FERNET_KEY, FRONTEND_URL, LLM keys
```

Generate the two required secrets locally or on the VM:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"                              # SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # FERNET_KEY
```

## 5. Launch

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

First build takes a few minutes (Chromium in the worker image). Then:
```bash
docker compose -f docker-compose.prod.yml logs -f backend worker
curl https://jobagent.duckdns.org/health      # expect 200
```

## 6. Point the frontend at the new backend

In **Vercel → your frontend project → Settings → Environment Variables**, set:
- `NEXT_PUBLIC_API_URL = https://jobagent.duckdns.org`
- `NEXT_PUBLIC_WS_URL  = wss://jobagent.duckdns.org`

Redeploy the frontend. Also make sure `FRONTEND_URL` in `.env.prod` is your Vercel
URL (CORS already allows `*.vercel.app`).

---

## Operating it

| Task | Command |
|---|---|
| Update to latest code | `git pull && docker compose -f docker-compose.prod.yml up -d --build` |
| Restart a service | `docker compose -f docker-compose.prod.yml restart worker` |
| Tail logs | `docker compose -f docker-compose.prod.yml logs -f worker` |
| Stop everything | `docker compose -f docker-compose.prod.yml down` |
| Back up the DB | `docker compose -f docker-compose.prod.yml exec postgres pg_dump -U jobagent jobagent > backup.sql` |

## Notes / gotchas

- **Data lives in Docker volumes** (`pgdata`, `uploads`) on the VM — they survive
  `down`/`up`. Snapshot the boot volume in Oracle Console for real backups.
- **Migrating data off Railway**: `pg_dump` your Railway Postgres, then
  `psql ... < dump.sql` into the VM's Postgres (via `docker compose exec -T postgres psql`).
- **Railway files to retire** once this works: `railway.json`, `nixpacks.toml`,
  `Procfile` (Railway-specific — harmless to leave, or delete them).
- **ARM**: all images used are multi-arch and build natively on Ampere; no changes needed.
