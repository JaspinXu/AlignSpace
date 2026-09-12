# Single-instance deployment

Target: existing Ubuntu Lightsail instance, 54.255.93.19. Public trial hostname: `54-255-93-19.sslip.io`. This temporary DNS name depends on the instance retaining its public IP.

The native deployment uses `/home/ubuntu/alignspace`, its own Python virtualenv and `alignspace.service`. It does not modify Hermes configuration. Caddy terminates HTTPS and proxies to localhost:8010. Only TCP 80 and 443 need public access for the app; keep existing SSH access.

## Current temporary HTTPS port

Trial URL: https://54-255-93-19.sslip.io:80/. TCP 443 is blocked and the participant cannot change the managed Lightsail firewall. A publicly trusted certificate was initially issued through HTTP-01 on port 80; Caddy now serves TLS on that already-open port. Browser and external TLS verification passed without bypassing certificate validation.

The certificate expires **11 December 2026, 17:25:16 UTC**. Do not assume automatic renewal works with this fallback: ACME validation expects HTTP on 80 or TLS on 443. Before renewal, ask the organiser to permit 443, restore a standard hostname Caddy site with default ports and automatic HTTP redirect, then validate reload and public health. Keep application port 8010 private. This temporary configuration is for the trial, not a permanent renewal strategy.

## Install/update

1. Transfer only `app/`, `schemas/`, `deploy/`, and `requirements.txt`; exclude local data, caches and secrets from the archive.
2. Transfer `.env` separately over SSH, set mode 600. Never put it in Git or the public web directory.
3. Create `.venv` with `python3 -m venv .venv`, install `requirements.txt`.
4. Copy `deploy/alignspace.service` to `/etc/systemd/system/`; review paths if using a different directory.
5. Copy `deploy/Caddyfile` to `/etc/caddy/Caddyfile`, adjusting the hostname if required. Verify DNS resolves to the instance and Lightsail permits TCP 80/443.
6. Run `sudo systemctl daemon-reload`, `sudo systemctl enable --now alignspace`, `sudo systemctl reload caddy`.

The systemd unit sets Secure cookies. Local HTTP development keeps this off. Run a single application process on the small instance. Caddy supplies forwarded HTTPS headers and Uvicorn trusts only the loopback proxy.

## Health and troubleshooting

```sh
systemctl is-active alignspace caddy
curl -f http://127.0.0.1:8010/health
curl -f https://54-255-93-19.sslip.io:80/health
sudo journalctl -u alignspace -n 30 --no-pager
sudo journalctl -u caddy -n 30 --no-pager
```

If local health works but public HTTPS times out, check the Lightsail IPv4 firewall for TCP 443. A certificate can be issued via port 80 even when 443 is blocked. Never bypass certificate verification as a deployment acceptance check.

## Persistence and rollback

SQLite database, membership hashes and analysis request ledger persist in `data/alignspace.db`; reference images persist in `data/uploads/`. Restarting the service does not reset quotas or participant access. Back up the database using SQLite's backup API and copy uploads while writes are stopped or coordinated. Do not copy a live WAL database as a single file.

Before an update, retain the previous code archive. To roll back code, stop `alignspace`, restore that archive, reinstall its dependencies if changed, and restart. Preserve `data/` and `.env`. Current migrations only add tables; future destructive migrations require a separate backup/recovery plan.

## Known boundaries

- No account recovery, session revocation UI, automated retention/deletion or external identity verification.
- Membership is possession of an HttpOnly cookie; invitations are single-use and expire after 24 hours.
- Rate limits reserve analysis requests, not exact currency. Track real team usage in `#ai-token-tracking`.
- The current competition endpoint passes text inference but failed the known-image probe. Image mode is disabled.
- Native systemd is the deployed path. Docker configuration is an alternative; it has not been used on this instance.
