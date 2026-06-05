import os

# Railway injects PORT as an env var; read it in Python so there is no
# shell-expansion dependency (which was sending the literal "$PORT").
port = os.getenv("PORT", "8000")
bind = f"0.0.0.0:{port}"
workers = 2
timeout = 120
