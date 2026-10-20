# Security

The gateway talks to local engines over 127.0.0.1 by default, refuses non-loopback hosts unless a
provider sets `allow_remote = true`, and keeps API keys in environment variables, never in the
config file.

If you find a vulnerability, please do not open a public issue. Use GitHub's private
vulnerability reporting on this repository ("Security" tab, "Report a vulnerability"). You will
get an answer within a week.
