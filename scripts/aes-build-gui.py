#!/usr/bin/env python3
"""Build the Auto Event Choices GUI files from vanilla:
    mod/in_game/gui/aes_event_option_entry.gui
    mod/in_game/gui/decisionwindow.gui

Run after every EU5 update:
    python3 scripts/aes-build-gui.py

aes_event_option_entry.gui:
  Redefines only vanilla's `template event_option_entry` and `template expedition_event_option_entry`
  (from in_game/gui/eventwindow.gui) instead of replacing the whole file, so other mods that change
  the event window keep working:
  1. Reads vanilla in_game/gui/eventwindow.gui.
  2. Shrinks normal event option buttons to 482 px and inlines the cog toggle + auto-select
     widgets after the option buttons (normal and expedition events). Inlined, not via a
     template: widgets added through `using = <template>` never showed up in game.
  3. Scans vanilla events for options whose name ending (.a, .b, ...) is shared by another
     option of the same event and disables automation for exactly those (event, letter) pairs,
     since KeyEndWith can't tell them apart.
  4. Writes just the two patched templates. A mod's redefinition of a vanilla template wins over
     vanilla's (the same technique Glorp UI uses); the templates use no file-scoped @constants.

decisionwindow.gui:
  Copies vanilla and makes this mod's own one-option decisions (reset / suspend / resume)
  act instantly: the option is clicked as soon as the window opens. Decisions are matched by
  localized title (the window exposes no decision key); on a mismatch the window just shows.

Fails loudly if vanilla changed in a way the patch no longer fits.
"""
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.environ.get('EU5_GAME_DIR') or os.path.expanduser(
    '~/.local/share/Steam/steamapps/common/Europa Universalis V/game')
VANILLA_GUI = os.path.join(GAME, 'in_game/gui/eventwindow.gui')
VANILLA_DECISION_GUI = os.path.join(GAME, 'in_game/gui/decisionwindow.gui')
EVENTS_DIR = os.path.join(GAME, 'in_game/events')
OUT = os.path.join(REPO, 'mod/in_game/gui/aes_event_option_entry.gui')
# Older builds replaced the whole vanilla file; removed so it can't shadow other mods.
OLD_OUT = os.path.join(REPO, 'mod/in_game/gui/eventwindow.gui')
TEMPLATES = ('event_option_entry', 'expedition_event_option_entry')
OUT_DECISION = os.path.join(REPO, 'mod/in_game/gui/decisionwindow.gui')

# This mod's one-option decisions that should act without showing the decision window.
INSTANT_DECISIONS = (
    'aes_reset_auto_event_choices',
    'aes_suspend_auto_event_choices',
    'aes_resume_auto_event_choices',
)

LETTERS = 'abcdefghijklmnop'


# --- duplicate option-letter scan --------------------------------------------------------

def _block_end(text, start):
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def _option_names(body):
    names = []
    for om in re.finditer(r'(?<![A-Za-z_])option\s*=\s*\{', body):
        s = body.index('{', om.start())
        ob = body[s + 1:_block_end(body, s)]
        depth, name = 0, None
        for tok in re.finditer(r'[{}]|(?<![A-Za-z_])name\s*=\s*"?([A-Za-z0-9_.:-]+)', ob):
            if tok.group(0) == '{':
                depth += 1
            elif tok.group(0) == '}':
                depth -= 1
            elif depth == 0 and name is None:
                name = tok.group(1)
        names.append(name)
    return names


def duplicate_letters(events_dir):
    """{letter: sorted [event keys]} where 2+ options of the event end in .<letter>."""
    dups = defaultdict(set)
    for dp, _, fs in os.walk(events_dir):
        for f in fs:
            if not f.endswith('.txt'):
                continue
            text = open(os.path.join(dp, f), encoding='utf-8-sig', errors='replace').read()
            text = re.sub(r'#[^\n]*', '', text)
            for m in re.finditer(r'(?m)^([A-Za-z0-9_]+\.[0-9]+)\s*=\s*\{', text):
                s = text.index('{', m.start())
                names = _option_names(text[s + 1:_block_end(text, s)])
                counts = defaultdict(int)
                for n in names:
                    lm = re.search(r'\.([a-z])$', n or '')
                    if lm:
                        counts[lm.group(1)] += 1
                for letter, c in counts.items():
                    if c > 1 and letter in LETTERS:
                        dups[letter].add(m.group(1))
    return {k: sorted(v) for k, v in dups.items()}


# --- GUI expressions -----------------------------------------------------------------------

def _nest(fn, items):
    return items[0] if len(items) == 1 else f'{fn}({items[0]}, {_nest(fn, items[1:])})'


def option_id_expr(dups):
    """GUI string: the option's letter (a..p), or '' if it has none or is ambiguous."""
    parts = []
    for L in LETTERS:
        cond = f"EventOption.KeyEndWith('.{L}')"
        if dups.get(L):
            blocked = _nest('Or', [f"EqualTo_string(EventWindow.GetEventKey, '{e}')" for e in dups[L]])
            cond = f'And({cond}, Not({blocked}))'
        parts.append(f"AddTextIf({cond}, '{L}')")
    return _nest('Concatenate', parts)


def controls_block(indent, cog_x, opt, layout_comment):
    scope = ("GuiScope.SetRoot(GetPlayer.MakeScope)"
             ".AddScope('aes_event', MakeScopeFlag(EventWindow.GetEventKey))"
             f".AddScope('aes_option', MakeScopeFlag(Concatenate('opt_', {opt})))"
             ".End")
    is_auto = f"GetScriptedGui('aes_is_auto').IsShown({scope})"
    should_auto = f"GetScriptedGui('aes_should_auto').IsShown({scope})"
    toggle = f"GetScriptedGui('aes_toggle').Execute({scope})"
    lines = f'''# Auto Event Choices (generated by scripts/aes-build-gui.py, do not edit by hand).
# Must come after the option buttons so it draws on top. Options are identified by their name
# ending (.a .. .p via EventOption.KeyEndWith); options without one, or sharing it, get no cog.
# Auto-select: fires once the open event has this option remembered (and automation isn't suspended).
widget = {{
	size = {{ 0 0 }}
	state = {{
		name = aes_auto_select
		trigger_when = "[And(Not(EventWindow.IsOptionClicked), {should_auto})]"
		on_start = "[EventOption.Select]"
	}}
}}

# Cog toggle (vanilla automation cog style): 65% when not remembered; when remembered a larger, glowing,
# full-opacity cog is drawn over it.
# {layout_comment}
button_automation_shortcut = {{
	visible = "[Not(StringIsEmpty({opt}))]"
	position = {{ {cog_x} 5 }}
	size = {{ 26 26 }}
	alpha = 0.65
	tooltip = "AES_TOGGLE_TT"
	onclick = "[{toggle}]"
}}

button_automation_shortcut = {{
	visible = "[{is_auto}]"
	position = {{ {cog_x - 2} 3 }}
	size = {{ 30 30 }}
	alpha = 1
	glow = {{
		glow_radius = 6
		color = {{ 1.0 0.85 0.55 1.0 }}
		alpha = 0.9
	}}
	tooltip = "AES_TOGGLE_ON_TT"
	onclick = "[{toggle}]"
}}
'''
    return '\n'.join((indent + l) if l else '' for l in lines.split('\n'))


def replace_once(text, old, new, what, file='eventwindow.gui'):
    n = text.count(old)
    if n != 1:
        sys.exit(f'ERROR: expected exactly one {what} in vanilla {file}, found {n}. '
                 'Vanilla changed; update scripts/aes-build-gui.py.')
    return text.replace(old, new)


def read_vanilla(path):
    s = open(path, 'rb').read().decode('utf-8-sig')
    return s.replace('\r\n', '\n'), ('\r\n' if '\r\n' in s else '\n')


def write_mod(path, text, newline):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(text.replace('\n', newline))
    print(f'Wrote {path}')


def build_decisionwindow():
    s, newline = read_vanilla(VANILLA_DECISION_GUI)
    anchor = '''							tagtooltip_enabled = yes
							tooltip = "[historical_option|e]"
						}
'''
    # One widget per decision so switching between them (e.g. suspend, then resume) is a fresh
    # false -> true edge for trigger_when even though the option widgets are reused.
    autos = []
    for key in INSTANT_DECISIONS:
        autos.append(f'''
						# Auto Event Choices (generated by scripts/aes-build-gui.py): {key} acts instantly.
						widget = {{
							size = {{ 0 0 }}
							state = {{
								name = aes_instant_decision
								trigger_when = "[And(DecisionWindow.IsSingleOptionDecision, And(DecisionOptionItem.IsEnabled, EqualTo_string(DecisionWindow.GetTitle, Localize('{key}.title'))))]"
								on_start = "[DecisionOptionItem.OnClick]"
							}}
						}}
''')
    s = replace_once(s, anchor, anchor + ''.join(autos), 'historical-option marker in decisionwindow.gui', 'decisionwindow.gui')
    write_mod(OUT_DECISION, s, newline)


def main():
    s, newline = read_vanilla(VANILLA_GUI)

    dups = duplicate_letters(EVENTS_DIR)
    opt = option_id_expr(dups)

    # normal events: narrower option buttons, cog beside them
    old_normal = '''		button_regular_diamond = {
			visible = "[And(Not(EventOption.IsTooltipEmpty), EventOption.IsHighRisk)]"
			using = event_option_entry_button_normal
			blockoverride "button_regular_diamond_texture" {
				using = button_event_special_diamond_texture
			}
		}
		button_regular_diamond = {
			visible = "[And(Not(EventOption.IsTooltipEmpty), Not(EventOption.IsHighRisk))]"
			using = event_option_entry_button_normal
		}

		button_regular_diamond = {
			visible = "[EventOption.IsTooltipEmpty]"
			using = event_option_entry_button_empty_tt
		}
	}
}
'''
    new_normal = old_normal.replace('using = event_option_entry_button_normal\n',
                                    'using = event_option_entry_button_normal\n\t\t\tsize = { 482 36 }\n')
    new_normal = new_normal.replace('using = event_option_entry_button_empty_tt\n',
                                    'using = event_option_entry_button_empty_tt\n\t\t\tsize = { 482 36 }\n')
    new_normal = new_normal[:-len('\t}\n}\n')] + '\n' + controls_block(
        '\t\t', 486, opt, 'Option buttons above are shrunk to 482 px so the cog sits beside them.') + '\t}\n}\n'
    s = replace_once(s, old_normal, new_normal, 'event_option_entry option list')

    # expedition events: buttons are 490 px centred in 514, cog overlaps their right end
    old_exp = '''				blockoverride "expeditions_button_rest_size" {
					size = { 490 36 }
				}
			}
		}
	}
}

template event_window_category_icon {'''
    new_exp = old_exp.replace('''			}
		}
	}
}

template event_window_category_icon {''', '''			}
		}

''' + controls_block('\t\t', 482, opt, 'Expedition buttons are 490 px centred in 514, so the cog overlaps their right end.')
        + '''	}
}

template event_window_category_icon {''')
    s = replace_once(s, old_exp, new_exp, 'expedition_event_option_entry tail')

    header = ('# Auto Event Choices (generated by scripts/aes-build-gui.py from vanilla eventwindow.gui,\n'
              '# do not edit by hand). Overrides only these vanilla templates.\n\n')
    blocks = []
    for name in TEMPLATES:
        m = re.search(rf'(?m)^template {name} \{{', s)
        if not m:
            sys.exit(f'ERROR: template {name} not found in vanilla eventwindow.gui. '
                     'Vanilla changed; update scripts/aes-build-gui.py.')
        block = s[m.start():_block_end(s, s.index('{', m.start())) + 1]
        if '@' in block:
            sys.exit(f'ERROR: template {name} now uses an @constant, which is file-scoped and would be '
                     'undefined in the override file. Update scripts/aes-build-gui.py to copy it.')
        blocks.append(block)
    write_mod(OUT, header + '\n\n'.join(blocks) + '\n', newline)
    if os.path.exists(OLD_OUT):
        os.remove(OLD_OUT)
        print(f'Removed {OLD_OUT}')
    blocked = sum(len(v) for v in dups.values())
    print(f'Blocked {blocked} ambiguous (event, letter) pairs across {len({e for v in dups.values() for e in v})} events')

    build_decisionwindow()


if __name__ == '__main__':
    main()
