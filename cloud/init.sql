CREATE DATABASE metabase;
CREATE DATABASE iotwx_db;
-- Connect to iotwx_db before creating tables
\c iotwx_db;

-- Create the stations table first (required for FK in readings)
CREATE TABLE IF NOT EXISTS stations (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(50) NOT NULL UNIQUE,
    device VARCHAR(50),
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    altitude DOUBLE PRECISION,
    firstname CHAR(50),
    lastname CHAR(50),
    email VARCHAR(50),
    organization VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create the readings table referencing stations
CREATE TABLE IF NOT EXISTS readings (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(50),
    edge_id VARCHAR(50),
    measurement VARCHAR(50),
    reading_value DOUBLE PRECISION NOT NULL,
    sensor_protocol VARCHAR(50),
    sensor_model VARCHAR(50),
    rssi INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    altitude DOUBLE PRECISION,
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
);