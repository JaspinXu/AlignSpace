#!/usr/bin/env bash
# Read-only snapshot of a running AlignSpace deployment, for the verification report.
# Prints service state, hardening, TLS, public checks, configured limits and aggregate usage counts.
# It never prints secret values: only the names of the non-secret limit settings and the .env file mode.
#
#   ssh -i key.pem ubuntu@<ip> "HOST=<ip>.sslip.io bash -s" < scripts/capture_deployment_evidence.sh
set -u
H=${HOST:-54.255.93.19.sslip.io}
BASE=${ALIGNSPACE_HOME:-$HOME/alignspace}
echo "## captured_at_utc"; date -u +%Y-%m-%dT%H:%M:%SZ
echo "## os"; . /etc/os-release; echo "$PRETTY_NAME, kernel $(uname -r)"
echo "## resources"; echo "vcpus=$(nproc)"; free -m | awk 'NR==2{print "memory_total_mb="$2", used_mb="$3}'; df -h / | awk 'NR==2{print "disk_size="$2", used="$3", avail="$4}'
echo "## uptime"; uptime -p; echo "booted_at=$(uptime -s)"
echo "## instance_metadata"
T=$(curl -s -m 3 -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60" || true)
for k in placement/region placement/availability-zone instance-type; do printf '%s=' "$k"; curl -s -m 3 -H "X-aws-ec2-metadata-token: $T" "http://169.254.169.254/latest/meta-data/$k" || printf 'n/a'; echo; done
echo "## release"; echo "current=$(readlink -f "$BASE/current")"; ls -1 "$BASE/releases" | sed 's/^/release=/'
echo "## services"
for s in alignspace caddy; do echo "$s enabled=$(systemctl is-enabled $s) active=$(systemctl is-active $s) since=$(systemctl show $s -p ActiveEnterTimestamp --value) restarts=$(systemctl show $s -p NRestarts --value)"; done
echo "## alignspace_unit_hardening"
systemctl show alignspace -p User -p ProtectSystem -p ProtectHome -p NoNewPrivileges -p PrivateTmp -p UMask -p Restart --no-pager
echo "## listening_sockets"
ss -ltn | awk 'NR==1 || $4 ~ /:(80|443|8010)$/ {print $1, $4}'
echo "## tls_certificate"
echo | openssl s_client -connect 127.0.0.1:443 -servername "$H" 2>/dev/null | openssl x509 -noout -subject -issuer -dates
echo "## public_https_checks"
curl -s -m 15 -o /dev/null -w "GET / -> http=%{http_code} ssl_verify=%{ssl_verify_result} time=%{time_total}s\n" "https://$H/"
printf 'GET /health -> '; curl -s -m 15 "https://$H/health"; echo
printf 'GET /api/runtime -> '; curl -s -m 15 "https://$H/api/runtime"; echo
curl -s -m 15 -o /dev/null -w "GET http://$H/health -> http=%{http_code} redirect=%{redirect_url}\n" "http://$H/health"
echo "## security_headers"
curl -s -m 15 -D - -o /dev/null "https://$H/" | grep -iE '^(content-security-policy|x-content-type-options|referrer-policy|strict-transport-security|x-frame-options):' | cut -c1-160
echo "## configured_limits"
grep -E '^ALIGNSPACE_(ANALYSIS_MODE|PROJECT_RUN_LIMIT|DAILY_RUN_LIMIT|SECURE_COOKIES|ALLOW_IMAGES)=' "$BASE/shared/.env"
echo "env_file_mode=$(stat -c %a "$BASE/shared/.env") owner=$(stat -c %U "$BASE/shared/.env")"
echo "## usage_ledger_aggregates"
DB="$BASE/shared/data/alignspace.db" python3 - <<'PY'
import json, os, sqlite3, time
db = sqlite3.connect('file:' + os.environ['DB'] + '?mode=ro', uri=True)
q = lambda s, *a: db.execute(s, a).fetchone()[0]
print('projects=', q('SELECT COUNT(*) FROM projects'))
print('audit_events=', q('SELECT COUNT(*) FROM audit_events'))
rows = db.execute('SELECT status, metrics_json FROM analysis_runs').fetchall()
modes = {}
for status, m in rows:
    mode = (json.loads(m or '{}') or {}).get('mode', 'unknown')
    modes[(status, mode)] = modes.get((status, mode), 0) + 1
print('analysis_runs_total=', len(rows))
for (status, mode), n in sorted(modes.items()):
    print(f'analysis_runs[{status},{mode}]=', n)
print('analysis_runs_last_24h=', q('SELECT COUNT(*) FROM analysis_runs WHERE created>?', time.time() - 86400))
PY
echo "## backups"; ls -1d "$HOME"/alignspace-backup-* 2>/dev/null
echo "## end"
