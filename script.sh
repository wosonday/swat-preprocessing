#!/usr/bin/env bash
# Example conversion commands. Replace ./data/... with your own paths.

swatprep convert streamflow \
  --format per_station \
  --glob "GAUGE01.csv" \
  ./data/streamflow_raw \
  ./data/streamflow/GAUGE01.csv


swatprep convert climate \
  ./data/climate_raw \
  ./data/climate
