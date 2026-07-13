#!/bin/bash
# clean_all.sh — wipe every generated SRAM artifact (mirrors logic/clean_all.sh).
#
# Removes the per-config work trees under TECH_*nm/ (wd_* / column_* /
# array_* / dec_*: generated GDS, extraction keepers, simulation runs) and
# the autosweep logs.  Everything here is regenerable from the flows; the
# library collateral lives in ../tech_libs/ and is never touched, and the
# datasets/ sheets are kept.

cd "$(dirname "$0")"

rm -rf ./TECH_*nm/*

rm -rf ./autosweep/logs/*
