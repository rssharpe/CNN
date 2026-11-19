# CCN Development Workflow: VS Code, Copilot, and GitHub

This guide describes the workflow used to build and package the Cable Counter
Network (CCN) application. It is written for someone learning Python and Git.

The [PDF version](./CCN_VSCode_Copilot_Workflow.pdf) predates the DEV21 update;
use this Markdown version for the current working revision.

## 1. Open the project in VS Code

1. Open the `C:\CNN` folder in Visual Studio Code.
2. Open the integrated terminal with **Terminal > New Terminal**.
3. Keep the active application source clear:
   - `CCN_V10_0_DEV19.py` is the frozen demo baseline.
   - `CCN_V10_0_DEV20.py` is the earlier multi-COM and TCP version.
   - `CCN_V10_0_DEV21.py` is the working Tension Integration revision.
4. To run DEV21 from the project folder:

   ```powershell
   cd C:\CNN
   python .\CCN_V10_0_DEV21.py
   ```

   If `python` is not recognized, try `py .\CCN_V10_0_DEV21.py`.

This project used **Visual Studio Code with Copilot Chat**. VS Code is a
different product from the full Visual Studio IDE, even though both products
can have Copilot chat features.

## 2. Ask Copilot to work directly in the project

When Copilot Chat has the `C:\CNN` workspace open, it can inspect and edit the
actual files. That is more reliable than copying a long source file into chat
or asking Copilot to recreate the whole program.

A useful request describes:

- The exact file or screen involved.
- What should change and what should stay the same.
- Whether a control should be available in server and client mode.
- How the change should be checked.

For example:

> In `CCN_V10_0_DEV21.py`, add a View-menu toggle for the Playback Source
> panel. Make it visible by default. Hiding it must not stop playback. Update
> the user manual and run a focused test.

For a larger or unclear change, ask Copilot to inspect the relevant code and
explain its approach before editing. For a small, clear change, Copilot can
inspect, make a focused edit, and then verify it.

## 3. Make small, reviewable changes

The usual coding loop is:

1. Search for the relevant function or widget.
2. Read its surrounding code and related call sites.
3. Edit only the necessary code and directly related documentation.
4. Review the changed files and confirm unrelated changes were not included.
5. Run a focused syntax check or test.
6. Launch the application or perform the relevant hardware/network test when
   possible.

Prefer focused changes to replacing or regenerating the entire application.
Preserve `ccn_config.json`, logs, recordings, and other existing local data.
Do not overwrite user changes just to make a test easier.

Useful VS Code actions:

- **Ctrl+P** opens a file by name.
- **Ctrl+F** searches the current file.
- **Ctrl+Shift+F** searches the project.
- **Terminal > New Terminal** opens another terminal, useful for running a
  server and client as separate CCN windows.
- The Source Control view shows changed and untracked files before a commit.

## 4. Tools used for coding and verification

| Tool | How it was used |
|---|---|
| VS Code workspace and Copilot Chat | Read and edit the project files directly; discuss requirements and review results. |
| Pylance | Check Python syntax and use Python-aware diagnostics where useful. |
| `rg`, file views, and Git | Find relevant code, inspect context, and review changed files. |
| PowerShell | Run focused Python/Qt checks, inspect Windows paths, and build the app. |
| PyInstaller | Package DEV21 as a single-file, windowed Windows executable. |
| Inno Setup | Build the per-user Windows installer. |
| Git and GitHub remote | Track milestones and back up selected source files to `rssharpe/CNN`. |

No separate background coding agents or GitHub Copilot coding agent were used
for these changes. The workspace-enabled Copilot assistant made the edits
directly. Pylance and the command-line tools were used for verification; they
are tools, not additional coding agents.

## 5. Test the application

Use the smallest test that verifies the change, then run broader tests when
needed.

### Source and interface checks

- Run a Pylance syntax check after Python edits.
- For a UI change, an offscreen Qt check can confirm that a menu action exists,
  toggles the expected widget, and leaves unrelated controls unchanged.
- Avoid test scripts that write to the real config or log files. Mock serial
  port discovery and serial connections when testing UI code without hardware.

### Serial testing

The test setup used the SS Serial Generator and two USB-to-RS-232 adapters
connected through a null-modem link. The generator and CCN must use opposite
COM endpoints. A virtual COM pair is another option when multiple independent
streams are needed.

### TCP testing

For a same-PC test, start a simulated source on one DEV21 window, start its TCP
server, then connect a second DEV21 window to `127.0.0.1` on port `8765`.
The client is view-only. A real second-PC test should be treated as a separate
validation; it was not performed as part of the Windows package build.

Use TCP only on a trusted LAN or VPN. DEV21's TCP service has no login or
encryption; do not expose it directly to the public internet.

## 6. Build the Windows executable and installer

From a PowerShell terminal in `C:\CNN`, run:

```powershell
.\build_ccn_v1.ps1
```

The script uses PyInstaller and Inno Setup to create:

- `dist\CSA Cable Counter Display V3.exe`
- `dist\installer\CSA_Cable_Counter_Display_V3_Setup.exe`

The script packages DEV21 using V3 output names. The installed application
identity remains `CSA Cable Counter Display V1` for compatibility with the
earlier installer.

The manual and CSA logo are bundled with the executable. The installed
application stores its configuration, logs, and recordings under:

```text
%LOCALAPPDATA%\CSA\Cable Counter Display V1
```

The installer is per-user and does not require administrator privileges. The
application and installer are not code-signed, so Windows SmartScreen may show
a warning.

## 7. Use Git and GitHub for safe backups

Git is the local version history. GitHub is the remote backup. A safe backup
uses a named milestone commit and pushes only the intended files.

Before staging:

```powershell
git status --short
```

Stage specific project files rather than using `git add .`. Review what will
be committed:

```powershell
git diff --cached --stat
git diff --cached --check
git diff --cached --name-only
```

Keep local configuration and test data out of GitHub unless there is a specific
reason to share them. In particular, review before adding:

- `ccn_config.json`
- CSV files in `logs`
- raw input files in `recordings`
- temporary build directories such as `build`
- compiled EXE and installer files in `dist`
- personal notes, workspace files, or credentials

The compiled EXE and installer can be rebuilt from the source and build script.
Keep them out of normal source commits unless you intentionally want to store
large binaries in the repository or publish them as release downloads.

Commit only after the selected files and diff are reviewed. Push to the intended
branch, not automatically to `main`. For example, the current backup plan uses
`origin/temp`:

```powershell
git push origin temp
```

Before committing, check whether a suitable Git author name and email are
configured. To configure identity locally for this repository, use your
GitHub profile name and email (a GitHub noreply email is fine):

```powershell
git config --local user.name "Your GitHub name"
git config --local user.email "your GitHub email or noreply address"
```

Then review and commit only the agreed files. Do not copy an example email
literally.

## 8. Suggested prompt for continuing in a new chat

> We are working in `C:\CNN`. Keep DEV19 as the frozen demo baseline and use
> DEV21 as the working version. Inspect the existing code before editing, make
> a small focused change, preserve local config/logs/recordings, update directly
> related documentation, and run a focused test. Show me which files changed
> and any commands or physical tests still needed.
