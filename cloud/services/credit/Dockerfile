FROM nvidia/cuda:12.2.0-base-ubuntu22.04

# Set environment variables
ARG ENV_NAME=credit
ENV ENV_NAME=${ENV_NAME}

ARG ENV_FILE=environment_cpu.yml
ENV ENV_FILE=${ENV_FILE}

ARG ARCHITECTURE=aarch64
ENV ARCHITECTURE=${ARCHITECTURE}

ARG FORECAST_DATE=2024-07-23
ENV FORECAST_DATE=${FORECAST_DATE}

ARG FORECAST_DAYS=7
ENV FORECAST_DAYS=${FORECAST_DAYS}

ENV CONDA_DIR=/opt/conda
ENV PATH=$CONDA_DIR/bin:$PATH
ENV MINIFORGE_VERSION=23.3.1-0

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl git wget bzip2 ca-certificates vim \
    libglib2.0-0 libxext6 libsm6 libxrender1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Miniforge (Conda)
RUN wget https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/Miniforge3-Linux-${ARCHITECTURE}.sh -O /tmp/miniforge.sh && \
    bash /tmp/miniforge.sh -b -p ${CONDA_DIR} && \
    rm /tmp/miniforge.sh

# Copy project repository
COPY miles-credit /cloud/services/credit/miles-credit

# Ensure write permissions for micromamba and pip
USER root
RUN chmod -R u+w /cloud/services/credit/miles-credit

# Set working dir to repo root
WORKDIR /cloud/services/credit/miles-credit

# Use the environment.yml to create the environment
RUN conda env create -n ${ENV_NAME} -f ${ENV_FILE} && \
    conda clean -afy

# Activate the conda environment.
RUN conda run -n ${ENV_NAME} pip install -e .

# Switch back to main service directory
WORKDIR /cloud/services/credit

COPY model.yml ./model.yml
RUN chmod +x ./model.yml

# Make sure script is executable
COPY scripts/credit.sh ./scripts/credit.sh
RUN chmod +x ./scripts/credit.sh

# Copy the credit_run directory
COPY credit_run .
RUN chmod +x ./credit_run/process.sh

# Default startup command
CMD ["/bin/bash", "./scripts/credit.sh"]
