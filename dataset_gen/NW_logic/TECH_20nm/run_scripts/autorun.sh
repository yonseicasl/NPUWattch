#!/bin/bash

# Example : ./01_syn.sh 20 TT 0.9 25 fpmult fpmult_200M

# 1. Argument Check
if [ $# -lt 6 ]; then
    echo "Error: Missing arguments."
    echo "Usage: $0 <NODE> <PROCESS> <VOLTAGE> <TEMP> <RTL_TOP> <CFG_FILE> [STEP]"
    exit 1
fi

# Assign arguments to variables
NODE=$1
PROCESS=$2
VOLTAGE=$3
TEMP=$4
RTL_TOP=$5
CFG_FILE=$6

# Handle STEP with a default value of 0 (now the 7th argument)
STEP=${7:-0}

# Base directory for technology libraries
TECH_BASE_DIR="../../tech_libs"
CATALOG_FILE="${TECH_BASE_DIR}/catalog.json"

# 2. File Validation
if [ ! -f "$CATALOG_FILE" ]; then
    echo "Error: Catalog file not found at $CATALOG_FILE"
    exit 1
fi

# 3. JSON Parsing using 'jq'
# Added 'temp' variable and included it in the selection criteria
target_corner=$(jq -c --arg node "$NODE" --arg proc "$PROCESS" --arg volt "$VOLTAGE" --arg temp "$TEMP" \
    '. | select(.node == $node) | .corners[] | select(.process == $proc and .voltage == $volt and .temperature == $temp)' \
    "$CATALOG_FILE")

# Check if a matching corner was found
if [ -z "$target_corner" ]; then
    echo "Error: No matching configuration found for Node:$NODE, Proc:$PROCESS, Volt:$VOLTAGE, Temp:$TEMP"
    exit 1
fi

# 4. Extract Directory and Filenames
DIR_NAME=$(echo "$target_corner" | jq -r '.directory')
FULL_PATH="${TECH_BASE_DIR}/${DIR_NAME}"

# 5. Overwrite Technology File Variables with Full Paths
DBFile="${FULL_PATH}/$(echo "$target_corner" | jq -r '.dbfile')"
TLUFile="${FULL_PATH}/$(echo "$target_corner" | jq -r '.tlufile')"
NDMFile="${FULL_PATH}/$(echo "$target_corner" | jq -r '.ndmfile')"
TechFile="${FULL_PATH}/$(echo "$target_corner" | jq -r '.techfile')"
MapFile="${FULL_PATH}/$(echo "$target_corner" | jq -r '.mapfile')"
GRDFile="${FULL_PATH}/$(echo "$target_corner" | jq -r '.grdfile')"

# Display loaded paths for verification
echo "------------------------------------------------------------------------------------------------"
echo " Technology Library Paths Loaded"
echo "------------------------------------------------------------------------------------------------"
echo " Process:       ${PROCESS}"
echo " Voltage:       ${VOLTAGE}V"
echo " Temperature:   ${TEMP}C"
echo " Directory:     $FULL_PATH"
echo " DBFile:        $DBFile"
echo " TLUFile:       $TLUFile"
echo " NDMFile:       $NDMFile"
echo " TechFile:      $TechFile"
echo " MapFile:       $MapFile"
echo " GRDFile:       $GRDFile"
echo "------------------------------------------------------------------------------------------------"

# Workflow directories
SYN_DIR="DC_$RTL_TOP"
PNR_DIR="ICC2_$RTL_TOP"
PEX_DIR="STRC_$RTL_TOP"

SYN_SCRIPT="01_syn.tcl"
PNR_SCRIPT="02_pnr.tcl"
PEX_SCRIPT="03_pex.strc"


if [ "$STEP" -eq 0 ] || [ "$STEP" -eq 1 ]; then
  (
  cd ../01_syn
  
  rm -rf "$SYN_DIR"
  mkdir -p "$SYN_DIR"
  cd "$SYN_DIR"
   
  cp ../../../master_tcl/"$SYN_SCRIPT" ./"$SYN_SCRIPT"
  
  # Files to search and replace in
  FILES=("$SYN_SCRIPT")
  
  # Loop through the files
  for FILE in "${FILES[@]}"; do
    if [[ -f "$FILE" ]]; then
      # Replace "MyDesign" with the provided argument
      sed -i "s/MyDesign/$RTL_TOP/g" "$FILE"
      sed -i "s|MyDBFile|$DBFile|g" "$FILE"
    else
      echo "File $FILE not found."
    fi
  done
  
  APPEND_SCRIPT="../../../rtl/$RTL_TOP/$CFG_FILE.cfg"
  
  # Insert lines from append script directly the tcl
  awk '
      BEGIN {
          append_start_found = 0
          append_lines_count = 0
      }
      # Read the append script into memory between the markers
      FILENAME == ARGV[1] {
          if ($0 ~ /#START_OF_DC_APPEND_SCRIPT/) append_start_found = 1
          else if ($0 ~ /#END_OF_DC_APPEND_SCRIPT/) append_start_found = 0
          else if (append_start_found) append_lines[++append_lines_count] = $0
          next
      }
      # Insert stored lines into the master script between its markers
      FILENAME == ARGV[2] {
          if ($0 ~ /#START_OF_DC_APPENDED_SCRIPT/) {
              print $0
              for (i = 1; i <= append_lines_count; i++) {
                  print append_lines[i]
              }
              next
          }
          print $0
      }
  ' "$APPEND_SCRIPT" "$SYN_SCRIPT" > "${SYN_SCRIPT}.tmp"
  
  # Replace the master script with the modified version
  mv "${SYN_SCRIPT}.tmp" "$SYN_SCRIPT"

  #csh ~/sources/dc23.cshrc
  
  dc_shell -f "$SYN_SCRIPT" | tee synthesis.log

  )
fi


if [ "$STEP" -eq 0 ] || [ "$STEP" -eq 2 ] || [ "$STEP" -eq 24 ]; then
  (
  cd ../02_pnr
  
  rm -rf "$PNR_DIR"
  mkdir -p "$PNR_DIR"
  cd "$PNR_DIR"
  
  cp ../../../master_tcl/"$PNR_SCRIPT" ./"$PNR_SCRIPT"
  cp ../../01_syn/"$SYN_DIR"/"$RTL_TOP"_syn.v ./
  cp ../../01_syn/"$SYN_DIR"/"$RTL_TOP".sdc ./
  
  
  # Files to search and replace in
  FILES=("$PNR_SCRIPT")
  
  # Loop through the files
  for FILE in "${FILES[@]}"; do
    if [[ -f "$FILE" ]]; then
      # Replace "MyDesign" with the provided argument
      sed -i "s/MyDesign/$RTL_TOP/g" "$FILE"
      sed -i "s|MyTLUFile|$TLUFile|g" "$FILE"
      sed -i "s|MyNDMFile|$NDMFile|g" "$FILE"
      sed -i "s|MyTechFile|$TechFile|g" "$FILE"
      sed -i "s|MyMapFile|$MapFile|g" "$FILE"
    else
      echo "File $FILE not found."
    fi
  done
  
  # csh ~/sources/icc2_23.12-SP4.cshrc
  
  icc2_shell -f "$PNR_SCRIPT"
  )
fi

if [ "$STEP" -eq 0 ] || [ "$STEP" -eq 3 ] || [ "$STEP" -eq 24 ]; then
  (
  cd ../03_pex
  
  rm -rf "$PEX_DIR"
  mkdir -p "$PEX_DIR"
  cd "$PEX_DIR" 

  cp ../../../master_tcl/"$PEX_SCRIPT" ./"$PEX_SCRIPT"
  
  
  # Files to search and replace in
  FILES=("$PEX_SCRIPT")
  
  # Loop through the files
  for FILE in "${FILES[@]}"; do
    if [[ -f "$FILE" ]]; then
      # Replace "MyDesign" with the provided argument
      sed -i "s/MyDesign/$RTL_TOP/g" "$FILE"
      sed -i "s|MyMapFile|$MapFile|g" "$FILE"
      sed -i "s|MyGRDFile|$GRDFile|g" "$FILE"
    else
      echo "File $FILE not found."
    fi
  done
  
  APPEND_SCRIPT="../../../rtl/$RTL_TOP/$CFG_FILE.cfg"
  
  TEMPERATURE=$(grep "STRC_TEMPERATURE" "$APPEND_SCRIPT" | awk '{print $2}')
  echo "$TEMPERATURE"
  sed -i "s/STRC_TEMPERATURE/$TEMPERATURE/g" "$PEX_SCRIPT"
  
  # csh ~/sources/starrc_23.cshrc
  StarXtract "$PEX_SCRIPT"
  
  )
fi

