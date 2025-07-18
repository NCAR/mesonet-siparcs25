FROM continuumio/miniconda3

# Set environment variables
ARG ENV_NAME=credit
ENV ENV_NAME=${ENV_NAME}

ARG ENV_FILE=environment_cpu.yml
ENV ENV_FILE=${ENV_FILE}

# System dependencies for pysteps and cartopy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    libproj-dev \
    libgeos-dev \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Create and enter working directory
WORKDIR /cloud
RUN mkdir -p /cloud/services/credit

WORKDIR /cloud/services/credit

# Copy static and service files
COPY scripts ./scripts
COPY model.yml ./model.yml

# Copy project repository
COPY miles-credit ./miles-credit

# Ensure write permissions for micromamba and pip
USER root
RUN chmod -R u+w ./miles-credit

# Copy environment files
COPY miles-credit/environment_cpu.yml ./miles-credit/environment_cpu.yml
COPY miles-credit/environment_gpu.yml ./miles-credit/environment_gpu.yml

# Set working dir to repo root
WORKDIR /cloud/services/credit/miles-credit

# Use the environment.yml to create the environment
RUN conda env create -n ${ENV_NAME} -f ${ENV_FILE}

# Install pysteps and your package
# RUN conda run -n ${ENV_NAME} pip install git+https://github.com/pySTEPS/pysteps
RUN conda run -n ${ENV_NAME} pip install -e .

# Switch back to main service directory
WORKDIR /cloud/services/credit

# Make sure script is executable
COPY scripts/init_credit.sh ./scripts/credit.sh
RUN chmod +x ./scripts/credit.sh

# Default startup command
CMD ["/bin/bash", "./scripts/init_credit.sh"]
