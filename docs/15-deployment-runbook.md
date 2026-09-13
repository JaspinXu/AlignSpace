# Deploy to an Ubuntu Lightsail instance

Develop locally, then run the code on the organiser-provided medium instance for assessment. The steps below use an example directory; adjust the path and SSH identity to the instance you receive.

## Install and run

1. Connect to the instance over SSH.
2. Clone the repository, or transfer the application code using SCP/SFTP. Keep local databases, uploads and secrets out of the code archive.
3. In the project directory, install the runtime:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

4. Edit the backend `.env` on the instance to set the gateway URL, model and API key. For subsequent updates, preserve the existing `.env`.
5. Start the application:

```sh
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010
```

This foreground command is for verification and ends when its terminal is closed. For an assessment deployment, use the instance's process manager to keep the same application command running after SSH disconnects.

## Verify from your computer

In another local terminal, forward a local port through SSH:

```sh
ssh -i /path/to/private-key.pem -L 8010:127.0.0.1:8010 ubuntu@INSTANCE_IP
```

Keep this connection open and visit http://127.0.0.1:8010 in your local browser. If that local port is occupied, change the first 8010 to an available port and use it in the browser URL. This tests the application running on the instance using its existing SSH access.

The tunnel is for your own testing. Arrange the judge-facing access method on the target instance when preparing the assessment; a local tunnel is not a public demo URL.

On the instance, check health with:

```sh
curl -f http://127.0.0.1:8010/health
```

## Updates and data

Pull the next revision or upload changed code, install dependencies if they changed, and restart the application. Pushing to GitHub does not automatically update the instance.

Preserve `.env`, `data/alignspace.db` and `data/uploads/` across updates. SQLite holds projects, participant access and analysis quotas; uploads hold private references. Back up SQLite through its backup API or stop writes before copying database files. Retain the previous code revision for rollback.

The generic `ALIGNSPACE_SECURE_COOKIES` setting remains available: leave it false for local HTTP verification and enable it when serving the application over HTTPS. Configure the actual assessment hosting environment separately.
