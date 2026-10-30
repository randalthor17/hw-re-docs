#!/bin/sh
# Re-creates the Ghidra project for the firmware dump and exports decompiled C + listing into ghidra/ (gitignored: derived from vendor firmware).
# Usage: tools/ghidra/run.sh [DUMP.bin]   (default captures/firmware/mk75-full-isp.bin, see NOTES "Firmware dump")
# Needs Ghidra 12 and a JDK it accepts: brew ghidra + openjdk@25, or GHIDRA_HOME (the dir holding support/analyzeHeadless) and JAVA_HOME.
DUMP=$(realpath "${1:-$(dirname "$0")/../../captures/firmware/mk75-full-isp.bin}")
cd "$(dirname "$0")/../.."
if command -v brew > /dev/null; then
  : "${GHIDRA_HOME:=$(brew --prefix ghidra)/libexec}"
  : "${JAVA_HOME:=$(brew --prefix openjdk@25)/libexec}"
fi
export JAVA_HOME PATH="$JAVA_HOME/bin:$PATH"
mkdir -p ghidra
"$GHIDRA_HOME/support/analyzeHeadless" "$PWD/ghidra" mk75 -import "$DUMP" -overwrite \
  -processor 8051:BE:16:default -loader BinaryLoader -scriptPath "$PWD/tools/ghidra" -postScript ExportAll.java "$PWD/ghidra"
