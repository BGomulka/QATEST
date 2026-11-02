#!/bin/sh
set -e -x

for SerialNumber in "$@"
do
    SerialNumberString=`printf "%03d" $SerialNumber`
    frugy -w \
          -s "serial_number=$SerialNumberString" \
          -o "TRGOUT_FMC_EEPROM_$SerialNumberString".bin \
          trgout-fmc.yml
done
