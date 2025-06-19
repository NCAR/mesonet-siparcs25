CREATE DATABASE metabase;

CREATE DATABASE iotwx_db;

CREATE TABLE IF NOT EXISTS readings (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(100),
    device VARCHAR(255),
    measurement VARCHAR(255),
    reading_value DOUBLE PRECISION NOT NULL,
    sensor_protocol VARCHAR(255),
    sensor_model VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
);

CREATE TABLE IF NOT EXISTS stations (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(255) NOT NULL UNIQUE,
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    firstname CHAR(50),
    lastname CHAR(50),
    email VARCHAR(20),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
