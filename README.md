# OctoPrint MCP2221A Filament Sensor Plugin

A comprehensive OctoPrint plugin for monitoring filament run-out and motion using the MCP2221A USB-to-GPIO bridge. Designed specifically for dual extruder printers with independent sensor monitoring per extruder.

## Features

- **Dual Extruder Support**: Independent monitoring for both E0 and E1 extruders
- **Two Sensor Types Per Extruder**:
  - Mechanical filament run-out sensors
  - Optical motion/pulse sensors
- **Platform Independent**: Works on Windows, macOS, and Linux (not just Raspberry Pi)
- **Intelligent Monitoring**: Only monitors active extruder during printing (configurable)
- **Configurable Actions**: Custom G-code commands, pause behavior, and notifications
- **Motion Timeout Detection**: Detects jammed filament or missing motion pulses
- **Comprehensive Settings**: Pin assignments, inversion, debouncing, timeouts
- **Real-time Status**: Live sensor status display and testing tools
- **Mock Mode**: Full testing capability without hardware

## Hardware Requirements

- MCP2221A USB-to-GPIO bridge board
- Filament run-out sensors (mechanical switches recommended)
- Motion sensors (optical encoders/pulse sensors)
- Dual extruder 3D printer

## Pin Assignments

Default pin assignments (configurable in settings):

| Sensor | Default Pin | Type |
|--------|-------------|------|
| E0 Runout | Pin 0 | Mechanical switch |
| E0 Motion | Pin 1 | Optical encoder |
| E1 Runout | Pin 2 | Mechanical switch |
| E1 Motion | Pin 3 | Optical encoder |

## Installation

### Via Plugin Manager (Recommended)
1. Open OctoPrint Settings
2. Go to Plugin Manager
3. Click "Get More..."
4. Install from URL: `https://github.com/chrisns/OctoPrint-MCP2221-Filament-Sensor/archive/main.zip`

### Manual Installation
```bash
# Activate your OctoPrint virtual environment
source /path/to/octoprint/venv/bin/activate

# Install from local directory
pip install .

# Or install from GitHub
pip install https://github.com/chrisns/OctoPrint-MCP2221-Filament-Sensor/archive/main.zip
```

## Configuration

1. Navigate to **Settings > MCP2221A Filament Sensor**
2. Configure hardware settings:
   - Enable mock mode for testing without hardware
   - Adjust polling interval (default: 0.1 seconds)
3. Configure each extruder:
   - Enable/disable sensors
   - Set GPIO pin assignments
   - Configure sensor inversion (for NC switches)
   - Set motion timeout values
   - Adjust debounce times
4. Configure actions:
   - Enable/disable print pausing
   - Set G-code commands (M600, @pause, custom)
   - Configure notifications
5. Test your sensors using the built-in test function

## Sensor Types

### Filament Run-out Sensors
- **Type**: Mechanical switches (recommended)
- **Connection**: Between GPIO pin and ground
- **Logic**: HIGH = filament present, LOW = filament run-out
- **Trigger**: When filament physically runs out

### Motion Sensors  
- **Type**: Optical encoders/pulse sensors
- **Connection**: Between GPIO pin and ground
- **Logic**: Pulses indicate filament movement
- **Trigger**: When no pulses detected for configured timeout period

## G-code Commands

### Default Commands
- **Filament Run-out**: `M600` (filament change)
- **Motion Timeout**: `@pause` (pause print)

### Custom Commands
You can configure custom G-code sequences for each trigger type:
```gcode
M117 Filament runout detected!
M300 S1000 P500
M600
```

## API Endpoints

### Get Status
```
GET /plugin/mcp2221_filament_sensor/status
```
Returns current sensor states, hardware status, and motion rates.

### Test Sensors
```
POST /plugin/mcp2221_filament_sensor/test_sensors
```
Performs a live test of all configured sensors.

## Troubleshooting

### Hardware Not Detected
1. Enable "Use mock hardware" for testing
2. Check MCP2221A USB connection
3. Verify PyMCP2221A library installation
4. Check system permissions for USB device access

### Sensors Not Responding
1. Use the "Test Sensors" function
2. Check pin assignments and wiring
3. Verify sensor types (NO vs NC)
4. Adjust debounce times if sensors are noisy
5. Enable debug logging for detailed diagnostics

### False Triggers
1. Increase debounce time
2. Check for loose connections
3. Verify sensor inversion settings
4. Adjust motion timeout values

## Development

### Mock Mode
Enable mock mode to test the plugin without hardware:
1. Go to plugin settings
2. Check "Use mock hardware"
3. The plugin will simulate sensor readings for testing

### Debug Logging
Enable debug logging to troubleshoot issues:
1. Go to plugin settings
2. Check "Enable debug logging"
3. Check OctoPrint logs for detailed sensor information

## Author

**Chris Nesbitt-Smith** - [chrisns](https://github.com/chrisns)

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Support

- **Issues**: [GitHub Issues](https://github.com/chrisns/OctoPrint-MCP2221-Filament-Sensor/issues)
- **Documentation**: This README and inline help text
- **Testing**: Use mock mode for development and testing 