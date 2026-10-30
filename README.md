# Auto Event Choices

A Europa Universalis V mod (game version 1.4.*). Click the cog next to an event option and that option is chosen automatically every time the event fires again in this save. Works on normal and expedition events. Player-facing description: [`workshop.txt`](workshop.txt) (Steam BBCode).

## Layout

| Path | What |
|------|------|
| `mod/` | The mod itself; this folder is what goes into the EU5 `mod/` directory and gets uploaded to the Workshop |
| `scripts/aes-build-gui.py` | Generates `mod/in_game/gui/aes_event_option_entry.gui` and `mod/in_game/gui/decisionwindow.gui` from vanilla |
| `workshop.txt` | Steam Workshop description |

## After every EU5 update

```bash
python3 scripts/aes-build-gui.py
```

The two `.gui` files are generated; never edit them by hand. The script reads the game from `~/.local/share/Steam/steamapps/common/Europa Universalis V/game`; set `EU5_GAME_DIR` to point it elsewhere. It fails loudly if vanilla changed so the patch no longer fits.

## How it works

- `aes_event_option_entry.gui` redefines only vanilla's `template event_option_entry` and `template expedition_event_option_entry` (from `eventwindow.gui`, which is not replaced), so other mods that change the event window stay compatible. Option buttons are shrunk to 482 px and the cog + auto-select widgets are inlined after them. Inlined rather than pulled in from a new template: widgets added through `using = <new template>` never showed up.
- Options are identified by their name's letter ending (`.a`–`.p`, tested with `EventOption.KeyEndWith`; the GUI has no option-key getter). Options without such an ending get no cog. The generator scans vanilla events and blocks (event, letter) pairs shared by two or more options. Position is not used, since options shift when some are hidden by triggers.
- Clicking a cog stores `flag:<event key> → flag:opt_<letter>` in the country variable map `aes_choices` via scripted GUIs (`aes_toggle`, `aes_is_auto`), so choices persist per save.
- A `trigger_when` state calls `EventOption.Select` when `aes_should_auto` is true (remembered, and no `aes_suspended` variable), guarded by `Not(EventWindow.IsOptionClicked)`.
- Decisions `aes_reset_…` (clear the map), `aes_suspend_…` / `aes_resume_…` (toggle `aes_suspended`). `decisionwindow.gui` makes these one-option decisions act instantly (matched by localized title); it is a whole-file replacement because the patched spot isn't inside a template.
- Localization ships for all 11 languages (English text for now; translations welcome).
