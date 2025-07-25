#!/bin/bash

cd /cloud/services/credit/credit_run

# Set timezone for Denver
TZ=America/Denver
DATE=$(TZ=$TZ date '+%Y-%m-%d %H:%M:%S')

ENV_NAME=${ENV_NAME:-credit}
FORECAST_DATE=${FORECAST_DATE}
FORECAST_DAYS=${FORECAST_DAYS}
TOTAL_HOURS=$((FORECAST_DAYS * 24))

# Ensure writable data directory exists
mkdir -p /cloud/services/credit/credit_run/results/${FORECAST_DATE}T00Z_Forecast/Notebooks
chmod -R 777 /cloud/services/credit/credit_run/results/${FORECAST_DATE}T00Z_Forecast/Notebooks
mkdir -p /cloud/services/credit/credit_run/results/${FORECAST_DATE}T00Z_Forecast/Data
chmod -R 777 /cloud/services/credit/credit_run/results/${FORECAST_DATE}T00Z_Forecast/Data

echo "[$DATE] Processing Forecast Data in environment: $ENV_NAME"
echo "[$DATE] Forecast Date: $FORECAST_DATE | Days: $FORECAST_DAYS | Hours: $TOTAL_HOURS"

# Copy template only if it doesn't already exist
if [ ! -f process/data_template.ipynb ]; then
    cp process/data.ipynb process/data_template.ipynb
fi

for HOUR in $(seq 6 6 $TOTAL_HOURS); do
    PADDED_HOUR=$(printf "%03d" $HOUR)

    echo "[$DATE] --- Processing forecast for hour: $PADDED_HOUR ---"

    # Reset notebook from template before replacing content
    cp process/data_template.ipynb process/data.ipynb

    echo "[$DATE] Updating the notebook for hour: $PADDED_HOUR and output path..."

    # Replace forecast path in the notebook using sed
    sed -i "s|results/[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}T00Z/pred_[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}T00Z_[0-9]\{3\}\b|results/${FORECAST_DATE}T00Z/pred_${FORECAST_DATE}T00Z_${PADDED_HOUR}|g" process/data.ipynb
    
    sed -i "s|results/[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}T00Z_Forecast/Data/forecast_[0-9]\{3\}|results/${FORECAST_DATE}T00Z_Forecast/Data/forecast_${PADDED_HOUR}|g" process/data.ipynb

    echo "[$DATE] Running the notebook..."
    conda run -n "$ENV_NAME" papermill process/data.ipynb /cloud/services/credit/credit_run/results/${FORECAST_DATE}T00Z_Forecast/Notebooks/forecast_${PADDED_HOUR}.ipynb

    if [ $? -eq 0 ]; then
        echo "[$DATE] 🤩 Processing forecast for ${PADDED_HOUR} completed successfully."

        echo "[$DATE] Writing processed data to the database..."
        sed -i "s|results/[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}T00Z_Forecast/Data/.*\.ipynb|results/${FORECAST_DATE}T00Z_Forecast/Data/forecast_${PADDED_HOUR}.xlsx|g" write_to_db.py
        conda run -n "$ENV_NAME" python write_to_db.py
    else
        echo "[$DATE] 😡 Processing forecast failed for ${PADDED_HOUR}."
    fi
done

# Restore original notebook and clean up
echo "[$DATE] Restoring original notebook."
cp process/data_template.ipynb process/data.ipynb

echo "[$DATE] Cleaning up template..."
rm process/data_template.ipynb

echo "[$DATE] ✅ All processing tasks completed and template cleaned up."
