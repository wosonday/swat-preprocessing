swatprep convert streamflow \
  --format per_station \
  --glob "Q_BA_0001.csv" \
  /mnt/d/DATA_STORAGE/_data/_DataReview/dailyStreamflow_end2019 \
  /mnt/d/streamflow/Q_BA_0001.csv


swatprep convert climate \
  /mnt/d/DATA_STORAGE/_data/_DataReview/dailyClimateData_USTH \
  /mnt/d/DATA_STORAGE/_data/_DataReview/climate_swatplus