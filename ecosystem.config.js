module.exports = {
  apps: [
    {
      name: "mapper-backend-new",
      cwd: "/home/uat_user/log-dashboard/mapper-new/mapper_new",
      script: "/home/uat_user/log-dashboard/mapper-new/mapper_new/venv/bin/python",
      args: "main.py",
      interpreter: "none",
      env: {
        PORT: "2528"
      },
      watch: false,
      autorestart: false,
      max_restarts: 10
    },
    {
      name: "mapper-frontend-new",
      cwd: "/home/username/mapper_new/frontend",
      script: "npm",
      args: "run preview -- --port 3005 --host",
      interpreter: "none",
      watch: false,
      autorestart: false,
      max_restarts: 10
    }
  ]
};