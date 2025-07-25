FROM continuumio/miniconda3

ARG ENV_NAME=credit
ENV ENV_NAME=${ENV_NAME}

ARG ENV_FILE=process/environment.yml
ENV ENV_FILE=${ENV_FILE}

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ git libproj-dev libgeos-dev libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy environment and project code
COPY process /cloud/services/credit/credit_run/process
WORKDIR /cloud/services/credit/credit_run

# Create the Conda environment and register Jupyter kernel
RUN conda env create -n ${ENV_NAME} -f ${ENV_FILE} && \
    conda run -n ${ENV_NAME} python -m ipykernel install --user \
      --name ${ENV_NAME} --display-name "CREDIT (processing)"

# Make sure script is executable
COPY process.sh .
RUN chmod +x process.sh

# Default startup command
CMD ["/bin/bash", "./process.sh"]
