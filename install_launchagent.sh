#!/bin/bash
# Installs the arena-wallpaper LaunchAgent on your Mac.
# Run this once from the project folder after completing the .env setup.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USERNAME="$(whoami)"
PLIST_NAME="com.${USERNAME}.arena-wallpaper.plist"
AGENTS_DIR="${HOME}/Library/LaunchAgents"

echo "---"
echo "Project path : ${SCRIPT_DIR}"
echo "Username     : ${USERNAME}"
echo "Plist name   : ${PLIST_NAME}"
echo "---"
echo ""

# Generate plist from template
sed "s|YOUR_USERNAME|${USERNAME}|g; s|YOUR_PROJECT_PATH|${SCRIPT_DIR}|g" \
    "${SCRIPT_DIR}/launchagent.plist.template" > "${SCRIPT_DIR}/${PLIST_NAME}"
echo "Created ${PLIST_NAME}"

# Install into LaunchAgents
mkdir -p "${AGENTS_DIR}"
cp "${SCRIPT_DIR}/${PLIST_NAME}" "${AGENTS_DIR}/${PLIST_NAME}"
echo "Copied to ~/Library/LaunchAgents/"

# Unload first if already running (safe to ignore error if not loaded)
launchctl unload "${AGENTS_DIR}/${PLIST_NAME}" 2>/dev/null || true

# Load and start
launchctl load "${AGENTS_DIR}/${PLIST_NAME}"
echo "LaunchAgent loaded — will run automatically daily at 09:00."
echo ""
echo "Running once now to verify setup..."
launchctl start "com.${USERNAME}.arena-wallpaper"

# Wait for the script to finish
sleep 8

echo ""
echo "Last 10 lines of log:"
echo "---"
tail -n 10 "${SCRIPT_DIR}/arena_wallpaper.log"
echo "---"
echo ""
echo "If you see 'Done.' above, the setup is complete."
echo "Your wallpaper should have changed."
