# Windows

Part of the edgible-cards skill: read [SKILL.md](SKILL.md) first, and its [Rules](SKILL.md#rules) apply here. Read this file whenever the person is on Windows, whether your shell is PowerShell, cmd or WSL.

## The simplest way: run the AI tool inside WSL

Open the Ubuntu distro that runs (or will run) the Edgible device, and start the AI tool there. It then behaves as on Linux, and everything in this skill applies as written. Setting WSL up is in [WSL2 on Windows](setup.md#wsl2-on-windows). Suggest this first.

## If the tool runs in PowerShell (or cmd)

This skill's commands are written for bash (`grep`, `$(…)`, `command -v`), and many fail or get rewritten badly in PowerShell. Connect the organisation's connector instead, and work through its tools where they cover the task:

1. **Make the offer** as SKILL.md says: your first reply, nothing else.
2. **After the yes, find the connector.** Through the WSL distro that holds the device (below), `edgible app list` shows an `mcp-signin` app. Its address is `https://<mcp-signin hostname>/mcp`: the app on `none`, never the `-login` one.
3. **Add it** as a remote server named `edgible-remote`, with the command for the tool in [mcp.md](mcp.md#add-a-server-by-tool). In GitHub Copilot CLI: `copilot mcp add --transport http edgible-remote <address>`, then `/mcp auth edgible-remote`. The person signs in with Edgible in the browser, in a private window, and approves. Then restart the tool.
4. **Say what it can change.** That depends on the connector's own device list (`EDGIBLE_MCP_DEVICES`), which is set where the connector runs.
5. **With no connector in the organisation,** say so, offer to set one up from the edgible-connector card as a separate step ([mcp.md](mcp.md#use-an-mcp-server-from-claude-anywhere)), and meanwhile run commands through `wsl.exe -d <distro> --`, or suggest WSL as above. If the tool cannot complete the sign-in, say so and ask before trying anything else.

Do not set up `edgible-local` from PowerShell. The local server is tested on macOS and Linux only: with the Windows `node` it calls the Windows-side `edgible`, which is often old and not signed in, and its CLI tools fail with "Connection closed".

## Which `edgible`, and which distro

A Windows computer can hold more than one `edgible`. The one that matters is signed in, in the WSL distro that runs the Edgible agent, next to the device and its Docker. `wsl.exe -l -v` lists the distros (`*` is the default). Find the right one with `wsl.exe -d <distro> -- edgible whoami`, then run `edgible` and `docker` through `wsl.exe -d <distro> --`, and stop probing the others. Say which one you used, and name the Edgible device, not only the distro.

An `edgible` on the Windows side that is not signed in is no reason to run `edgible auth login`: that makes a second identity apart from the device. A WSL distro that runs the Edgible agent counts as "Edgible is set up on this machine"; a Windows-side `edgible` alone does not.

## The status page

`status-page.py` writes it inside WSL, so its `file://` address is a Linux path that a Windows browser cannot open. Also give the Windows form, which `wslpath -w <the file>` prints (it looks like `\\wsl.localhost\<distro>\home\<name>\.edgible\status.html`), for the person to paste into File Explorer or the browser's address bar.

## Also on Windows

- **Keeping it on:** WSL stops when its last session ends. See [Is the machine always-on?](setup.md#is-the-machine-always-on).
- **Line endings:** card-kit and cards carry a `.gitattributes` that keeps LF. A clone made before it landed shows many files as modified (line endings only) when read from WSL: a fresh clone fixes it.
- **Node and npm:** inside WSL, check that `npm` is the Linux one (`which npm` is not under `/mnt/c`); a Windows `npm` that leaks in installs the Windows build of a tool.
