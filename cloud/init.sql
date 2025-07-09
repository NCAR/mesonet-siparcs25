CREATE DATABASE metabase;
CREATE DATABASE iotwx_db;
-- Connect to iotwx_db before creating tables
\c iotwx_db;

-- Create the stations table first (required for FK in readings)
CREATE TABLE IF NOT EXISTS stations (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(25) NOT NULL UNIQUE,
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    firstname CHAR(25),
    lastname CHAR(25),
    email VARCHAR(25),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create the readings table referencing stations
CREATE TABLE IF NOT EXISTS readings (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(25),
    edge_id VARCHAR(25),
    device VARCHAR(25),
    measurement VARCHAR(25),
    reading_value DOUBLE PRECISION NOT NULL,
    sensor_protocol VARCHAR(25),
    sensor_model VARCHAR(25),
    rssi INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
);