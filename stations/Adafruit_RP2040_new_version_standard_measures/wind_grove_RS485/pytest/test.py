import minimalmodbus

instrument = minimalmodbus.Instrument('COM8', 1)  # port, slave address
instrument.serial.baudrate = 9600
instrument.serial.timeout = 0.5

import serial
instrument.serial.parity = serial.PARITY_ODD

try:
    regs = instrument.read_registers(0, 2, functioncode=3)
    print("Success (func 3):", regs)
except Exception as e:
    print("func 3 failed:", e)

try:
    regs = instrument.read_registers(0, 2, functioncode=4)
    print("Success (func 4):", regs)
except Exception as e:
    print("func 4 failed:", e)