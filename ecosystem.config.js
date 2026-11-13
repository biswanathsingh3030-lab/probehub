// pm2 config for the ProbeHub API (hub).
//   pm2 start ecosystem.config.js      # start
//   pm2 logs probehub-hub              # logs
//   pm2 restart probehub-hub           # after code/.env changes
//   pm2 save                           # keep it across reboots (with `pm2 startup`)
// DB credentials, host and port come from .env at the repo root (loaded by hub/config.py).
const path = require("path");

module.exports = {
  apps: [
    {
      name: "probehub-hub",
      cwd: __dirname,
      script: path.join(__dirname, ".venv/bin/python"),
      args: "-m hub",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
      min_uptime: "10s",
      kill_timeout: 5000,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
