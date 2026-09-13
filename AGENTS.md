# FlaskOllama Agent Instructions

## Scope

These instructions apply to the FlaskOllama knowledge-base repository.

## Project topology

This project is developed across one Windows computer and two Linux workstations:

- Local Windows computer: `DOOROCEAN`, user `xulin`.
- Local FlaskOllama checkout: `V:\FineTuning\FlaskOllama`.
- VLLM/A6000 workstation: Tailscale `100.81.248.84`, SSH user `ubuntu`, repository `/home/ubuntu/Projects/202509_CRRC_MCP`, service port `8008`.
- FlaskOllama/knowledge-base workstation: Tailscale `100.91.253.77`, SSH user `crrc`, repository `/home/crrc/PycharmProjects/FlaskOllama`, service port `8550`.

The externally reachable frontend uses the VLLM workstation as the master/API entry point. VLLM forwards knowledge-base requests to this FlaskOllama service over the company network. FlaskOllama is the knowledge-base slave and is not expected to be directly exposed to the external frontend. The VLLM and FlaskOllama repositories are independent Git repositories and must be synchronized separately through GitHub.

## Fast environment identification

At the beginning of every task, identify the current machine and repository before using SSH or editing files:

```powershell
$env:USERNAME
$env:COMPUTERNAME
git rev-parse --show-toplevel
git branch --show-current
```

When the result is the expected Windows checkout (`xulin` / `DOOROCEAN`), edit locally first and synchronize Linux workstations through Git. Do not assume that a shell is running on either workstation. If the identity, checkout, or repository does not match the documented environment, stop remote operations and verify the target.

## Repository and remote execution

- GitHub repository: `https://github.com/wudaowudaowudao/FlaskOllama.git`
- Keep source changes in the Windows checkout; use the remote workstation only for bounded execution and integration tests.
- Before remote writes, inspect the target repository status and preserve pre-existing modifications and untracked files.
- Never expose passwords, private keys, API tokens, or VPN credentials. The SSH key is outside the repository at `~/.ssh/id_ed25519_crrc_workstation`.
- The Flask service normally runs from `app.py` on `0.0.0.0:8550`; stop and restart it only when the task explicitly requires code deployment or testing.
