# Desktop Pets

Little animated companions for Windows 10 or 11. Requires Python 3.10 or newer
with Tkinter. The pets app itself uses only Python's standard library.

Double-click **run_pets.bat**, or run `py -3 desktop_pets.py` from this folder.
To add Start Menu and optional desktop shortcuts, run `py -3 install_app.py`.
Keep this folder in place after installing. Re-run the installer to update older
shortcuts to the currently selected Python version.

## Pets & play

- **Surprise pet** adds a random bird, fish, cat, blob, bug, or ghost (up to 12).
  Pets have different palettes, names, personalities, sizes and accessories.
- **Make a pet** recognizes descriptions such as `a sleepy purple cat with a crown`,
  `a tiny golden koi with sparkles`, or `a fast blue ghost with glasses and a trail`.
  It uses local keyword rules; it is instant and needs no API key. Unknown details
  don't add new shapes. Blank descriptions create a surprise.
- Give everyone treats, start a dance party, take a nap, trigger zoomies, or follow
  the cursor for 15 seconds. **Wander** ends an activity. Right-click a pet to play
  with that pet alone. Click to boop; drag to reposition.
- Pets blink and occasionally do something on their own. Turn off **Little surprises**
  to keep them wandering. Sounds start off and can be enabled separately.
- Pause, hide, change flight speed, or change whether pets stay above other windows.
  Pause and hide also stop activity timers. Minimize the panel to keep pets flying;
  closing it quits.

## AcumenAI

The **Ask Acumen** tab uses the existing AcumenAI local bridge for actual questions,
math, and research. Questions and Acumen commands are sent unchanged; source text
is preserved in answers. Pet creation uses local rules because Acumen's bridge
is a question-answering service, not a pet-design model. DeepSeek is no longer required.

### One-click start

1. Keep your working `AcumenAI-2.0` installation beside this folder, or set
   `ACUMEN_HOME` to its folder. Its dependencies and `config.yaml` must already work.
2. Open **Ask Acumen** and click **Start Acumen**.
3. Wait for **Connected to Acumen**, then type a question and click **Send**
   (or press Ctrl+Enter). Try `Calculate 6*7`.

The app uses Acumen's `.worker-venv`, `.venv`, or `venv` when available, then the
app's Python as a fallback. It starts the bridge hidden on `127.0.0.1`, pairs
automatically, and stops only the bridge it started when you quit Desktop Pets.
That bridge uses Acumen's configured knowledge directory. Acumen may access the
internet to answer research questions, according to its own configuration.

### Connect to a running bridge

1. Start your Acumen bridge as usual. For this checkout, from `AcumenAI-2.0`:
   `.\.worker-venv\Scripts\python.exe bridge.py`
2. In **Ask Acumen**, enter its local address (default `http://127.0.0.1:8765`).
3. Paste the pairing token shown by Acumen and click **Connect**.

You can also set `ACUMEN_BRIDGE_URL` and `ACUMEN_TOKEN` before launching.
The token stays in memory; Desktop Pets never writes it into its settings or logs.
An externally started Acumen bridge keeps running when you close the pets app.
**Open Acumen** opens the local website for its full learning and knowledge controls.
Use Acumen's own controls to review/save learning before stopping its bridge.

Requests run in the background so pets and controls remain responsive. Failed
questions remain available through **Retry last**, and typing a new draft while
waiting never gets overwritten by the previous answer. You can select/copy answers
or use **Copy answers** to copy the conversation.

## Saved settings and troubleshooting

Pets, play preferences, bridge address and unfinished drafts are saved in
`%LOCALAPPDATA%\Desktop Pets\settings.json`. Existing pet designs are retained.
Conversations are kept only for the current pets-app session; Acumen manages its
own session data. Errors are logged to `%LOCALAPPDATA%\Desktop Pets\app.log`.

- **A server already uses this port:** paste that Acumen server's token and Connect,
  or choose a different local port before Start Acumen.
- **Pairing token not accepted:** restarting Acumen may change its token. Paste the
  current token and reconnect. Tokens are not recovered from another app's files.
- **Could not find/start Acumen:** check `ACUMEN_HOME`, its Python environment and
  config. Run its `bridge.py` manually to see its startup error, then Connect.
- **Long or failed answer:** check the Acumen server, then Retry last. Pets still work
  without Acumen running.
- **Wrong Python opens:** install a current Python with the Windows Python launcher,
  then use `run_pets.bat` or `py -3 desktop_pets.py`. Reinstall shortcuts if needed.

## Validation

Run `py -3 -m unittest discover -s tests -v`. GUI tests create real Tk widgets and
temporary settings; they don't overwrite your saved pets. The optional real Acumen
smoke test is `py -3 scripts/check_acumen.py`; it uses isolated temporary knowledge
storage and an unused local port, then shuts down its owned server.

Main files: `desktop_pets.py` (UI and animation), `pet_ai.py` (local pet designs),
`acumen_client.py` (authenticated local API), `acumen_bridge.py` (owned bridge
startup), and `launch_pets.pyw` / `run_pets.bat` (launchers).
