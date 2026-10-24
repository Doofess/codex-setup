# MCP presets

Project-scoped MCP servers. Nothing here loads globally. Copy a preset's tables
into the repo's `.codex/config.toml`, delete what that project does not use, and
trust the project so Codex loads it. Secrets come from environment variables
named in `env_vars`, never from the file.

| Preset | For | Servers |
| --- | --- | --- |
| `web.toml` | Web apps | Supabase, Neon, Prisma, DBHub (any SQL), Vercel, Sentry, PostHog |
| `cluster.toml` | Cluster backend | Kubernetes (read-only), Terraform, Grafana, Sentry, DBHub, docs.rs |

HTTP servers sign in with OAuth on first use: `codex mcp login <name>`.
DBHub reads its connection string from the `DSN` environment variable; point it at a read-only role.

CLIs to install before the cluster project: `winget install Docker.DockerDesktop Kubernetes.kubectl Helm.Helm`.
