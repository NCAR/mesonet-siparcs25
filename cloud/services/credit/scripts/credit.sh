#!/bin/bash

# Fall back if env vars are not provided
# Set timezone for Denver
TZ=America/Denver

# Fallback if environment vars are not provided
ENV_NAME=${ENV_NAME:-credit}
START_DATE=${START_DATE:-$(TZ=$TZ date +"%Y-%m-%d 00:00:00")}
END_DATE=${END_DATE:-$(TZ=$TZ date -d "+1 day" +"%Y-%m-%d 00:00:00")}
SAVE_LOC=${SAVE_LOC:-"credit_run/results/gfs_init_$(TZ=$TZ date +%Y%m%d_0000).zarr"}

echo "[$(date)] Starting Forecast Pipeline in the environment: $ENV_NAME"
echo "[$(date)] Forecast window: $START_DATE → $END_DATE"
echo "[$(date)] Output path: $SAVE_LOC"

# Modify model.yml using sed
echo "Updating model.yml..."
sed -i "s|^ *forecast_start_time:.*|        forecast_start_time: \"$START_DATE\"|" model.yml
sed -i "s|^ *forecast_end_time:.*|        forecast_end_time: \"$END_DATE\"|" model.yml
sed -i "s|^\([[:space:]]*save_loc:\).*zarr\"$|\1 \"$SAVE_PATH\"|" model.yml

# Start pipeline
echo "[$(date)] Running gfs_init.py..."
conda run -n "$ENV_NAME" python miles-credit/applications/gfs_init.py -c model.yml

if [ $? -eq 0 ]; then
    echo "[$(date)] gfs_init.py completed successfully."

    echo "[$(date)] Running rollout_realtime.py..."
    conda run -n "$ENV_NAME" python miles-credit/applications/rollout_realtime.py -c model.yml

    if [ $? -eq 0 ]; then
        echo "[$(date)] Forecast complete. Transforming..."
        conda run -n "$ENV_NAME" python services/credit/transform_forecast_output.py
    else
        echo "[$(date)] Forecast failed."
    fi
else
    echo "[$(date)] gfs_init.py failed."
fi

echo "[$(date)] Done."
