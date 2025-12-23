# Mesonet-siparcs25

## Cloud

A Python application for analyzing and visualizing Mesonet weather data as part of the SIPaRCs 2025 project.

### Features

- Download and process Mesonet weather datasets
- Data cleaning and transformation utilities
- Interactive data visualizations
- Export results to CSV or image formats

### Installation

```bash
git clone https://github.com/NCAR/mesonet-siparcs25.git
cd mesonet-siparcs25/cloud
pip install -r requirements.txt
```

### Usage

```bash
sh scripts/run.sh -s
```

## Edge-Server
All the stations push data through raspberry pis that serve as gateways using radio.
The pis push the data to the cloud using an MQTT server.
### Installation
This clones the repo and pip installs the edge-server requirements. 

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/NCAR/mesonet-siparcs25.git
cd mesonet-siparcs25/edge-server
pip install -r requirements.txt
```

### Usage
This runs the application as a service in the background.
```bash
./setup_and_run.sh
```
### Verify
You can run this to see the ouput of the application
```bash
./verify.sh
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License.

