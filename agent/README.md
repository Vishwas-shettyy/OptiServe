# OptiServe agent

A single-file collector. Every 10 seconds it sends CPU, memory, network in/out (kbps) and disk usage to your OptiServe backend. It can also send requests per minute if your app exposes a counter.

- **Needs:** Python 3.9+ with `psutil` and `requests`. Tested targets: Amazon Linux 2023 and Ubuntu 22.04+.
- **On EC2:** it reads the instance id, instance type and region through IMDSv2, so its metrics link to the AWS record. The Auto Scaling group name is read too if instance metadata tags are enabled. On other machines the hostname is used as the id.
- **Offline:** it buffers up to 10 minutes of samples. Retries back off from 10 s up to 5 min, and it respects `Retry-After` on 429.
- **Secrets:** the token is never logged.

## 1. Create a token

In OptiServe, open **Settings → Agent tokens → New token**. You can also call the API with an admin session: `POST /api/agent-tokens {"label": "web-1"}`.

The token (`osa_...`) is shown only once. OptiServe stores only its hash.

## 2. Install as a service (Linux, systemd)

```bash
sudo bash install.sh https://optiserve.example.com osa_xxx [http://127.0.0.1:8000/metrics]
# or in one line, without cloning:
curl -fsSL https://raw.githubusercontent.com/Vishwas-shettyy/OptiServe/v2/agent/install.sh \
  | sudo bash -s -- https://optiserve.example.com osa_xxx
```

The installer:
- puts the agent in `/opt/optiserve-agent` with its own virtualenv;
- writes the settings to `/etc/optiserve-agent.env` (mode 600);
- starts the `optiserve-agent` systemd service.

Logs: `journalctl -u optiserve-agent -f`.

## 3. Or run it by hand (any OS)

```bash
pip install psutil requests
python3 optiserve_agent.py --url http://localhost:8000 --token osa_xxx
```

Every flag also has an environment variable:

| Flag | Environment variable |
|---|---|
| `--url` | `OPTISERVE_URL` |
| `--token` | `OPTISERVE_TOKEN` |
| `--requests-url` | `OPTISERVE_REQUESTS_URL` |
| `--interval` | `OPTISERVE_INTERVAL` |

## Requests per minute (optional)

`--requests-url` must point to a local URL that returns either `{"requests_per_min": 42}` or a plain number.

## Revoke

Delete the token in Settings (`DELETE /api/agent-tokens/{id}`). The backend then rejects that agent with 401.

To stop the agent and uninstall it:

```bash
sudo systemctl disable --now optiserve-agent
sudo rm -rf /opt/optiserve-agent /etc/optiserve-agent.env /etc/systemd/system/optiserve-agent.service
```
