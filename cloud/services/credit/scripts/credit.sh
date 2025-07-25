#!/bin/bash

# Fall back if env vars are not provided
# Set timezone for Denver
TZ=America/Denver
DATE=$(TZ=$TZ date '+%Y-%m-%d %H:%M:%S')

# Fallback if environment vars are not provided
ENV_NAME=${ENV_NAME:-credit}
START_DATE=${START_DATE:-$(TZ=$TZ date +"%Y-%m-%d 00:00:00")}
END_DATE=${END_DATE:-$(TZ=$TZ date -d "+1 day" +"%Y-%m-%d 00:00:00")}
SAVE_LOC=${SAVE_LOC:-"credit_run/results/gfs_init_$(TZ=$TZ date +%Y%m%d_0000).zarr"}

echo "[$DATE] Starting Forecast Pipeline in the environment: $ENV_NAME"
echo "[$DATE] Forecast window: $START_DATE → $END_DATE"
echo "[$DATE] Output path: $SAVE_LOC"

# Test GPU availability
echo "[$DATE] Testing GPU availability..."
conda run -n "$ENV_NAME" python -c "import torch; print('CUDA available?', torch.cuda.is_available())"

# Modify model.yml using sed
echo "Updating model.yml..."
sed -i "s|^ *forecast_start_time:.*|        forecast_start_time: \"$START_DATE\"|" model.yml
sed -i "s|^ *forecast_end_time:.*|        forecast_end_time: \"$END_DATE\"|" model.yml
sed -i "s|^\([[:space:]]*save_loc:\).*zarr\"$|\1 \"$SAVE_PATH\"|" model.yml
sed -i "s|^\([[:space:]]*save_loc_surface:\).*zarr\"$|\1 \"$SAVE_PATH\"|" model.yml
echo "model.yml updated successfully..."

# Start pipeline
echo "[$DATE] Running gfs_init.py..."
conda run -n "$ENV_NAME" python miles-credit/applications/gfs_init.py -c model.yml

if [ $? -eq 0 ]; then
    echo "[$DATE] gfs_init.py completed successfully."

    echo "[$DATE] Running rollout_realtime.py..."
    conda run -n "$ENV_NAME" python miles-credit/applications/rollout_realtime.py -c model.yml

    if [ $? -eq 0 ]; then
        echo "[$DATE] Forecast complete. Transforming..."
        conda run -n "$ENV_NAME" bash credit_run/process.sh
        echo "[$DATE] Credit is running fine ..."
    else
        echo "[$DATE] Forecast failed."
    fi
else
    echo "[$DATE] gfs_init.py failed."
fi

echo "[$DATE] Done."
