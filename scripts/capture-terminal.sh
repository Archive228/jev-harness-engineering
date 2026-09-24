#!/bin/sh
# Capture real screenshots of the JEVIS agent running in a real terminal.
#
# Not a recording of a rendered mock: this opens Terminal.app at a fixed size,
# runs the agent in it, and captures that window's screen region with the system
# screenshot tool. What lands in the PNG is what a person would see.
#
#   ./capture-terminal.sh open  [command...]   open the window and start the agent
#   ./capture-terminal.sh send  "text"         type text into it and press Return
#   ./capture-terminal.sh enter                press Return on its own
#   ./capture-terminal.sh shot  NAME           capture the window into NAME.png
#   ./capture-terminal.sh close                close the window
#
# Only the window's own rectangle is captured, so nothing else on the desktop
# can end up in the frame.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
AGENT="$ROOT/terminal-agent"
OUT="$ROOT/assets/screenshots/terminal"
STATE="${TMPDIR:-/tmp}/jevis-capture.state"

# The window is sized in character cells, not pixels, so the agent always gets the
# same terminal geometry and the text keeps its natural size on any display.
# PROFILE must be an opaque Terminal profile: a translucent one lets the desktop
# show through and the screenshot stops being a picture of the terminal.
COLS=${JEVIS_COLS:-110}
ROWS=${JEVIS_ROWS:-34}
PROFILE=${JEVIS_PROFILE:-Novel}
X=${JEVIS_X:-40}
Y=${JEVIS_Y:-40}
DOCK_MARGIN=110

die() { printf '%s\n' "$*" >&2; exit 1; }

case "${1:-}" in

open)
	shift
	CMD=${*:-".venv/bin/python -m jev_agent --demo --mission loglab"}
	[ -x "$AGENT/.venv/bin/python" ] || die "no virtualenv at $AGENT/.venv — run ./setup.sh in $AGENT first"
	mkdir -p "$OUT"
	ID=$(osascript <<-EOF
		tell application "Finder" to set screen to bounds of window of desktop
		set usableBottom to (item 4 of screen) - $DOCK_MARGIN
		tell application "Terminal"
			do script "cd $AGENT && clear && $CMD"
			set w to front window
			-- the profile belongs to the tab, not the window
			set current settings of (selected tab of w) to settings set "$PROFILE"
			set number of columns of w to $COLS
			set number of rows of w to $ROWS
			set b to bounds of w
			set h to (item 4 of b) - (item 2 of b)
			set wd to (item 3 of b) - (item 1 of b)
			-- shed rows until the window clears the Dock
			repeat while ($Y + h) > usableBottom and (number of rows of w) > 20
				set number of rows of w to (number of rows of w) - 2
				set b to bounds of w
				set h to (item 4 of b) - (item 2 of b)
			end repeat
			set bounds of w to {$X, $Y, $X + wd, $Y + h}
			activate
			return id of w as string
		end tell
	EOF
	) || die "could not open Terminal"
	printf '%s\n' "$ID" > "$STATE"
	# Read the bounds back: the window manager may clamp them to the menu bar.
	osascript -e "tell application \"Terminal\" to get bounds of (first window whose id is $ID)" \
		| tr -d ' ' >> "$STATE"
	printf 'window %s opened, running: %s\n' "$ID" "$CMD"
	;;

send)
	[ -f "$STATE" ] || die "no open window; run: $0 open"
	ID=$(head -1 "$STATE")
	[ $# -ge 2 ] || die "usage: $0 send \"text\""
	osascript -e "tell application \"Terminal\" to do script \"$2\" in (first window whose id is $ID)" >/dev/null
	;;

enter)
	[ -f "$STATE" ] || die "no open window; run: $0 open"
	ID=$(head -1 "$STATE")
	osascript -e "tell application \"Terminal\" to do script \"\" in (first window whose id is $ID)" >/dev/null
	;;

shot)
	# screencapture -R grabs a screen rectangle, so it would happily photograph
	# whatever window happens to sit on top of ours. Guard against that: confirm
	# our window is the front window of the front application both immediately
	# before and immediately after the shot, and throw the frame away otherwise.
	[ -f "$STATE" ] || die "no open window; run: $0 open"
	[ $# -ge 2 ] || die "usage: $0 shot NAME"
	ID=$(head -1 "$STATE")
	TMPSHOT="${TMPDIR:-/tmp}/jevis-shot.$$.png"
	mkdir -p "$OUT"

	front_state() {
		osascript -e "tell application \"Terminal\"
			if (count of windows) is 0 then return \"none\"
			return (frontmost as string) & \",\" & (id of front window as string)
		end tell" 2>/dev/null | tr -d ' '
	}

	ATTEMPT=0
	while [ "$ATTEMPT" -lt 6 ]; do
		ATTEMPT=$((ATTEMPT + 1))
		osascript >/dev/null 2>&1 <<-EOF || true
			tell application "Terminal"
				activate
				set index of (first window whose id is $ID) to 1
			end tell
		EOF
		sleep 1
		[ "$(front_state)" = "true,$ID" ] || continue

		BOUNDS=$(osascript -e "tell application \"Terminal\" to get bounds of (first window whose id is $ID)" | tr -d ' ')
		L=$(printf '%s' "$BOUNDS" | cut -d, -f1)
		T=$(printf '%s' "$BOUNDS" | cut -d, -f2)
		R=$(printf '%s' "$BOUNDS" | cut -d, -f3)
		B=$(printf '%s' "$BOUNDS" | cut -d, -f4)
		screencapture -x -R"$L,$T,$((R - L)),$((B - T))" -t png "$TMPSHOT"

		if [ "$(front_state)" = "true,$ID" ] && [ -s "$TMPSHOT" ]; then
			mv "$TMPSHOT" "$OUT/$2.png"
			printf '%s\n' "$OUT/$2.png"
			exit 0
		fi
		rm -f "$TMPSHOT"
	done
	rm -f "$TMPSHOT"
	die "could not get a clean shot: another window kept coming to the front"
	;;

close)
	[ -f "$STATE" ] || exit 0
	ID=$(head -1 "$STATE")
	osascript -e "tell application \"Terminal\" to close (every window whose id is $ID)" >/dev/null 2>&1 || true
	rm -f "$STATE"
	printf 'window %s closed\n' "$ID"
	;;

*)
	sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
	exit 1
	;;
esac
